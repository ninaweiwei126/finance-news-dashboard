# -*- coding: utf-8 -*-
"""通用 HTTP 工具：超时、重试、UA、gzip、JSON。纯标准库实现。"""
import gzip
import io
import json
import time
import urllib.request
import urllib.error

DEFAULT_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

USER_AGENT = DEFAULT_UA
TIMEOUT = 15
MAX_RETRIES = 2


class SourceError(Exception):
    """数据源级错误（网络失败、被拦截、解析失败等）。"""


def _build_opener(headers):
    opener = urllib.request.build_opener()
    req_headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
    req_headers.update(headers or {})
    return opener, req_headers


def http_get(url, headers=None, timeout=TIMEOUT, retries=MAX_RETRIES, encoding="utf-8"):
    """GET 请求，自动解 gzip，失败重试。返回解码后的文本。"""
    last_err = None
    for attempt in range(retries + 1):
        try:
            opener, req_headers = _build_opener(headers)
            req = urllib.request.Request(url, headers=req_headers)
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                    raw = gzip.decompress(raw)
                return raw.decode(encoding, errors="replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            last_err = e
            if attempt < retries:
                time.sleep(1.0 + attempt)
    raise SourceError(f"GET failed: {url} -> {last_err}")


def http_post(url, payload, headers=None, timeout=TIMEOUT, retries=MAX_RETRIES, encoding="utf-8"):
    """POST JSON 请求。payload 为 dict，自动序列化。"""
    last_err = None
    data = json.dumps(payload).encode("utf-8")
    for attempt in range(retries + 1):
        try:
            opener, req_headers = _build_opener(headers)
            req_headers.update({"Content-Type": "application/json"})
            req = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                    raw = gzip.decompress(raw)
                return raw.decode(encoding, errors="replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            last_err = e
            if attempt < retries:
                time.sleep(1.0 + attempt)
    raise SourceError(f"POST failed: {url} -> {last_err}")


def http_get_json(url, headers=None, timeout=TIMEOUT, retries=MAX_RETRIES):
    return json.loads(http_get(url, headers=headers, timeout=timeout, retries=retries))


def http_post_json(url, payload, headers=None, timeout=TIMEOUT, retries=MAX_RETRIES):
    return json.loads(http_post(url, payload, headers=headers, timeout=timeout, retries=retries))


def fetch_with_status(name, fn):
    """包装一次数据源调用，返回 (ok, data|error)。永不抛异常。"""
    try:
        return True, fn()
    except Exception as e:  # noqa: BLE001 数据源隔离
        return False, {"source": name, "error": str(e)[:300]}


def http_get_bytes(url, headers=None, timeout=TIMEOUT, retries=MAX_RETRIES):
    """GET 请求返回原始字节（不解码），用于 GBK 等非 UTF-8 响应。"""
    last_err = None
    for attempt in range(retries + 1):
        try:
            opener, req_headers = _build_opener(headers)
            req = urllib.request.Request(url, headers=req_headers)
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                    raw = gzip.decompress(raw)
                return raw
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            last_err = e
            if attempt < retries:
                time.sleep(1.0 + attempt)
    raise SourceError(f"GET failed: {url} -> {last_err}")
