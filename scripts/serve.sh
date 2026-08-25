#!/bin/bash
# 本地预览（防缓存）：在项目根目录起静态服务
cd "$(dirname "$0")/.."
PORT="${1:-8000}"
python3 scripts/serve.py "$PORT"
