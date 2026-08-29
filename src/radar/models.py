"""数据模型：RawItem（信息源产出）与 FreebieItem（入库条目）。"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Kind(str, Enum):
    PERMANENT = "permanent"  # 永久免费层 / 长期免费
    DAILY = "daily"          # 每日赠送
    NEW_USER = "new_user"    # 新人额度 / 试用 credits
    LIMITED = "limited"      # 限时活动
    FORUM = "forum"          # 社区动态


KIND_LABELS: dict[Kind, str] = {
    Kind.PERMANENT: "永久免费层",
    Kind.DAILY: "每日赠送",
    Kind.NEW_USER: "新人额度 / 试用",
    Kind.LIMITED: "限时活动",
    Kind.FORUM: "社区动态",
}

KIND_ORDER: list[Kind] = [
    Kind.LIMITED,
    Kind.PERMANENT,
    Kind.DAILY,
    Kind.NEW_USER,
    Kind.FORUM,
]


class Confidence(str, Enum):
    OFFICIAL = "official"  # 官方页面 / 官方 API
    LIST = "list"          # 社区人工维护清单
    FORUM = "forum"        # 论坛帖子


CONF_LABELS: dict[Confidence, str] = {
    Confidence.OFFICIAL: "官方",
    Confidence.LIST: "清单收录",
    Confidence.FORUM: "论坛帖",
}

STATUS_ACTIVE = "active"
STATUS_STALE = "stale"

REGION_LABELS = {"cn": "国内", "global": "国际"}


class RawItem(BaseModel):
    """信息源产出的一条原始记录，字段允许缺失，由 extract.convert 补全。"""

    title: str
    platform: str | None = None
    kind: Kind | None = None
    quota: str | None = None
    expires: str | None = None
    howto: str | None = None
    url: str = ""
    source_name: str = ""
    region: str = "global"  # cn / global
    confidence: Confidence = Confidence.LIST
    tags: list[str] = Field(default_factory=list)


class FreebieItem(BaseModel):
    id: str
    title: str
    platform: str = "未知平台"
    kind: Kind = Kind.PERMANENT
    quota: str | None = None
    expires: str | None = None
    howto: str | None = None
    url: str = ""
    source_name: str = ""
    region: str = "global"
    confidence: Confidence = Confidence.LIST
    tags: list[str] = Field(default_factory=list)
    discovered_at: str  # ISO8601 UTC
    last_seen: str
    status: str = STATUS_ACTIVE

    @staticmethod
    def make_id(platform: str, title: str) -> str:
        key = f"{platform.strip().lower()}|{title.strip().lower()}"
        return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
