"""CLI 入口：python -m radar [--offline] [--data-dir PATH]"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import http
from .extract import convert
from .render import render
from .store import Store

log = logging.getLogger("radar")


def run(data_dir: Path, offline: bool = False) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    store = Store(data_dir / "freebies.json")

    if not offline:
        from .sources import ALL_SOURCES

        raw_items = []
        with http.make_client() as client:
            for src in ALL_SOURCES:
                try:
                    got = src.fetch(client)
                    log.info("%s: 抓到 %s 条", src.name, len(got))
                    raw_items.extend(got)
                except Exception:  # noqa: BLE001 - 单个源失败不影响整体
                    log.exception("源 %s 抓取失败", src.name)
        converted = [convert(r) for r in raw_items]
        added, updated = store.merge(converted)
        log.info("合并完成：新增 %s，更新 %s", added, updated)

    stale = store.mark_stale()
    if stale:
        log.info("标记 %s 条为 stale（连续 14 天未再出现）", stale)
    store.save()
    # README 渲染到数据目录的上一级（仓库根目录），与 data/freebies.json 的相对链接配套
    out = render(store.export(), data_dir.parent)
    active = len(store.export())
    print(f"完成：有效条目 {active}，README -> {out}")


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)  # 每个请求一行太吵
    parser = argparse.ArgumentParser(
        prog="radar", description="免费 LLM 资源雷达：聚合公开免费额度情报"
    )
    parser.add_argument("--offline", action="store_true", help="不联网，仅用已有数据重新渲染")
    parser.add_argument("--data-dir", default="data", help="数据目录（默认 ./data）")
    args = parser.parse_args(argv)
    run(Path(args.data_dir), offline=args.offline)


if __name__ == "__main__":
    main()
