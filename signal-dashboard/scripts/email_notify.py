#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from pathlib import Path


def load(path: str) -> list[dict]:
    if not path:
        return []
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def state_map(items: list[dict]) -> dict[str, dict]:
    return {item.get("symbol", ""): item for item in items if item.get("symbol")}


def changed_symbols(previous: list[dict], current: list[dict]) -> list[dict]:
    old = state_map(previous)
    changes = []
    for item in current:
        symbol = item.get("symbol")
        old_item = old.get(symbol)
        if old_item is None or old_item.get("state_code") != item.get("state_code"):
            changes.append(item)
    return changes


def format_item(item: dict) -> str:
    return (
        f"{item['symbol']}：{item['state_label']}\n"
        f"  价格：${item['price']:.2f}\n"
        f"  距参考高点：{item['drawdown_pct']:+.2f}%\n"
        f"  下一触发价：${item['trigger_price']:.2f}\n"
        f"  日线 K/D/J：{item['daily_k']:.1f} / {item['daily_d']:.1f} / {item['daily_j']:.1f}\n"
        f"  周线 K/D/J：{item['weekly_k']:.1f} / {item['weekly_d']:.1f} / {item['weekly_j']:.1f}\n"
        f"  原因：{item['state_reason']}\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Send NVDA/GOOGL signal email")
    parser.add_argument("--previous", required=True)
    parser.add_argument("--current", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    current = load(args.current)
    previous = load(args.previous)
    if not current:
        print("No current status data; email skipped.")
        return 0

    changes = current if args.force else changed_symbols(previous, current)
    if not changes:
        print("No signal state changes; email skipped.")
        return 0

    username = os.environ.get("MAIL_USERNAME", "").strip()
    password = os.environ.get("MAIL_APP_PASSWORD", "").strip()
    recipient = (os.environ.get("MAIL_TO", "").strip() or username)
    if not username or not password or not recipient:
        print("Mail secrets are not configured; email skipped.")
        return 0

    subject_states = " | ".join(f"{item['symbol']} {item['state_label'].split(' · ')[0]}" for item in changes)
    subject = f"[NVDA/GOOGL 信号] {subject_states}"
    updated = current[0].get("updated_at", "")
    body = [
        "NVDA + GOOGL 信号状态发生变化",
        f"更新时间：{updated}",
        "",
        *[format_item(item) for item in changes],
        "看板：https://ninaweiwei126.github.io/finance-news-dashboard/signal-dashboard/docs/nvda-googl-dashboard.html",
        "",
        "说明：邮件由 GitHub Actions 自动发送；仅状态变化时推送。",
    ]

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = username
    message["To"] = recipient
    message.set_content("\n".join(body))

    context = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(username, password)
        smtp.send_message(message)

    print(f"Email sent to {recipient}: {subject}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
