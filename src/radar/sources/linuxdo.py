"""linux.do（Discourse）公开接口，中文圈免费额度情报最活跃的社区。

该站有 Cloudflare 防护：统一走 curl_cffi 浏览器指纹通道（环境变量代理 -> 直连），
失败回退普通 httpx。匿名 search.json 接口限速极严（长期 429），故不使用；
改为三条廉价路径：最新帖分页、资源荟萃/福利羊毛分类、周热门榜。
分类 id 可通过 https://linux.do/categories.json 查询。
"""

from __future__ import annotations

import json
import logging
import re
import time

from .. import http, impersonate
from ..models import Confidence, Kind, RawItem
from .base import Source

log = logging.getLogger("radar.linuxdo")

BASE = "https://linux.do"
LATEST_PAGES = 3
CATEGORIES = [("resource", 14, "资源荟萃"), ("welfare", 36, "福利羊毛")]
TOP_PERIOD = "weekly"
MAX_ITEMS = 24
PACE_SECONDS = 2.0  # Discourse 限速敏感，请求间统一间隔

KEYWORD_RE = re.compile(r"免费|额度|白嫖|限免|赠送|token|credit|free|llm|api", re.I)
BLOCK_RE = re.compile(
    r"代充|出售|收购|收u|出u|合租|拼车|回收|有偿|广告|抽奖"
    r"|发票|对公|号池|中转|1比1|稳定.*在线|纯Pro",  # 中转站广告特征
    re.I,
)


class LinuxDoSource(Source):
    name = "linux.do"

    def fetch(self, client) -> list[RawItem]:
        found: dict[int, RawItem] = {}
        self._via_latest(client, found)
        for slug, cid, _label in CATEGORIES:
            if len(found) >= MAX_ITEMS:
                break
            self._via_category(client, slug, cid, found)
        if len(found) < MAX_ITEMS:
            self._via_top(client, found)
        log.info("linux.do: %s 条", len(found))
        return list(found.values())

    # ---- 请求通道 ----

    def _get_json(self, client, url: str):
        time.sleep(PACE_SECONDS)
        text = impersonate.get(url, headers={"Accept": "application/json"})
        if text is not None:
            try:
                return json.loads(text)
            except json.JSONDecodeError as exc:
                log.warning("linux.do JSON 解析失败 %s: %s", url, exc)
                return None
        return http.get_json(client, url)  # 回退普通通道（可能被 403）

    # ---- 路径一：最新帖分页（捕捉刚发布的情报） ----

    def _via_latest(self, client, found: dict[int, RawItem]) -> None:
        for page in range(LATEST_PAGES):
            if len(found) >= MAX_ITEMS:
                return
            data = self._get_json(client, f"{BASE}/latest.json?page={page}")
            if not data:
                continue
            for topic in (data.get("topic_list") or {}).get("topics", []):
                self._add_topic(topic, found)
                if len(found) >= MAX_ITEMS:
                    return

    # ---- 路径二：资源荟萃 / 福利羊毛 分类最新帖 ----

    def _via_category(self, client, slug: str, cid: int, found: dict[int, RawItem]) -> None:
        data = self._get_json(client, f"{BASE}/c/{slug}/{cid}.json")
        if not data:
            return
        for topic in (data.get("topic_list") or {}).get("topics", []):
            self._add_topic(topic, found)
            if len(found) >= MAX_ITEMS:
                return

    # ---- 路径三：周热门（热门汇总帖） ----

    def _via_top(self, client, found: dict[int, RawItem]) -> None:
        data = self._get_json(client, f"{BASE}/top.json?period={TOP_PERIOD}")
        if not data:
            return
        for topic in (data.get("topic_list") or {}).get("topics", []):
            self._add_topic(topic, found)
            if len(found) >= MAX_ITEMS:
                return

    # ---- 条目构造 ----

    def _add_topic(self, topic: dict, found: dict[int, RawItem]) -> None:
        tid = topic.get("id")
        title = (topic.get("title") or topic.get("fancy_title") or "").strip()
        if not tid or tid in found or not title:
            return
        if BLOCK_RE.search(title) or not KEYWORD_RE.search(title):
            return
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
