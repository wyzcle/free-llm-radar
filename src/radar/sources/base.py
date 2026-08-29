"""信息源基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from ..models import RawItem


class Source(ABC):
    name: str = "base"

    @abstractmethod
    def fetch(self, client: httpx.Client) -> list[RawItem]:
        """返回本轮抓到的原始条目；失败返回空列表而非抛异常。"""
