"""信息源注册表。"""

from __future__ import annotations

from .github_lists import GitHubListsSource
from .linuxdo import LinuxDoSource
from .official import OfficialPagesSource, OpenRouterSource
from .rss import RssSource
from .base import Source

ALL_SOURCES: list[Source] = [
    OpenRouterSource(),      # 官方 API，最稳
    GitHubListsSource(),     # 社区维护清单（api.github.com，国内直连可用）
    LinuxDoSource(),         # 中文社区动态（可能被 Cloudflare 拦截，自动跳过）
    RssSource(),             # Reddit 动态（数据中心 IP 可能 403，自动跳过）
    OfficialPagesSource(),   # 厂商官方定价/活动页（尽力而为）
]

__all__ = ["ALL_SOURCES", "Source"]
