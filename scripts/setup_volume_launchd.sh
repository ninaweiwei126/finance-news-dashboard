#!/bin/bash
# A股成交额追踪定时任务：每日两次（11:35 上午快照 / 15:05 全天快照）
# 用法: bash scripts/setup_volume_launchd.sh
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.weijin.finance-volume-snapshot"
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
        <string>$ROOT/scripts/volume_snapshot.py</string>
    </array>
    <key>WorkingDirectory</key><string>$ROOT</string>
    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Hour</key><integer>11</integer><key>Minute</key><integer>35</integer></dict>
        <dict><key>Hour</key><integer>15</integer><key>Minute</key><integer>5</integer></dict>
    </array>
    <key>StandardOutPath</key><string>$ROOT/data/volume.log</string>
    <key>StandardErrorPath</key><string>$ROOT/data/volume.err.log</string>
</dict>
</plist>
PL
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "已安装 A股成交额定时任务：每日 11:35（上午）与 15:05（全天）各采集一次 ($PLIST)"
