#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ResumeCube 简历魔方 · 本地开发服务器 + Dify MCP 转发代理
=========================================================
零第三方依赖，只用 Python 标准库。

用途：
  1) 静态托管本目录下的 index.html（打开 http://127.0.0.1:8787 即用）
  2) 把浏览器的 /mcp 请求转发到 Dify MCP Server，并补上 CORS 响应头
     —— Dify 官方 MCP 端点没有返回 Access-Control-Allow-Origin，
        纯静态页面（含 GitHub Pages）直连会被浏览器拦截。
  3) 可选：转发 /v1/* 到 Dify Service API

启动：
  python proxy.py                # 默认 8787 端口，自动打开浏览器
  python proxy.py --port 9000
  python proxy.py --no-browser

注意：
  密钥默认内置在 index.html 里（本项目按需求硬编码），本代理不会把密钥写到日志。
  生产环境请改成由后端注入密钥，不要明文放在前端。
"""

import argparse
import json
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MCP = "https://api.dify.ai/mcp/server/nMpZfw4ZeCtHxFAf/mcp"
DEFAULT_API = "https://api.dify.ai/v1"
DEFAULT_KEY = "sk-12afc6e78c2640ca9a9a02d8d7d5aa5f"

MCP_URL = os.environ.get("RC_MCP_URL", DEFAULT_MCP)
API_BASE = os.environ.get("RC_API_BASE", DEFAULT_API)
FALLBACK_KEY = os.environ.get("RC_API_KEY", DEFAULT_KEY)

CT_JSON = "application/json; charset=utf-8"


class Handler(BaseHTTPRequestHandler):
    server_version = "ResumeCubeProxy/1.0"

    # ---------- 基础工具 ----------
    def _cors(self):
        origin = self.headers.get("Origin") or "*"
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
        self.send_header("Access-Control-Allow-Headers",
                         "Authorization, Content-Type, Accept, Mcp-Session-Id, X-Api-Key")
        self.send_header("Access-Control-Expose-Headers", "Content-Type, Mcp-Session-Id")
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Max-Age", "86400")

    def _send(self, code, body, content_type=CT_JSON, extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, fmt, *args):
        msg = fmt % args
        # 不打印任何请求体 / 密钥，只打印方法与路径
        if "mcp" in msg.lower() or "v1/" in msg.lower():
            sys.stderr.write("[proxy] " + msg + "\n")

    # ---------- 预检 ----------
    def do_OPTIONS(self):
        self._send(204, b"")

    # ---------- 健康检查（前端据此判断代理是否可用） ----------
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/health":
            self._send(200, json.dumps({
                "ok": True, "relay": "mcp", "mcp": MCP_URL, "api": API_BASE
            }, ensure_ascii=False))
            return
        self._serve_static(path)

    def _serve_static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        rel = path.lstrip("/").replace("..", "")
        full = os.path.join(HERE, rel)
        if not os.path.isfile(full):
            self._send(404, json.dumps({"error": "not found", "path": path}, ensure_ascii=False))
            return
        ext = os.path.splitext(full)[1].lower()
        types = {
            ".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8", ".json": CT_JSON,
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".svg": "image/svg+xml", ".ico": "image/x-icon",
            ".md": "text/markdown; charset=utf-8", ".txt": "text/plain; charset=utf-8",
        }
        with open(full, "rb") as f:
            data = f.read()
        self._send(200, data, types.get(ext, "application/octet-stream"))

    # ---------- 转发 ----------
    def do_POST(self):
        path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""

        if path == "/mcp":
            target = MCP_URL
        elif path.startswith("/v1/"):
            target = API_BASE.rstrip("/") + path[len("/v1"):]
        else:
            self._send(404, json.dumps({"error": "unknown relay path", "path": path}, ensure_ascii=False))
            return

        auth = self.headers.get("Authorization") or ("Bearer " + FALLBACK_KEY)
        fwd_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": auth,
        }
        sid = self.headers.get("Mcp-Session-Id")
        if sid:
            fwd_headers["Mcp-Session-Id"] = sid

        req = Request(target, data=body, headers=fwd_headers, method="POST")
        try:
            with urlopen(req, timeout=180) as r:
                payload = r.read()
                ctype = r.headers.get("Content-Type", CT_JSON)
                code = r.status
                extra = {}
                rsid = r.headers.get("Mcp-Session-Id")
                if rsid:
                    extra["Mcp-Session-Id"] = rsid
                self._send(code, payload, ctype, extra)
        except HTTPError as e:
            payload = e.read()
            self._send(e.code, payload, e.headers.get("Content-Type", CT_JSON))
        except URLError as e:
            self._send(502, json.dumps({
                "error": "upstream unreachable",
                "detail": str(e.reason),
                "hint": "检查网络能否访问 api.dify.ai；若在国内网络，可尝试配置代理后重试。"
            }, ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            self._send(502, json.dumps({"error": "relay failed", "detail": str(e)}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description="ResumeCube 本地服务器 + Dify MCP 转发代理")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    url = "http://%s:%d/" % (args.host, args.port)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print("=" * 62)
    print("  ResumeCube 简历魔方 · 本地服务已启动")
    print("=" * 62)
    print("  页面地址      : " + url)
    print("  MCP 转发      : " + url + "mcp  ->  " + MCP_URL)
    print("  Service API   : " + url + "v1/*  ->  " + API_BASE)
    print("  健康检查      : " + url + "health")
    print("")
    print("  前端会自动探测 /health；检测到后 AI 通道显示「本地代理已连接」。")
    print("  停止服务：在本窗口按 Ctrl + C")
    print("=" * 62)
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
        srv.shutdown()


if __name__ == "__main__":
    main()
