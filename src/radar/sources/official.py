"""厂商官方信息：OpenRouter 免费模型统计（官方 API）+ 静态定价页关键词摘录。

静态页面解析是尽力而为：JS 渲染或反爬导致拿不到内容时自动跳过。
"""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from .. import http
from ..extract import classify_kind
from ..models import Confidence, Kind, RawItem
from .base import Source

log = logging.getLogger("radar.official")


class OpenRouterSource(Source):
    name = "openrouter"

    API = "https://openrouter.ai/api/v1/models"
    PAGE = "https://openrouter.ai/models?max_price=0"

    def fetch(self, client) -> list[RawItem]:
        data = http.get_json(client, self.API)
        if not data:
            return []
        models = data.get("data") or []
        free = [
            m
            for m in models
            if str(m.get("id", "")).endswith(":free")
            or str((m.get("pricing") or {}).get("prompt", "1")) == "0"
        ]
        if not free:
            return []
        free.sort(key=lambda m: -(m.get("context_length") or 0))
        names = [str(m.get("name") or m.get("id", "?")) for m in free[:6]]
        quota = (
            f"当前 {len(free)} 个免费模型，注册即可调用（有每日请求上限）。"
            f"大上下文代表：{'、'.join(names)} 等"
        )
        return [
            RawItem(
                title="OpenRouter 免费模型池",
                platform="OpenRouter",
                kind=Kind.PERMANENT,
                quota=quota[:400],
                howto="注册 OpenRouter 后调用带 :free 后缀的模型",
                url=self.PAGE,
                source_name=self.name,
                region="global",
                confidence=Confidence.OFFICIAL,
            )
        ]


# (平台, URL, 地区, 命中关键词) —— 仅收静态渲染页，SPA 页面（如国产云控制台）拿不到内容会自动跳过
STATIC_PAGES = [
    (
        "Google AI Studio (Gemini)",
        "https://ai.google.dev/gemini-api/docs/pricing",
        "global",
        r"free of charge|free tier|no charge|免费",
    ),
    (
        "Cloudflare Workers AI",
        "https://developers.cloudflare.com/workers-ai/platform/pricing/",
        "global",
        r"free|neurons|每日|免费",
    ),
    (
        "GitHub Models",
        "https://docs.github.com/en/github-models/use-github-models/prototyping-with-ai-models",
        "global",
        r"free|rate limit|免费|速率",
    ),
    ("智谱开放平台", "https://open.bigmodel.cn/pricing", "cn", r"免费|赠送"),
    (
        "ModelScope 魔搭社区",
        "https://modelscope.cn/docs/model-service/API-Inference/intro",
        "cn",
        r"免费|每日|赠送",
    ),
    ("SiliconFlow 硅基流动", "https://siliconflow.cn/pricing", "cn", r"免费|赠送"),
]


class OfficialPagesSource(Source):
    name = "official-pages"

    def fetch(self, client) -> list[RawItem]:
        items: list[RawItem] = []
        for platform, url, region, marker in STATIC_PAGES:
            text = http.get_text(client, url)
            if not text:
                continue
            snippet = self._extract(text, marker)
            if not snippet:
                continue
            items.append(
                RawItem(
                    title=f"{platform} 官方免费额度",
                    platform=platform,
                    kind=classify_kind(snippet, default=Kind.PERMANENT),
                    quota=snippet,
                    howto="以官方页面说明为准",
                    url=url,
                    source_name=self.name,
                    region=region,
                    confidence=Confidence.OFFICIAL,
                )
            )
        log.info("official-pages: %s 条", len(items))
        return items

    @staticmethod
    def _extract(html: str, marker: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        lines = [re.sub(r"\s+", " ", ln).strip() for ln in soup.get_text("\n").splitlines()]
        hits = [ln for ln in lines if 10 < len(ln) < 300 and re.search(marker, ln, re.I)]
        # 只保留与额度/模型相关的描述性句子，过滤导航与页脚
        hits = [
            h
            for h in hits
            if re.search(r"tokens?|额度|模型|请求|credit|rate|调用|limit|免费|赠送", h, re.I)
        ]
        # 含具体数字（额度/限速值）的句子信息量更高，排前面
        hits.sort(key=lambda h: 0 if re.search(r"\d", h) else 1)
        return " ｜ ".join(dict.fromkeys(hits))[:400]
