# -*- coding: utf-8 -*-
"""Investing.com：新闻 RSS。
国内网络常被 Cloudflare 拦截（403）。带失败快速跳过，秒级降级。
"""

import xml.etree.ElementTree as ET
from datetime import datetime

from collector.common import http_get, fetch_with_status

NAME = "investing"

RSS_FEEDS = [
    ("https://www.investing.com/rss/news_25.rss", "Top News"),
    ("https://www.investing.com/rss/market_overview.rss", "Market Overview"),
    ("https://www.investing.com/rss/stock_market_news.rss", "Stock Market News"),
]
REQ_TIMEOUT = 6


def _parse_rss(text, feed_name):
    out = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return out
    for item in root.iter("item"):
        title = link = pub = desc = ""
        for child in item:
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "title":
                title = (child.text or "").strip()
            elif tag == "link":
                link = (child.text or "").strip()
            elif tag == "pubDate":
                pub = (child.text or "").strip()
            elif tag == "description":
                desc = (child.text or "").strip()
        if not title:
            continue
        out.append({
            "title": title,
            "summary": desc[:300],
            "time": _parse_rfc822(pub),
            "source": NAME,
            "sub_source": feed_name,
            "url": link,
        })
    return out


def _parse_rfc822(s):
    if not s:
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M %z", "%d %b %Y %H:%M:%S %z"):
        try:
            return datetime.strptime(s.strip(), fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return None


def fetch_news():
    all_items = []
    for url, label in RSS_FEEDS:
        try:
            text = http_get(url, headers={"Accept": "application/rss+xml"},
                            timeout=REQ_TIMEOUT, retries=0)
            all_items.extend(_parse_rss(text, label))
        except Exception:
            continue
    return all_items


def collect_all():
    result = {"quotes": [], "news": [], "flash": []}
    ok, v = fetch_with_status(NAME, fetch_news)
    if ok:
        result["news"] = v
    return result
