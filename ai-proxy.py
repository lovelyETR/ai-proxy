#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================
#  ai-proxy —— 通用 AI 接口代理（引擎无关）
#  ---------------------------------------------------------------------------
#  作者：AWA　　本插件全由 DSH 开发
#
#  【设计目标：任何引擎、任何语言的插件都能接】
#  它就是一个标准 HTTP 服务，说的是 OpenAI 兼容格式。
#  所以「适配某个引擎」不需要为那个引擎改任何东西 ——
#  只要那个引擎的插件「会发 HTTP 请求」就可以。
#
#  起源引擎 / Unity / 虚幻 / 寒霜(Frostbite) / GMod / FiveM /
#  Minecraft / Godot / CryEngine / GameMaker / 自研引擎
#  …… 全都走同一套接口。
#
#  各引擎可直接复制的代码片段见同目录的「接入指南.txt」和 示例代码\。
#
#  【这一版补齐的兼容性】
#    /v1/models           许多插件启动时会探测模型列表，探不到就整个不工作
#    /v1/chat/completions 核心接口，支持真流式（SSE 逐块转发，边生成边收）
#    /v1/completions      老式补全接口，有些老插件还在用
#    /v1/embeddings       向量接口，部分插件会用到
#    OPTIONS 预检 + CORS  浏览器 / JS 插件需要
#    失败重试             上游偶发 5xx / 超时时自动重试
#    多上游轮转           配多个上游，一个挂了自动换下一个
#    请求日志落盘         出问题能查
#    config.json 支持     改配置不用编辑 bat
#    x-api-key 兼容       有些客户端不用 Authorization 而是 x-api-key
#
#  【零第三方依赖】只用 Python 标准库。Python 3.8+。
#  【开源】MIT License，详见同目录 LICENSE。
# ============================================================================

import json
import os
import secrets
import sys
import threading
import time
import urllib.error
import urllib.request

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Windows 控制台默认不是 UTF-8，中文日志会变乱码
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

VERSION = "1.1.0"
WATERMARK = "AWA"


# ---------------------------------------------------------------------------
# 配置：环境变量 > config.json > 默认值
# ---------------------------------------------------------------------------

def _load_config_file():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "config.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print("[warn] config.json 读不了，忽略: %s" % e)
        return {}


_CFG = _load_config_file()


def cfg(env_key, json_key, default):
    v = os.environ.get(env_key)
    if v is not None and str(v) != "":
        return v
    v = _CFG.get(json_key)
    if v is not None and str(v) != "":
        return v
    return default


def cfg_int(env_key, json_key, default):
    try:
        return int(str(cfg(env_key, json_key, default)).strip())
    except Exception:
        return default


API_KEY = str(cfg("AI_API_KEY", "api_key", "") or "").strip()
TOKENS_RAW = str(cfg("AI_TOKENS", "tokens", "") or "").strip()
HOST = str(cfg("AI_HOST", "host", "127.0.0.1")).strip()
PORT = cfg_int("AI_PORT", "port", 8787)
UPSTREAMS_RAW = str(cfg("AI_UPSTREAMS", "upstreams", "") or "").strip()
UPSTREAM_SINGLE = str(cfg("AI_UPSTREAM", "upstream", "https://api.deepseek.com")).strip()
FORCE_MODEL = str(cfg("AI_MODEL", "model", "") or "").strip()
RATE_PER_MIN = cfg_int("AI_RATE_PER_MIN", "rate_per_min", 30)
DAILY_QUOTA = cfg_int("AI_DAILY_QUOTA", "daily_quota", 500)
TIMEOUT = cfg_int("AI_TIMEOUT", "timeout", 60)
ADMIN_TOKEN = str(cfg("AI_ADMIN_TOKEN", "admin_token", "") or "").strip()
RETRY = cfg_int("AI_RETRY", "retry", 2)
LOG_PATH = str(cfg("AI_LOG", "log", "") or "").strip()
EXPOSE_MODELS = str(cfg("AI_EXPOSE_MODELS", "expose_models",
                        "deepseek-chat,deepseek-reasoner")).strip()

# 上游列表：AI_UPSTREAMS 优先（逗号分隔，轮转），否则用单个
if UPSTREAMS_RAW:
    UPSTREAMS = [u.strip().rstrip("/") for u in UPSTREAMS_RAW.split(",") if u.strip()]
else:
    UPSTREAMS = [UPSTREAM_SINGLE.rstrip("/")]
