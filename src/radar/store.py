"""JSON 文件存储：按 id 合并去重 + last_seen 状态流转。

选择 JSON 而非 SQLite：数据量小、需要提交进 git 留痕可追溯，
且 diff 可读、无合并冲突风险。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .models import STATUS_ACTIVE, STATUS_STALE, FreebieItem

log = logging.getLogger("radar.store")

STALE_AFTER_DAYS = 14  # 连续 N 天未再出现则标记为 stale，不再上页


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.items: dict[str, FreebieItem] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for raw in data.get("items", []):
                item = FreebieItem.model_validate(raw)
                self.items[item.id] = item
            log.info("载入存量 %s 条 <- %s", len(self.items), self.path)
        except Exception as exc:  # noqa: BLE001 - 存储损坏时按空库处理
            log.warning("读取存储失败，按空库处理: %s", exc)

    def merge(self, incoming: list[FreebieItem]) -> tuple[int, int]:
        """合并本轮结果，返回 (新增数, 更新数)。id 相同视为同一条事实。"""
        added = updated = 0
        for item in incoming:
            old = self.items.get(item.id)
            if old is None:
                self.items[item.id] = item
                added += 1
                continue
            patch = item.model_dump(exclude={"id", "discovered_at", "last_seen", "status"})
            changed = False
            for key, val in patch.items():
                if val not in (None, []) and getattr(old, key) != val:
                    setattr(old, key, val)
                    changed = True
            old.last_seen = item.last_seen
            old.status = STATUS_ACTIVE
            if changed:
                updated += 1
        return added, updated

    def mark_stale(self, stale_after_days: int = STALE_AFTER_DAYS) -> int:
        now = datetime.now(timezone.utc)
        n = 0
        for item in self.items.values():
            seen = datetime.fromisoformat(item.last_seen)
            if (now - seen).days >= stale_after_days and item.status != STATUS_STALE:
                item.status = STATUS_STALE
                n += 1
        return n

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "count": len(self.items),
            "items": [i.model_dump(mode="json") for i in self.items.values()],
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def export(self, include_stale: bool = False) -> list[FreebieItem]:
        items = sorted(self.items.values(), key=lambda i: i.discovered_at, reverse=True)
        if include_stale:
            return items
        return [i for i in items if i.status == STATUS_ACTIVE]
