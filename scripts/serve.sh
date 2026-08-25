#!/bin/bash
# 本地预览：在项目根目录起静态服务（web 页读取 data/latest.json）
cd "$(dirname "$0")/.."
PORT="${1:-8000}"
echo "打开: http://localhost:${PORT}/web/"
python3 -m http.server "$PORT"