if not UPSTREAMS:
    UPSTREAMS = ["https://api.deepseek.com"]

# 令牌表：令牌[:标签]，逗号分隔
TOKENS = {}
for _part in TOKENS_RAW.split(","):
    _part = _part.strip()
    if not _part:
        continue
    if ":" in _part:
        _tok, _label = _part.split(":", 1)
    else:
        _tok, _label = _part, ""
    _tok = _tok.strip()
    if _tok:
        TOKENS[_tok] = _label.strip() or (_tok[:6] + "...")

_lock = threading.Lock()
_usage = {}
_upstream_index = 0


def _bucket(token):
    now = time.time()
    today = time.strftime("%Y-%m-%d")
    b = _usage.get(token)
    if b is None:
        b = {"minute": 0, "minute_at": now, "day": 0, "day_at": today,
             "requests": 0, "prompt": 0, "completion": 0}
        _usage[token] = b
    if now - b["minute_at"] >= 60:
        b["minute"] = 0
        b["minute_at"] = now
    if b["day_at"] != today:
        b["day"] = 0
        b["day_at"] = today
    return b


def check_limits(token):
    """返回 None 表示放行，否则返回错误说明。"""
    with _lock:
        b = _bucket(token)
        if RATE_PER_MIN > 0 and b["minute"] >= RATE_PER_MIN:
            wait = int(60 - (time.time() - b["minute_at"])) + 1
            return "rate limit exceeded (%d/min), retry in %ds" % (RATE_PER_MIN, wait)
        if DAILY_QUOTA > 0 and b["day"] >= DAILY_QUOTA:
            return "daily quota exceeded (%d/day)" % DAILY_QUOTA
        b["minute"] += 1
        b["day"] += 1
        b["requests"] += 1
    return None


def add_usage(token, prompt, completion):
    if not prompt and not completion:
        return
    with _lock:
        b = _bucket(token)
        try:
            b["prompt"] += int(prompt or 0)
            b["completion"] += int(completion or 0)
        except Exception:
            pass


def next_upstream():
    """轮转取下一个上游 —— 配了多个就能自动容灾。"""
    global _upstream_index
    with _lock:
        u = UPSTREAMS[_upstream_index % len(UPSTREAMS)]
        _upstream_index += 1
        return u


