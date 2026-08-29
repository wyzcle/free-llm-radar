"""渲染 README.md 汇总页（按类型分组的 Markdown 表格）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import (
    CONF_LABELS,
    KIND_LABELS,
    KIND_ORDER,
    REGION_LABELS,
    Confidence,
    FreebieItem,
    Kind,
)

TZ8 = timezone(timedelta(hours=8))

CONF_RANK = {Confidence.OFFICIAL: 0, Confidence.LIST: 1, Confidence.FORUM: 2}

HEADER = """# 免费 LLM 资源雷达

> 自动聚合全网**公开**的免费大模型额度情报：限时活动 / 永久免费层 / 每日赠送 / 新人额度 / 社区动态。
> 本页由 [radar](src/radar) 自动生成，GitHub Actions 每 6 小时刷新一次；也可本地运行 `python -m radar`。
> 国内网络提示：GitHub 清单与 OpenRouter 可直连；linux.do / Reddit 有 Cloudflare 拦截，需设置 `HTTPS_PROXY`（如 Clash 的 `http://127.0.0.1:7897`）后再运行，未配置时这些源自动跳过。

最后更新：**{updated}** ｜ 有效条目：**{total}** ｜ 48h 内新增：**{fresh}** ｜ 来源：{sources}

## 合规边界（先读这段）

- 本项目只聚合互联网上**公开**的信息：官方页面 / 官方 API / 社区维护清单 / 论坛公开帖，遵守 robots.txt 并对请求限速。
- **不抓取、不存储、不使用任何泄露的 API key** —— 使用他人泄露的凭证属于未授权访问，有法律风险，且此类 key 会被厂商快速吊销，得不偿失。
- 逆向 web 端点的 free-api 类项目仅收录链接与风险提示（违反平台 ToS，随时可能失效或封号），不提供部署指引。
- 各项额度以平台官方页面为准，本项目信息仅供参考，转载请注明原始来源。

## 可信度说明

| 标记 | 含义 |
| --- | --- |
| 官方 | 平台官方页面 / 官方 API 直接读取，最可靠 |
| 清单收录 | 社区人工维护的汇总清单收录（mnfst/awesome-free-llm-apis 等） |
| 论坛帖 | 论坛公开帖子，时效性强，真伪与有效期需自行甄别 |

"""


def _esc(text: str | None, limit: int = 180) -> str:
    if not text:
        return "—"
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text.replace("|", "\\|") or "—"


def _is_fresh(item: FreebieItem, cutoff: datetime) -> bool:
    try:
        return datetime.fromisoformat(item.discovered_at) >= cutoff
    except ValueError:
        return False


def render(items: list[FreebieItem], out_dir: Path) -> Path:
    now = datetime.now(TZ8)
    fresh_cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

    groups: dict[Kind, list[FreebieItem]] = {k: [] for k in KIND_ORDER}
    source_counter: dict[str, int] = {}
    fresh = 0
    for it in items:
        groups[it.kind].append(it)
        source_counter[it.source_name or "unknown"] = (
            source_counter.get(it.source_name or "unknown", 0) + 1
        )
        if _is_fresh(it, fresh_cutoff):
            fresh += 1

    sources_txt = "、".join(
        f"{name}({n})" for name, n in sorted(source_counter.items(), key=lambda kv: -kv[1])
    )
    lines = [
        HEADER.format(
            updated=now.strftime("%Y-%m-%d %H:%M") + " (UTC+8)",
            total=len(items),
            fresh=fresh,
            sources=sources_txt or "—",
        )
    ]

    for kind in KIND_ORDER:
        rows = groups[kind]
        lines.append(f"\n## {KIND_LABELS[kind]}（{len(rows)}）\n")
        if not rows:
            lines.append("_暂无条目_\n")
            continue
        lines.append("| 平台 | 内容 / 额度 | 领取 / 详情 | 来源 | 可信度 | 地区 | 发现 |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for it in sorted(
            rows, key=lambda x: (x.platform.lower(), CONF_RANK.get(x.confidence, 9))
        ):
            date_txt = "—"
            try:
                date_txt = datetime.fromisoformat(it.discovered_at).astimezone(TZ8).strftime(
                    "%m-%d"
                )
            except ValueError:
                pass
            fresh_mark = " 🆕" if _is_fresh(it, fresh_cutoff) else ""
            conf = CONF_LABELS.get(it.confidence, it.confidence.value)
            region = REGION_LABELS.get(it.region, it.region)
            tags = " ".join(f"`{t}`" for t in it.tags)

            if it.kind == Kind.FORUM:
                platform_cell = _esc(it.platform)
                content = f"[{_esc(it.title, 80)}]({it.url})" if it.url else _esc(it.title, 80)
                if it.quota:
                    content += "：" + _esc(it.quota, 140)
            else:
                platform_cell = f"[{_esc(it.platform)}]({it.url})" if it.url else _esc(it.platform)
                content = _esc(it.quota or it.title)
            if tags:
                content += " " + tags

            lines.append(
                f"| {platform_cell} | {content} | {_esc(it.howto, 80)} | "
                f"{_esc(it.source_name)} | {conf} | {region} | {date_txt}{fresh_mark} |"
            )
        lines.append("")

    lines.append(
        "\n---\n\n<sub>由 free-llm-radar 自动生成 · 结构化数据见 "
        "[data/freebies.json](data/freebies.json) · 本地运行：`python -m radar`</sub>\n"
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "README.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
