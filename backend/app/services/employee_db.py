"""
employee_db.py

Async MySQL connection pool for querying the employee directory
and storing employee usage records (for manager preview).

Database: aiservice on 172.16.2.68
Tables used:
  - employees (EMPID, EMPNAME, DEPTNAME, DUTYNAME)
  - employee_records (id, empid, type, file_name, summary, processed_at)
"""

import os
import asyncio
import aiomysql
from typing import Optional
from datetime import datetime

# ── Connection settings ────────────────────────────────────────────────────
DB_HOST = os.getenv("MYSQL_HOST", "172.16.2.68")
DB_PORT = int(os.getenv("MYSQL_PORT", "3306"))
DB_USER = os.getenv("MYSQL_USER", "aiadmin")
DB_PASS = os.getenv("MYSQL_PASS", "AIP@ssw0rd")
DB_NAME = os.getenv("MYSQL_DB", "aiservice")

_pool: Optional[aiomysql.Pool] = None
_pool_lock = asyncio.Lock()


async def _get_pool() -> aiomysql.Pool:
    global _pool
    if _pool is not None:
        return _pool
    async with _pool_lock:
        if _pool is None:
            _pool = await aiomysql.create_pool(
                host=DB_HOST, port=DB_PORT,
                user=DB_USER, password=DB_PASS, db=DB_NAME,
                charset="utf8mb4", autocommit=True,
                minsize=1, maxsize=5, echo=False,
            )
            print(f"[EmployeeDB] Pool created → {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}", flush=True)
    return _pool


# ── Auto-create records table on first use ─────────────────────────────────

async def ensure_records_table():
    """Create employee_records table if it doesn't already exist."""
    try:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS employee_records (
                        id           INT AUTO_INCREMENT PRIMARY KEY,
                        empid        VARCHAR(20) NOT NULL,
                        type         ENUM('voice','translation') NOT NULL,
                        file_name    VARCHAR(255),
                        summary      TEXT,
                        decisions    TEXT,
                        action_items TEXT,
                        processed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_empid (empid)
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """)
        print("[EmployeeDB] ✓ employee_records table ready", flush=True)
    except Exception as e:
        print(f"[EmployeeDB] ensure_records_table error: {e}", flush=True)


# ── Department helpers ─────────────────────────────────────────────────────

def _root_dept(deptname: str) -> str:
    """
    Extract the top-level department name.
    e.g. "製造部品管課" → "製造部"
         "研發部"       → "研發部"
    """
    idx = deptname.find("部")
    if idx >= 0:
        return deptname[: idx + 1]
    return deptname  # fallback: use full name if "部" not found


# ── Employee queries ───────────────────────────────────────────────────────

async def get_employee(empid: str) -> Optional[dict]:
    """Fetch a single employee by EMPID."""
    try:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT EMPID, EMPNAME, DEPTNAME, DUTYNAME "
                    "FROM employees WHERE EMPID = %s LIMIT 1",
                    (empid,),
                )
                row = await cur.fetchone()
        return dict(row) if row else None
    except Exception as e:
        print(f"[EmployeeDB] get_employee({empid}) error: {e}", flush=True)
        return None


async def get_department_employees(deptname: str) -> list[dict]:
    """
    Fetch all employees whose DEPTNAME starts with the same root department.

    "XX部" and "XX部XX課" are treated as the same department because they
    share the same root (everything up to and including '部').
    """
    root = _root_dept(deptname)
    try:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT EMPID, EMPNAME, DEPTNAME, DUTYNAME "
                    "FROM employees WHERE DEPTNAME LIKE %s ORDER BY EMPNAME",
                    (f"{root}%",),
                )
                rows = await cur.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"[EmployeeDB] get_department_employees({deptname}) error: {e}", flush=True)
        return []


async def get_subordinates(requester_empid: str, deptname: str, requester_rank: int) -> list[dict]:
    """
    Return same-root-department employees whose rank is lower
    (numerically greater) than the requester.
    Excludes the requester themselves.
    """
    from app.services.rank_service import get_rank

    all_dept = await get_department_employees(deptname)
    result = []
    for emp in all_dept:
        if emp["EMPID"] == requester_empid:
            continue
        emp_rank = get_rank(emp.get("DUTYNAME", ""))
        if emp_rank is None or emp_rank > requester_rank:
            emp["rank"] = emp_rank
            result.append(emp)
    return result


# ── Record storage ─────────────────────────────────────────────────────────

async def save_employee_record(
    empid: str,
    record_type: str,       # 'voice' | 'translation'
    file_name: str,
    summary: str = "",
    decisions: str = "",
    action_items: str = "",
) -> Optional[int]:
    """
    Insert a usage record for an employee.
    Returns the new record ID, or None on error.
    """
    try:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO employee_records "
                    "(empid, type, file_name, summary, decisions, action_items) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (empid, record_type, file_name, summary, decisions, action_items),
                )
                return cur.lastrowid
    except Exception as e:
        print(f"[EmployeeDB] save_employee_record({empid}) error: {e}", flush=True)
        return None


async def get_employee_records(empid: str) -> list[dict]:
    """Return all usage records for an employee, newest first."""
    try:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT id, empid, type, file_name, summary, decisions, "
                    "action_items, processed_at "
                    "FROM employee_records WHERE empid = %s "
                    "ORDER BY processed_at DESC",
                    (empid,),
                )
                rows = await cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if isinstance(d.get("processed_at"), datetime):
                d["processed_at"] = d["processed_at"].isoformat()
            result.append(d)
        return result
    except Exception as e:
        print(f"[EmployeeDB] get_employee_records({empid}) error: {e}", flush=True)
        return []