def log_line(text):
    line = "[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), text)
    print(line, flush=True)
    if not LOG_PATH:
        return
    try:
        p = LOG_PATH
        if not os.path.isabs(p):
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)), p)
        d = os.path.dirname(p)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):

    protocol_version = "HTTP/1.1"
    server_version = "ai-proxy/" + VERSION

    def log_message(self, fmt, *args):
        pass

    # ---------- 工具 ----------

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers",
                         "Authorization, Content-Type, Accept, x-api-key, anthropic-version")
        self.send_header("Access-Control-Max-Age", "86400")

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _err(self, code, message, err_type="invalid_request_error"):
        log_line("%s %s -> %d  %s" % (self.command, self.path, code, message))
        self._json(code, {"error": {"message": message, "type": err_type, "code": code}})

    def _token(self):
        """取令牌，兼容 Authorization: Bearer 和 x-api-key 两种写法。"""
        h = self.headers.get("Authorization", "") or ""
        if h.lower().startswith("bearer "):
            return h[7:].strip()
        return (self.headers.get("x-api-key") or "").strip()

    def _auth(self):
        tok = self._token()
        if not tok:
            return None, "missing token (use 'Authorization: Bearer <token>' or 'x-api-key: <token>')"
        if tok not in TOKENS:
            return None, "invalid token"
        return tok, None

    def _read_body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except Exception:
            n = 0
        if n <= 0:
            return None
        try:
            raw = self.rfile.read(n)
        except Exception as e:
            return {"__parse_error__": "cannot read body: %s" % e}
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception as e:
            return {"__parse_error__": str(e)}

    # ---------- OPTIONS ----------

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---------- GET ----------

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/") or "/"

        if path in ("/health", "/"):
            self._json(200, {
                "ok": True,
                "version": VERSION,
                "watermark": WATERMARK,
                "engine_agnostic": True,
                "upstreams": UPSTREAMS,
                "tokens_configured": len(TOKENS),
                "forced_model": FORCE_MODEL or None,
                "rate_per_min": RATE_PER_MIN,
                "daily_quota": DAILY_QUOTA,
                "retry": RETRY,
                "streaming": True,
                "cors": True,
            })
            return

        # 模型列表 —— 很多插件启动时会探测这个，探测失败就整个不工作
        if path in ("/v1/models", "/models"):
            now = int(time.time())
            names = [m.strip() for m in EXPOSE_MODELS.split(",") if m.strip()]
            if FORCE_MODEL and FORCE_MODEL not in names:
                names.insert(0, FORCE_MODEL)
            self._json(200, {
                "object": "list",
                "data": [{"id": n, "object": "model", "created": now, "owned_by": WATERMARK}
                         for n in names],
            })
            return

        if path == "/stats":
            if not ADMIN_TOKEN:
                self._err(503, "AI_ADMIN_TOKEN not configured", "server_error")
                return
            if self._token() != ADMIN_TOKEN:
                self._err(401, "admin token required", "authentication_error")
                return
            with _lock:
                snap = {}
                for t, b in _usage.items():
                    snap[TOKENS.get(t, t)] = {
                        "requests": b["requests"],
                        "this_minute": b["minute"],
                        "today": b["day"],
                        "prompt_tokens": b["prompt"],
                        "completion_tokens": b["completion"],
                    }
            self._json(200, {"version": VERSION, "usage": snap})
            return

        self._err(404, "no such endpoint: %s" % path)

    # ---------- POST ----------

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")

        if path not in ("/v1/chat/completions", "/chat/completions",
                        "/v1/completions", "/completions",
                        "/v1/embeddings", "/embeddings"):
            self._err(404, "no such endpoint: %s" % path)
            return

        if not API_KEY:
            self._err(500, "proxy not configured: AI_API_KEY is empty", "server_error")
            return

        token, err = self._auth()
        if err:
            self._err(401, err, "authentication_error")
            return

        limited = check_limits(token)
        if limited:
            self._err(429, limited, "rate_limit_error")
            return

        payload = self._read_body()
        if payload is None:
            self._err(400, "empty request body")
            return
        if "__parse_error__" in payload:
            self._err(400, "invalid JSON: " + payload["__parse_error__"])
            return

        if FORCE_MODEL:
            payload["model"] = FORCE_MODEL
        if not payload.get("model"):
            first = EXPOSE_MODELS.split(",")[0].strip()
            payload["model"] = first or "deepseek-chat"

        want_stream = bool(payload.get("stream"))

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        tried = []
        last_err = None

        for _attempt in range(max(1, RETRY + 1)):
            upstream = next_upstream()
            url = upstream.rstrip("/") + path

            req = urllib.request.Request(url, data=body, method="POST")
            req.add_header("Content-Type", "application/json; charset=utf-8")
            req.add_header("Authorization", "Bearer " + API_KEY)
            req.add_header("Accept", "text/event-stream" if want_stream else "application/json")
            req.add_header("User-Agent", "ai-proxy/" + VERSION)

            try:
                resp = urllib.request.urlopen(req, timeout=TIMEOUT)
            except urllib.error.HTTPError as e:
                detail = ""
                try:
                    detail = e.read().decode("utf-8", "replace")[:400]
                except Exception:
                    pass
                tried.append("%s -> HTTP %s" % (upstream, e.code))
                last_err = (e.code, detail or ("upstream returned HTTP %s" % e.code))
                # 4xx 是请求本身的问题，换上游也没用
                if 400 <= e.code < 500:
                    break
                log_line("上游失败，重试: %s (HTTP %s)" % (upstream, e.code))
                continue
            except Exception as e:
                tried.append("%s -> %s" % (upstream, e))
                last_err = (502, "cannot reach upstream: %s" % e)
                log_line("上游连不上，重试: %s (%s)" % (upstream, e))
                continue

            if want_stream:
                self._relay_stream(resp, token)
            else:
                self._relay_json(resp, token)
            return

        code, msg = last_err or (502, "all upstreams failed")
        suffix = ("  [tried: %s]" % "; ".join(tried)) if tried else ""
        self._err(code, msg + suffix,
                  "upstream_error" if code >= 500 else "invalid_request_error")

    # ---------- 转发 ----------

    def _relay_json(self, resp, token):
        code = getattr(resp, "status", 200) or 200
        try:
            data = resp.read()
        except Exception as e:
            self._err(502, "failed reading upstream response: %s" % e, "upstream_error")
            return
        try:
            obj = json.loads(data.decode("utf-8"))
            u = obj.get("usage") or {}
            add_usage(token, u.get("prompt_tokens"), u.get("completion_tokens"))
        except Exception:
            pass

        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

    def _relay_stream(self, resp, token):
        """SSE 逐块转发 —— 插件用 stream:true 时不必等全部生成完。"""
        self.send_response(getattr(resp, "status", 200) or 200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self._cors()
        self.end_headers()

        prompt_t = completion_t = 0
        try:
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                # 顺手统计 token 用量
                try:
                    text = chunk.decode("utf-8", "ignore")
                    for line in text.splitlines():
                        if not line.startswith("data:"):
                            continue
                        js = line[5:].strip()
                        if not js or js == "[DONE]":
                            continue
                        o = json.loads(js)
                        u = o.get("usage") or {}
                        if u.get("prompt_tokens"):
                            prompt_t = u["prompt_tokens"]
                        if u.get("completion_tokens"):
                            completion_t = u["completion_tokens"]
                except Exception:
                    pass

                self.wfile.write(chunk)
                self.wfile.flush()
        except Exception as e:
            log_line("流式转发中断: %s" % e)

        add_usage(token, prompt_t, completion_t)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def gen_token():
    return "ai-" + secrets.token_urlsafe(24)


def banner():
    print("")
    print("=" * 70)
    print("  ai-proxy  v%s   —— 通用 AI 接口代理" % VERSION)
    print("  引擎无关 · 任何插件都能接 · MIT License")
    print("=" * 70)
    print("")
    if not API_KEY:
        print("  [x] 还没配置 AI_API_KEY —— 请求会返回 500")
        print("      改 启动接口.bat，或设环境变量 AI_API_KEY")
        print("")
    if not TOKENS:
        print("  [x] 还没配置 AI_TOKENS —— 没有令牌能通过认证")
        print("      先跑  python ai-proxy.py --gen-token  生成一个")
        print("")
    print("  监听       : http://%s:%d" % (HOST, PORT))
    print("  上游       : %s" % ", ".join(UPSTREAMS))
    print("  强制模型   : %s" % (FORCE_MODEL or "（不强制，透传调用方指定的）"))
    print("  对外模型表 : %s" % EXPOSE_MODELS)
    print("  令牌数     : %d" % len(TOKENS))
    print("  限流       : %s 次/分钟    配额: %s 次/天" % (RATE_PER_MIN, DAILY_QUOTA))
    print("  重试       : %d 次（多个上游会自动轮转）" % RETRY)
    print("  流式转发   : 支持（SSE 边生成边收）")
    print("  CORS       : 支持（浏览器 / JS 插件可用）")
    if LOG_PATH:
        print("  请求日志   : %s" % LOG_PATH)
    print("")
    print("  插件里这样填：")
    print("      api_base_url :  http://%s:%d/v1" % (HOST, PORT))
    print("      api_key      :  <你的令牌，不是真 Key>")
    print("")
    print("  自检： curl http://%s:%d/health" % (HOST, PORT))
    print("  模型： curl http://%s:%d/v1/models" % (HOST, PORT))
    print("  用量： curl -H \"Authorization: Bearer %s\" http://%s:%d/stats"
          % (ADMIN_TOKEN or "<AI_ADMIN_TOKEN>", HOST, PORT))
    print("")
    print("  各引擎接入代码见： 接入指南.txt   和   示例代码\\")
    print("")
    print("  按 Ctrl+C 停止")
    print("")


def main():
    argv = sys.argv[1:]

    if "--gen-token" in argv or "-g" in argv:
        t = gen_token()
        print("")
        print("  生成的令牌：")
        print("")
        print("      " + t)
        print("")
        print("  填到 启动接口.bat 的 AI_TOKENS 里，例如：")
        print("      set AI_TOKENS=%s:我的服务器" % t)
        print("")
        print("  插件里 api_key 就填这个令牌。")
        print("")
        return 0

    if "--version" in argv or "-v" in argv:
        print("ai-proxy v%s" % VERSION)
        return 0

    if "--help" in argv or "-h" in argv:
        print("ai-proxy v%s —— 通用 AI 接口代理（引擎无关）" % VERSION)
        print("")
        print("用法: python ai-proxy.py [--gen-token] [--version]")
        print("")
        print("接口: /v1/chat/completions  /v1/models  /health  /stats")
        print("配置: 环境变量 或 同目录 config.json（环境变量优先）")
        print("说明: 见同目录 说明.txt / 接入指南.txt / README.md")
        return 0

    banner()

    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("")
        print("  已停止。")
    finally:
        try:
            srv.server_close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
