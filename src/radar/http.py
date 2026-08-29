"""共享 HTTP 工具：统一 UA、超时、重试与限速。

httpx 默认 trust_env=True，自动识别 HTTPS_PROXY/HTTP_PROXY 环境变量；
国内网络访问部分源（linux.do、Reddit 等）时设置代理环境变量即可。
"""

from __future__ import annotations

import logging
import time

import httpx

log = logging.getLogger("radar.http")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 free-llm-radar/0.1"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

MIN_INTERVAL = 0.6  # 相邻请求最小间隔（秒），所有源统一限速

_last_ts = 0.0


def throttle() -> None:
    global _last_ts
    wait = MIN_INTERVAL - (time.monotonic() - _last_ts)
    if wait > 0:
        time.sleep(wait)
    _last_ts = time.monotonic()


def make_client() -> httpx.Client:
    return httpx.Client(
        headers=HEADERS,
        timeout=httpx.Timeout(20.0),
        follow_redirects=True,
    )


def request(
    client: httpx.Client,
    url: str,
    *,
    retries: int = 1,
    headers: dict[str, str] | None = None,
) -> httpx.Response | None:
    """GET 请求，返回 None 表示失败（调用方按缺数据处理，不抛异常）。"""
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        throttle()
        try:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                return resp
            last_err = httpx.HTTPStatusError(
                f"HTTP {resp.status_code}", request=resp.request, response=resp
            )
            log.warning("HTTP %s <- %s", resp.status_code, url)
        except Exception as exc:  # noqa: BLE001 - 所有网络错误统一降级
            last_err = exc
            log.warning("请求失败(%s/%s) %s: %s", attempt + 1, retries + 1, url, exc)
        if attempt < retries:
            time.sleep(1.0 + attempt)
    log.warning("放弃 %s: %s", url, last_err)
    return None


def get_text(client: httpx.Client, url: str) -> str | None:
    resp = request(client, url)
    return resp.text if resp is not None else None


def get_json(client: httpx.Client, url: str):
    resp = request(client, url)
    if resp is None:
        return None
    try:
        return resp.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("JSON 解析失败 %s: %s", url, exc)
        return None
