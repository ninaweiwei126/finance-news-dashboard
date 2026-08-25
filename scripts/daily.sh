#!/bin/bash
# 每日采集脚本：cd 到项目根目录并运行采集器
cd "$(dirname "$0")/.."
python3 run_daily.py "$@"
