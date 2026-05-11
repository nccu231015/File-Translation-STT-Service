"""
Background sampler: while any GPU-heavy module holds a refcount, log host metrics periodically.
Disabled when GPU_LIVE_METRICS_ENABLED is false-ish.
English-only comments match project conventions.

Single-GPU: nvidia-smi returns one CSV row; GPU_VRAM_MiB and GPU_util_pct match that card
(summing one value or max of one value is identical).

Performance: acquire/release only touch a short lock (no I/O). Sampling runs on a daemon
thread, so HTTP/worker coroutines are not blocked. While no module holds a refcount, the
worker only sleeps and checks refcounts—no psutil and no nvidia-smi. When active, each tick
does one psutil read plus one nvidia-smi subprocess (typically tens of ms, not on the
async event loop).
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from collections import defaultdict
from contextlib import contextmanager

# Module labels (stable for grep / dashboards).
MODULE_VOICE = "voice"
MODULE_DOCUMENT_TRANSLATION = "document_translation"
MODULE_KM_ASSISTANT = "km_assistant"


def _env_enabled() -> bool:
    v = os.getenv("GPU_LIVE_METRICS_ENABLED", "true").lower()
    return v not in ("0", "false", "no", "off")


def _interval_seconds() -> float:
    try:
        return max(1.0, float(os.getenv("GPU_LIVE_METRICS_INTERVAL_SECONDS", "3")))
    except ValueError:
        return 3.0


_refs: defaultdict[str, int] = defaultdict(int)
_lock = threading.Lock()


def _sample_process_and_host():
    rss_mib = ram_pct = None
    try:
        import psutil

        proc = psutil.Process(os.getpid())
        rss_mib = proc.memory_info().rss / (1024.0 * 1024.0)
        ram_pct = psutil.virtual_memory().percent
    except Exception:
        pass

    vram_total_mib = util_max = None
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=8,
            stderr=subprocess.DEVNULL,
        )
        mem_vals: list[float] = []
        util_vals: list[float] = []
        for line in out.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2:
                try:
                    mem_vals.append(float(parts[0]))
                    util_vals.append(float(parts[1]))
                except ValueError:
                    continue
        if mem_vals:
            vram_total_mib = sum(mem_vals)
        if util_vals:
            util_max = max(util_vals)
    except Exception:
        pass

    return rss_mib, ram_pct, vram_total_mib, util_max


def _format_line(label: str, rss, ram_pct, vram_mib, util_pct) -> str:
    r = "n/a" if rss is None else f"{rss:.1f}"
    rp = "n/a" if ram_pct is None else f"{ram_pct:.1f}"
    gv = "n/a" if vram_mib is None else f"{vram_mib:.1f}"
    gu = "n/a" if util_pct is None else f"{util_pct:.0f}"
    return (
        "[LIVE_METRICS]"
        f" module={label}"
        f" RSS_MiB={r}"
        f" system_RAM_used_pct={rp}"
        f" GPU_VRAM_MiB={gv}"
        f" GPU_util_pct={gu}"
    )


_sampler_started = threading.Event()


def _sampler_worker():
    interval = _interval_seconds()
    while True:
        time.sleep(interval)
        if not _env_enabled():
            continue
        with _lock:
            active = [(k, v) for k, v in _refs.items() if v > 0]
        if not active:
            continue
        rss_mib, ram_pct, vram_mib, util_max = _sample_process_and_host()
        for lbl, cnt in sorted(active):
            line = _format_line(lbl, rss_mib, ram_pct, vram_mib, util_max)
            if cnt != 1:
                line += f" concurrent_refs={cnt}"
            print(line, flush=True)


def _ensure_sampler_started():
    if _sampler_started.is_set():
        return
    with _lock:
        if _sampler_started.is_set():
            return
        threading.Thread(target=_sampler_worker, daemon=True, name="gpu-live-metrics").start()
        _sampler_started.set()


def gpu_work_acquire(module: str) -> None:
    if not _env_enabled():
        return
    if not module:
        return
    _ensure_sampler_started()
    with _lock:
        _refs[module] += 1


def gpu_work_release(module: str) -> None:
    if not _env_enabled():
        return
    if not module:
        return
    with _lock:
        if module not in _refs or _refs[module] <= 0:
            return
        _refs[module] -= 1
        if _refs[module] <= 0:
            del _refs[module]


@contextmanager
def gpu_work_scope(module: str):
    """
    Sync context manager safe across async callers ( refcount only ).
    Increments refcount around GPU-heavy sections; sampler runs every N seconds while >0.
    """
    gpu_work_acquire(module)
    try:
        yield
    finally:
        gpu_work_release(module)


def get_active_modules() -> dict[str, int]:
    """Return a snapshot of modules currently holding GPU work refcounts.

    Keys are module label strings; values are the refcount (concurrent tasks).
    Safe to call from async context — only acquires a short threading lock.
    """
    with _lock:
        return {k: v for k, v in _refs.items() if v > 0}
