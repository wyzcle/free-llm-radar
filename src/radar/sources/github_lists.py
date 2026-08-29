"""GitHub 社区维护清单：经 api.github.com 读取 raw README（国内可直连，无需代理）。

兼容两种主流版式：
1. mnfst 式：`### [厂商](注册链接) 🇨🇳` 分节 + 免费层描述 + 模型表格
2. nejib1 / open-free-llm-api 式：分类分节（Permanent / Trial / Self-host...）+ 厂商表格
"""

from __future__ import annotations

import logging
import re

from .. import http
from ..extract import classify_kind, classify_section
from ..models import Confidence, FreebieItem, Kind, RawItem
from .base import Source

log = logging.getLogger("radar.github_lists")

README_API = "https://api.github.com/repos/{repo}/readme"
README_HEADERS = {"Accept": "application/vnd.github.raw+json"}

LIST_REPOS = [
    "mnfst/awesome-free-llm-apis",
    "open-free-llm-api/awesome-freellm-apis",
    "nejib1/Free-LLM",
]

MAX_ITEMS_PER_REPO = 60

CN_FLAG = "\U0001F1E8\U0001F1F3"  # 🇨🇳

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
HEADING_LINK_RE = re.compile(r"^\s*(?:\*\*)?\[([^\]]+)\]\((https?://[^)\s]+)\)(?:\*\*)?")
LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
HTML_RE = re.compile(r"<[^>]+>")
FOOTNOTE_RE = re.compile(r"\[\^\w+\]")
FENCE_RE = re.compile(r"^\s*```")
SEP_ROW_RE = re.compile(r"^\s*\|?[\s:\-|]+\|?\s*$")
BULLET_RE = re.compile(
    r"^\s*(?:[-*]|\d+[.)])\s+(?:\*\*)?\[([^\]]+)\]\((https?://[^)\s]+)\)(?:\*\*)?[:\s—\-]*(.*)$"
)
RATE_RE = re.compile(r"\d+\s*(RPM|RPD|TPM|RPS|concurrent)", re.I)
HEADER_WORDS = {"provider", "provider name", "model name", "platform", "service", "---"}
SKIP_SECTION_RE = re.compile(
    r"contents|目录|quick start|quick reference|how to use|why this|base url|基础教程"
    r"|best free model|weekly usage|usage|abbreviation|glossary|缩写",
    re.I,
)
# 目录表表头首列白名单：只有这类表才产出条目（其余为缩写/明细/统计表，整表跳过）
DIRECTORY_HEADER_CELLS = {"provider", "provider name", "platform", "tool"}


def _is_junk_platform(name: str) -> bool:
    if re.match(r"^[A-Z]{2,6}$", name):
        return True  # RPM / TPD / TPM 之类的缩写定义行
    if re.match(r"^[a-z0-9][a-z0-9._\-]*(/[\w.\-]+)?$", name) and ("-" in name or "/" in name):
        return True  # 模型 id 行：agnes-1.5-flash、qwen/qwen3.5-397b-a17b
    return False


def _clean(cell: str) -> str:
    cell = IMAGE_RE.sub("", cell)
    cell = FOOTNOTE_RE.sub("", cell)
    cell = HTML_RE.sub("", cell)
    cell = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", cell)  # [text](url) -> text
    cell = cell.replace("`", "")
    cell = re.sub(r"\s+", " ", cell).strip().strip("*_").strip()
    return cell


def _first_link(text: str) -> str:
    m = LINK_RE.search(text)
    return m.group(2) if m else ""


