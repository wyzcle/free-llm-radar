"""浏览器 TLS 指纹请求通道（curl_cffi）：用于有 Cloudflare 防护的公开源。

对每个 URL 依次尝试：HTTPS_PROXY 环境变量代理 -> 直连，任一成功即返回文本。
未安装 curl_cffi 或全部失败时返回 None，调用方回退普通 httpx 通道（可能被
403 拦截，按缺数据降级）。仅用于读取公开只读接口，遵守限速。
"""

from __future__ import annotations

import logging
import os
import time

log = logging.getLogger("radar.impersonate")


def _proxy() -> dict[str, str] | None:
    raw = (
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("http_proxy")
    )
    return {"https": raw, "http": raw} if raw else None


def get(
    url: str,
    *,
    impersonate: str = "chrome",
    timeout: float = 20.0,
    headers: dict[str, str] | None = None,
) -> str | None:
    try:
        from curl_cffi import requests as cr
    except ImportError:
        log.info("curl_cffi 未安装，跳过浏览器指纹通道: %s", url)
        return None

    paths: list[dict[str, str] | None] = []
    px = _proxy()
    if px:
        paths.append(px)
    paths.append(None)

    for proxies in paths:
        for attempt in range(2):  # 每条路径 429 时退避重试一次
            try:
                r = cr.get(
                    url, impersonate=impersonate, proxies=proxies,
                    timeout=timeout, headers=headers,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("指纹请求异常 %s: %s", url, exc)
                break
            if r.status_code == 200:
                return r.text
            log.warning("指纹请求 %s <- %s (proxy=%s)", r.status_code, url, bool(proxies))
            if r.status_code == 429 and attempt == 0:
                time.sleep(6)
                continue
            break
    return None
