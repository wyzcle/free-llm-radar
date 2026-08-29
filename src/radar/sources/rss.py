"""RSS/Atom 源：Hugging Face 论坛、Reddit 社区动态。

优先走 curl_cffi 指纹通道（部分站点对非浏览器 TLS 指纹返回 403），
失败回退普通 httpx；Reddit 对数据中心 IP 拦截很严，拿不到属预期。
"""

from __future__ import annotations

import logging
import re

import feedparser

from .. import http, impersonate
from ..models import Confidence, Kind, RawItem
from .base import Source

log = logging.getLogger("radar.rss")

FEEDS = [
    ("HF 论坛", "https://discuss.huggingface.co/latest.rss", "global"),
    ("r/LocalLLaMA", "https://www.reddit.com/r/LocalLLaMA/new/.rss", "global"),
]

KEYWORD_RE = re.compile(r"free|credit|tier|giveaway|白嫖|免费|额度", re.I)


class RssSource(Source):
    name = "rss"

    def fetch(self, client) -> list[RawItem]:
        items: list[RawItem] = []
        for feed_name, url, region in FEEDS:
            text = impersonate.get(url)
            if text is None:
                resp = http.request(client, url)
                text = resp.text if resp is not None else None
            if not text:
                continue
            parsed = feedparser.parse(text)
            count = 0
            for entry in parsed.entries[:100]:
                title = (entry.get("title") or "").strip()
                link = entry.get("link") or ""
                # 仅标题匹配，避免摘要里偶然出现 free 的无关帖混入
                if not title or not KEYWORD_RE.search(title):
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
                count += 1
            log.info("%s: %s 条", feed_name, count)
        log.info("rss: %s 条", len(items))
        return items