class _Reader:
    """逐行扫描清单 README，产出 RawItem。"""

    def __init__(self, repo: str):
        self.repo = repo
        self.items: list[RawItem] = []
        self.section = ""  # 最近的分类分节标题（推断 kind 用）
        self.section_kind: Kind | None = None
        self.section_tags: list[str] = []
        self.provider: str | None = None  # mnfst 式厂商分节名
        self.provider_url = ""
        self.provider_region = "global"
        self.desc: list[str] = []
        self.models: list[str] = []
        self.rates: list[str] = []
        self.in_fence = False
        self._in_table = False  # 当前是否处于一张表格中
        self._table_dir = False  # 当前表格是否为厂商目录表

    # ---- 分节状态 ----

    def _set_section(self, text: str) -> None:
        self.section = text
        self.section_kind, self.section_tags = classify_section(text)

    def flush_provider(self) -> None:
        if not self.provider:
            return
        desc_txt = " ".join(self.desc).strip()
        parts = []
        if desc_txt:
            parts.append(desc_txt)
        if self.models:
            shown = "、".join(self.models[:6]) + ("等" if len(self.models) > 6 else "")
            parts.append(f"免费模型 {len(self.models)} 个：{shown}")
        uniq_rates = list(dict.fromkeys(self.rates))[:3]
        if uniq_rates:
            parts.append("限速: " + "；".join(uniq_rates))
        quota = "｜".join(parts)[:400] or None
        kind = classify_kind(desc_txt) if desc_txt else (self.section_kind or Kind.PERMANENT)
        self.items.append(
            RawItem(
                title=f"{self.provider} 免费 API",
                platform=self.provider,
                kind=kind,
                quota=quota,
                howto="控制台申请 API Key",
                url=self.provider_url,
                source_name=self.repo,
                region=self.provider_region,
                confidence=Confidence.LIST,
                tags=list(self.section_tags),
            )
        )
        self.provider = None
        self.desc, self.models, self.rates = [], [], []

    # ---- 逐行处理 ----

    def feed(self, md: str) -> None:
        for line in md.splitlines():
            if FENCE_RE.match(line):
                self.in_fence = not self.in_fence
                self._in_table = False
                continue
            if self.in_fence:
                continue

            heading = HEADING_RE.match(line)
            if heading:
                self._in_table = False
                level, text = len(heading.group(1)), _clean(heading.group(2))
                link = HEADING_LINK_RE.match(_clean_keep_links(heading.group(2)))
                self.flush_provider()
                if link and level >= 3:
                    # mnfst 式厂商分节：### [Name](url) 🇨🇳
                    self.provider = link.group(1).strip()[:60]
                    self.provider_url = link.group(2)
                    self.provider_region = "cn" if CN_FLAG in heading.group(2) else "global"
                else:
                    self._set_section(text)
                continue

            stripped = line.strip()
            if stripped.startswith("|"):
                if SEP_ROW_RE.match(stripped):
                    continue  # 表头分隔行不影响表格状态
                self._on_table_row(line, stripped)
                continue

            self._in_table = False
            if self.provider is not None:
                text = _clean(stripped)
                if text and not text.startswith(("Base URL", "Docs", "文档")):
                    self.desc.append(text)
            else:
                self._on_bullet(stripped)

        self.flush_provider()

    def _is_directory_table(self, header_row: str) -> bool:
        cells = [_clean(c).lower() for c in header_row.strip().strip("|").split("|")]
        return (
            bool(cells)
            and cells[0] in DIRECTORY_HEADER_CELLS
            and len(cells) >= 3
            and not SKIP_SECTION_RE.search(self.section)
        )

    def _on_table_row(self, raw_line: str, stripped: str) -> None:
        cells = [_clean(c) for c in stripped.strip("|").split("|")]

        if self.provider is not None:
            # 厂商分节内的模型表格：表头行（Model Name ...）经 HEADER_WORDS 过滤
            first = cells[0] if cells else ""
            if not first or first.lower() in HEADER_WORDS:
                return
            self.models.append(first)
            for cell in cells[1:]:
                if RATE_RE.search(cell):
                    self.rates.append(cell)
            return

        if not self._in_table:
            # 表格首行 = 表头，据此判定整张表是否为厂商目录表
            self._in_table = True
            self._table_dir = self._is_directory_table(stripped)
            return

        if not self._table_dir:
            return

        first = cells[0] if cells else ""
        if not first or first.lower() in HEADER_WORDS or _is_junk_platform(first):
            return
        desc = " | ".join(c for c in cells[1:] if c)
        url = _first_link(raw_line)
        kind = self.section_kind or classify_kind(desc)
        region = "cn" if CN_FLAG in raw_line else "global"
        section_short = re.sub(r"^[^\w\u4e00-\u9fff]+", "", self.section)[:40]
        title = f"{first[:50]}｜{section_short}" if section_short else f"{first[:50]} 免费额度"
        self.items.append(
            RawItem(
                title=title,
                platform=first[:60],
                kind=kind,
                quota=desc[:400] or None,
                url=url,
                source_name=self.repo,
                region=region,
                confidence=Confidence.LIST,
                tags=list(self.section_tags),
            )
        )

    def _on_bullet(self, stripped: str) -> None:
        m = BULLET_RE.match(stripped)
        if not m or SKIP_SECTION_RE.search(self.section):
            return
        name, url, desc = m.group(1).strip(), m.group(2), m.group(3).strip()
        if not name or len(name) > 40 or _is_junk_platform(name):
            return
        kind = self.section_kind or classify_kind(desc)
        section_short = re.sub(r"^[^\w\u4e00-\u9fff]+", "", self.section)[:40]
        title = f"{name[:50]}｜{section_short}" if section_short else f"{name[:50]} 免费额度"
        self.items.append(
            RawItem(
                title=title,
                platform=name[:60],
                kind=kind,
                quota=desc[:400] or None,
                url=url,
                source_name=self.repo,
                region="global",
                confidence=Confidence.LIST,
                tags=list(self.section_tags),
            )
        )


def _clean_keep_links(text: str) -> str:
    """标题行清洗：去掉图片/脚注/HTML，但保留 [name](url) 供识别厂商链接。"""
    text = IMAGE_RE.sub("", text)
    text = FOOTNOTE_RE.sub("", text)
    text = HTML_RE.sub("", text)
    return text.strip()


class GitHubListsSource(Source):
    name = "github-lists"

    def fetch(self, client) -> list[RawItem]:
        items: list[RawItem] = []
        seen: set[str] = set()
        for repo in LIST_REPOS:
            resp = http.request(
                client, README_API.format(repo=repo), retries=1, headers=README_HEADERS
            )
            if resp is None:
                continue
            parsed = self._parse(repo, resp.text)
            for raw in parsed:
                key = FreebieItem.make_id(raw.platform or repo, raw.title)
                if key in seen:
                    continue
                seen.add(key)
                items.append(raw)
                if len(items) >= MAX_ITEMS_PER_REPO * len(LIST_REPOS):
                    break
            log.info("%s: 解析出 %s 条", repo, len(parsed))
        return items

    @staticmethod
    def _parse(repo: str, md: str) -> list[RawItem]:
        reader = _Reader(repo)
        reader.feed(md)
        return reader.items
