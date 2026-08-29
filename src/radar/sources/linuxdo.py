"""linux.do（Discourse）公开搜索接口，中文圈免费额度情报最活跃的社区。

注意：linux.do 有 Cloudflare 防护，直连或数据中心 IP 常被 403 拦截；
被拦截时本源自动跳过（返回空列表）。国内网络建议设置 HTTPS_PROXY 后运行。
"""

from __future__ import annotations

import logging
import re
from urllib.parse import quote

from .. import http
from ..models import Confidence, Kind, RawItem
from .base import Source

log = logging.getLogger("radar.linuxdo")

BASE = "https://linux.do"
QUERIES = ["免费额度", "免费 token", "白嫖", "限免", "free credit"]
MAX_ITEMS = 20

KEYWORD_RE = re.compile(r"免费|额度|白嫖|限免|赠送|羊毛|token|credit|free", re.I)
BLOCK_RE = re.compile(r"代充|出售|收购|收u|出u|合租|拼车|回收|有偿|广告", re.I)


class LinuxDoSource(Source):
    name = "linux.do"

    def fetch(self, client) -> list[RawItem]:
        found: dict[int, RawItem] = {}
        for q in QUERIES:
            if len(found) >= MAX_ITEMS:
                break
            data = http.get_json(client, f"{BASE}/search.json?q={quote(q)}")
            if not data:
                continue
            topics = {t.get("id"): t for t in data.get("topics", []) if t.get("id")}
            for post in data.get("posts", []):
                tid = post.get("topic_id")
                topic = topics.get(tid)
                if not topic or tid in found:
                    continue
                title = (topic.get("title") or topic.get("fancy_title") or "").strip()
                if not title or BLOCK_RE.search(title) or not KEYWORD_RE.search(title):
                    continue
                blurb = (post.get("blurb") or "").strip()
                found[tid] = RawItem(
                    title=title,
                    platform="linux.do",
                    kind=Kind.FORUM,
                    quota=blurb[:280] or None,
                    url=f"{BASE}/t/topic/{tid}",
                    source_name=self.name,
                    region="cn",
                    confidence=Confidence.FORUM,
                )
                if len(found) >= MAX_ITEMS:
                    break

        if not found:
            self._fallback_latest(client, found)

        log.info("linux.do: %s 条", len(found))
        return list(found.values())

    def _fallback_latest(self, client, found: dict[int, RawItem]) -> None:
        """搜索接口被拦截时，退回最新帖子列表按标题关键词过滤。"""
        for page in (0, 1):
            if len(found) >= MAX_ITEMS:
                return
            data = http.get_json(client, f"{BASE}/latest.json?page={page}")
            if not data:
                return
            for topic in (data.get("topic_list") or {}).get("topics", []):
                tid = topic.get("id")
                title = (topic.get("title") or "").strip()
                if not tid or tid in found or not title:
                    continue
                if BLOCK_RE.search(title) or not KEYWORD_RE.search(title):
                    continue
                found[tid] = RawItem(
                    title=title,
                    platform="linux.do",
                    kind=Kind.FORUM,
                    quota=None,
                    url=f"{BASE}/t/topic/{tid}",
                    source_name=self.name,
                    region="cn",
                    confidence=Confidence.FORUM,
                )
                if len(found) >= MAX_ITEMS:
                    return
