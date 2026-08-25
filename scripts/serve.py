#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地静态服务（防缓存版）：所有响应带 Cache-Control: no-store，
确保前端修改后刷新即可看到最新页面，不会被浏览器缓存旧版本。
用法: python3 scripts/serve.py [端口]   默认 8000
"""
import functools
import http.server
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000

class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, fmt, *args):
        sys.stdout.write("[serve] %s %s\n" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    print(f"打开: http://localhost:{PORT}/web/  (防缓存模式)")
    http.server.ThreadingHTTPServer(("", PORT), NoCacheHandler).serve_forever()
