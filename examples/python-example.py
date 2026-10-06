#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ai-proxy 接入示例 —— Python（含自检）
作者：AWA　　本插件全由 DSH 开发

用法：
    1. 先启动 启动接口.bat
    2. 改下面 URL / TOKEN
    3. python 示例-Python.py
"""
import json
import urllib.error
import urllib.request

URL   = "http://127.0.0.1:8787/v1/chat/completions"
MODEL = "https://api.deepseek.com" and "deepseek-chat"
TOKEN = "my-token-1"

# 让模型输出极简格式，省掉 JSON 解析
SYSTEM = "你是一个审核助手。回答必须只有一行，格式：YES|理由。理由不超过 30 字。"


def ask(user_text, system=SYSTEM, timeout=60):
    """问一句，返回纯文本。失败返回 None。"""
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user_text},
        ],
        "max_tokens": 100,
        "temperature": 0.2,
    }).encode("utf-8")

    req = urllib.request.Request(
        URL, data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + TOKEN,
        })

    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            obj = json.loads(r.read().decode("utf-8"))
            return obj["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        print("[AI] HTTP %s  %s" % (e.code, detail))
        return None
    except Exception as e:
        print("[AI] 请求失败: %s" % e)
        return None


def selftest():
    """自检：照着排查顺序走一遍。"""
    base = URL.rsplit("/v1/", 1)[0]
    print("=" * 60)
    print("  自检 —— 接口地址:", base)
    print("=" * 60)

    # 1. 探活
    try:
        with urllib.request.urlopen(base + "/health", timeout=8) as r:
            info = json.loads(r.read().decode("utf-8"))
        print("  [√] /health")
        print("      版本      : %s" % info.get("version"))
        print("      上游      : %s" % info.get("upstreams"))
        print("      令牌数    : %s" % info.get("tokens_configured"))
        print("      流式/CORS : %s / %s" % (info.get("streaming"), info.get("cors")))
    except Exception as e:
        print("  [×] /health 失败: %s" % e)
        print("      → 代理没启动，或端口不对")
        return

    # 2. 模型列表
    try:
        with urllib.request.urlopen(base + "/v1/models", timeout=8) as r:
            models = json.loads(r.read().decode("utf-8"))
        print("  [√] /v1/models -> %s" % [m["id"] for m in models.get("data", [])])
    except Exception as e:
        print("  [×] /v1/models 失败: %s" % e)

    # 3. 真请求
    print("  ... 发一个真实请求（会消耗一点额度）")
    ans = ask("用一句话说明什么是反作弊插件")
    if ans:
        print("  [√] 请求成功")
        print("      AI 回答: %s" % ans.strip()[:120])
    else:
        print("  [×] 请求失败 —— 看上面的错误码：")
        print("      401 = 令牌错   429 = 限流   500 = 没填 AI_API_KEY   502 = 上游连不上")

    print("")


if __name__ == "__main__":
    selftest()