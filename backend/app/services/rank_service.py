"""
rank_service.py

Built-in job title → rank (1~9) mapping.
Rank 1 = highest authority, rank 9 = lowest.

Permission rule:
  - Ranks 1~4 (管理層 and above) → can view subordinate records
  - Ranks 5~9 → no view access

Scope rule (for those with access):
  - Can view records of employees in the SAME department
    whose rank is NUMERICALLY GREATER (i.e. lower authority).
"""

# ── Job title → rank lookup ────────────────────────────────────────────────
_TITLE_TO_RANK: dict[str, int] = {
    # 1 — 最高管理層
    "董事長": 1,
    "總經理": 1,
    # 2 — 最高管理層
    "副總經理": 2,
    "總監": 2,
    "協理": 2,
    "資深經理": 2,
    "常駐監察人": 2,
    # 3 — 管理層
    "專案經理": 3,
    "專案副理": 3,
    "產品經理": 3,
    "經理": 3,
    "副理": 3,
    # 4 — 管理層
    "課長": 4,
    "副課長": 4,
    "專案課長": 4,
    "組長": 4,
    "副組長": 4,
    # 5 — 專業層
    "資深工程師": 5,
    "高級工程師": 5,
    "專案工程師": 5,
    "資深帶線主任": 5,
    "高級專員": 5,
    "資深專員": 5,
    "主任": 5,
    # 6 — 專業層
    "專員": 6,
    "副工程師": 6,
    "工程師": 6,
    "副工程師": 6,
    "職員": 6,
    "領班": 6,
    "辦事員": 6,
    "管理師": 6,
    # 7 — 專業層
    "助理": 7,
    "助理專員": 7,
    "助理工程師": 7,
    # 8 — 基層
    "作業員": 8,
    "技術員": 8,
    "固日作業員": 8,
    "固夜作業員": 8,
    "輪班作業員": 8,
    "固日技術員": 8,
    "固夜技術員": 8,
    "輪班技術員": 8,
    # 9 — 支援層
    "顧問": 9,
    "約僱": 9,
    "實習生": 9,
    "工讀生": 9,
    "按摩師": 9,
}

# Minimum rank level required to view subordinate records
_MANAGER_RANK_THRESHOLD = 4


def get_rank(duty_name: str) -> int | None:
    """
    Return the rank (1–9) for the given job title.
    Returns None if the title is not in the table.

    Falls back to a fuzzy match: if the title *contains* a known title
    (e.g. "資深軟體工程師" matches "工程師").
    """
    if not duty_name:
        return None

    # Exact match first
    rank = _TITLE_TO_RANK.get(duty_name)
    if rank is not None:
        return rank

    # Fuzzy: find the first known title that is contained in duty_name
    # Sort by length (longest first) to prefer more specific matches
    for title in sorted(_TITLE_TO_RANK.keys(), key=len, reverse=True):
        if title in duty_name:
            return _TITLE_TO_RANK[title]

    return None


def has_view_permission(rank: int | None) -> bool:
    """Return True if the rank grants permission to view subordinate records."""
    if rank is None:
        return False
    return rank <= _MANAGER_RANK_THRESHOLD
