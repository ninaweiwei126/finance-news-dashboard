#!/bin/bash
# macOS 每日自动运行（launchd）：每天 17:30 运行采集（A股/港股收盘后）
# 用法: bash scripts/setup_launchd.sh [小时] [分钟]
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOUR="${1:-17}"
MINUTE="${2:-30}"
LABEL="com.weijin.finance-news-daily"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>$ROOT/run_daily.py</string>
    </array>
    <key>WorkingDirectory</key><string>$ROOT</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>$HOUR</integer>
        <key>Minute</key><integer>$MINUTE</integer>
    </dict>
    <key>StandardOutPath</key><string>$ROOT/data/daily.log</string>
    <key>StandardErrorPath</key><string>$ROOT/data/daily.err.log</string>
</dict>
</plist>
PL
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "已安装定时任务：每天 ${HOUR}:$(printf '%02d' "$MINUTE") 运行 ($PLIST)"
