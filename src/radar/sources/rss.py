"""RSS/Atom 源：Reddit 社区动态。

Reddit 对数据中心 IP / 无 OAuth 请求常返 403，失败自动跳过；
本地带浏览器 UA 通常可读 RSS。
"""

from __future__ import annotations

import logging
import re

import feedparser

from .. import http
from ..models import Confidence, Kind, RawItem
from .base import Source

log = logging.getLogger("radar.rss")

FEEDS = [
    ("r/LocalLLaMA", "https://www.reddit.com/r/LocalLLaMA/new/.rss", "global"),
]

KEYWORD_RE = re.compile(r"free|credit|tier|giveaway|白嫖|免费|额度", re.I)


class RssSource(Source):
    name = "rss"

    def fetch(self, client) -> list[RawItem]:
        items: list[RawItem] = []
        for feed_name, url, region in FEEDS:
            resp = http.request(client, url)
            if resp is None:
                continue
            parsed = feedparser.parse(resp.text)
            for entry in parsed.entries[:100]:
                title = (entry.get("title") or "").strip()
                link = entry.get("link") or ""
                if not title or not KEYWORD_RE.search(title):
                    # 仅标题匹配，避免摘要里偶然出现 free 的无关帖混入
                    continue
                summary = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", entry.get("summary") or ""))
                items.append(
                    RawItem(
                        title=title[:200],
                        platform=feed_name,
                        kind=Kind.FORUM,
                        quota=summary.strip()[:280] or None,
                        url=link,
                        source_name=self.name,
                        region=region,
                        confidence=Confidence.FORUM,
                    )
                )
        log.info("rss: %s 条", len(items))
        return items
