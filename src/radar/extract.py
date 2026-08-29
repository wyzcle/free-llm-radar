"""原始记录 -> 入库条目：稳定 id、类型分类、字段规整。"""

from __future__ import annotations

import re

from .models import Confidence, FreebieItem, Kind, RawItem, utcnow

# 分类规则按优先级排列，先命中先得
LIMITED_PAT = re.compile(
    r"限时|限免|即日起|截止|活动期|limited[- ]time|promo|for a limited|weekend|flash sale", re.I
)
DAILY_PAT = re.compile(r"每日|每天|daily|per[- ]day|/ ?day|每小时|hourly|RPD", re.I)
NEW_USER_PAT = re.compile(
    r"新人|新用户|注册(即送|送|赠送|可得)|trial|sign[- ]?up bonus|new[- ]user|one[- ]time", re.I
)
PERMANENT_PAT = re.compile(
    r"永久|长期|免费层|free[- ]tier|permanently|always[- ]free|free|credit|额度", re.I
)

# 分节标题 -> 类型（nejib1 式分类清单）
SECTION_KIND_RULES: list[tuple[re.Pattern[str], Kind]] = [
    (re.compile(r"trial|one[- ]time|试用", re.I), Kind.NEW_USER),
    (re.compile(r"renewable", re.I), Kind.PERMANENT),
    (re.compile(r"permanent|永久|长期|free tier", re.I), Kind.PERMANENT),
]

SECTION_TAG_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"self[- ]host|local", re.I), "self-host"),
]


def classify_kind(text: str, default: Kind = Kind.PERMANENT) -> Kind:
    if LIMITED_PAT.search(text):
        return Kind.LIMITED
    if DAILY_PAT.search(text):
        return Kind.DAILY
    if NEW_USER_PAT.search(text):
        return Kind.NEW_USER
    if PERMANENT_PAT.search(text):
        return Kind.PERMANENT
    return default


def classify_section(section: str) -> tuple[Kind | None, list[str]]:
    """从清单的分节标题推断类型与标签；未命中返回 (None, [])。"""
    for pat, kind in SECTION_KIND_RULES:
        if pat.search(section):
            tags = [tag for pat2, tag in SECTION_TAG_RULES if pat2.search(section)]
            return kind, tags
    tags = [tag for pat2, tag in SECTION_TAG_RULES if pat2.search(section)]
    return None, tags


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def convert(raw: RawItem) -> FreebieItem:
    now = utcnow().isoformat(timespec="seconds")
    platform = _clean_text(raw.platform or raw.source_name or "未知平台")[:60]
    title = _clean_text(raw.title)[:200]
    kind = raw.kind or classify_kind(" ".join(filter(None, [title, raw.quota, raw.howto])))
    return FreebieItem(
        id=FreebieItem.make_id(platform, title),
        title=title,
        platform=platform,
        kind=kind,
        quota=_clean_text(raw.quota)[:400] if raw.quota else None,
        expires=_clean_text(raw.expires)[:120] if raw.expires else None,
        howto=_clean_text(raw.howto)[:200] if raw.howto else None,
        url=raw.url,
        source_name=raw.source_name,
        region=raw.region,
        confidence=raw.confidence,
        tags=raw.tags,
        discovered_at=now,
        last_seen=now,
    )
