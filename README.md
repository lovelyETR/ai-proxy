# ai-proxy

**给任何需要调用 AI 的插件提供统一入口。真实 API Key 只留在本机一处。**

OpenAI 兼容 · 零第三方依赖（纯 Python 标准库）· MIT License

作者：**AWA**　　本项目全由 **DSH**（DeepSeek Harness）开发

---

## 引擎无关

它是标准 HTTP 服务，说的是 OpenAI 兼容格式。
所以「适配某个引擎」**不需要为那个引擎改任何代码** ——
只要那个引擎的插件**会发 HTTP 请求**就能接。

已覆盖（每个都有可直接复制的代码，见 [`接入指南.txt`](接入指南.txt) 和 [`examples/`](examples)）：

| 引擎 / 框架 | 语言 | 需要额外东西吗 |
|---|---|---|
| Unity / BepInEx | C# | 不需要 |
| Unity / MelonLoader | C# | 不需要 |
| RimWorld / 单机模组 | C# | 不需要 |
| 起源引擎 / SourceMod | SourcePawn | SourceMod 1.11+ 或 SteamWorks |
| 起源引擎 / Lua | Lua | luasocket |
| GMod | Lua | 不需要（自带 `http`）|
| FiveM / RedM | Lua | 不需要（自带 `PerformHttpRequest`）|
| 虚幻引擎 | C++ | 不需要（HTTP 模块）|
| 虚幻引擎 / 蓝图 | 蓝图 | VaRest 等插件 |
| 寒霜 / Venice Unleashed | Python | 不需要 |
| 寒霜 / 其他 | RCON + 外部程序 | 需要写外部程序 |
| Minecraft / 模组 | Java 11+ | 不需要 |
| Minecraft / 服务端插件 | Java 11+ | 不需要 |
| Godot | GDScript / C# | 不需要 |
| CryEngine | Lua | 看版本，可能要外部程序 |
| GameMaker | GML | HTTP 扩展 |
| GoldSource / AMX | Pawn | curl 或 sockets 模块 |
| Web / Node | JavaScript | 不需要（已开 CORS）|

---

## 它解决什么问题

直接让每个插件各存一份 API Key 有三个麻烦：

| 问题 | 用代理之后 |
|---|---|
| Key 散落各处，分享配置就泄露 | Key 只在代理这一处，插件里全是**可吊销的令牌** |
| 插件写错逻辑刷爆余额 | 统一**限流 + 每日配额** |
| 换 Key / 换模型要挨个改插件 | 只改代理，**所有插件自动生效** |
| 不知道谁用了多少 | `/stats` 里**按令牌分账** |

---

## 快速开始

```bash
# 1. 设置真 Key
set AI_API_KEY=sk-你的Key

# 2. 生成一个令牌给插件用
python ai-proxy.py --gen-token

# 3. 设置允许的令牌
set AI_TOKENS=<上一步生成的令牌>:我的服务器

# 4. 启动
python ai-proxy.py
```

Windows 上双击 `启动接口.bat` 更省事 —— 顶部就是配置区。

也可以用配置文件：把 `config.example.json` 复制成 `config.json` 再改
（环境变量优先级更高）。

---

## 让插件接过来

任何支持自定义 API 地址的插件，改两个字段就行：

```yaml
api_base_url: 'http://127.0.0.1:8787/v1'
api_key: 'my-token-1'          # 令牌，不是真 Key
```

因为它就是 OpenAI 兼容接口，所以**不需要改插件代码**。

### 配合 AWA-DeepSeek-AntiCheat 用

```yaml
# 原来（直连官方，配置里存真 Key）
api_base_url: 'https://api.deepseek.com'
api_key: 'sk-你的真Key'

# 改成（走代理，配置里只有令牌）
api_base_url: 'http://127.0.0.1:8787/v1'
api_key: 'my-token-1'
```

这样就算把配置发给别人，泄露的也只是一个可以随时删掉的令牌。

---

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/v1/chat/completions` | OpenAI 兼容，**支持真流式（SSE 逐块转发）** |
| POST | `/v1/completions` | 老式补全接口 |
| POST | `/v1/embeddings` | 向量接口 |
| GET | `/v1/models` | 模型列表（很多插件启动时会探测）|
| GET | `/health` | 探活，不需要令牌 |
| GET | `/stats` | 用量统计，需要管理令牌 |
| OPTIONS | `*` | CORS 预检 |

**鉴权**兼容两种写法：`Authorization: Bearer <token>` 和 `x-api-key: <token>`。

---

## 配置项

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `AI_API_KEY` | — | 上游 API Key（**必填**）|
| `AI_TOKENS` | — | 允许的令牌，`令牌:标签` 逗号分隔（**必填**）|
| `AI_HOST` | `127.0.0.1` | 监听地址 |
| `AI_PORT` | `8787` | 监听端口 |
| `AI_UPSTREAMS` | — | 上游地址，**可配多个逗号分隔，一个挂了自动换** |
| `AI_UPSTREAM` | `https://api.deepseek.com` | 单个上游地址 |
| `AI_MODEL` | 空 | 强制模型，留空则透传调用方指定的 |
| `AI_EXPOSE_MODELS` | `deepseek-chat,deepseek-reasoner` | `/v1/models` 返回的名字 |
| `AI_RATE_PER_MIN` | `30` | 每令牌每分钟请求上限 |
| `AI_DAILY_QUOTA` | `500` | 每令牌每日请求上限 |
| `AI_TIMEOUT` | `60` | 上游超时秒数 |
| `AI_RETRY` | `2` | 失败重试次数 |
| `AI_ADMIN_TOKEN` | 空 | 访问 `/stats` 用 |
| `AI_LOG` | 空 | 请求日志文件路径 |

---

## 换别的 AI 服务

只要对方是 OpenAI 兼容接口，改两个变量就行：

```bat
rem 本地 Ollama
set AI_UPSTREAMS=http://127.0.0.1:11434/v1
set AI_MODEL=qwen2.5:7b-instruct

rem LM Studio
set AI_UPSTREAMS=http://127.0.0.1:1234/v1
set AI_MODEL=<你在 LM Studio 里加载的模型名>
```

---

## 排查顺序

照这个走，99% 的问题都能定位：

```bash
# 1. 接口活着吗
curl http://127.0.0.1:8787/health

# 2. 模型列表能拿到吗（插件启动报错八成是这个不通）
curl http://127.0.0.1:8787/v1/models

# 3. 带令牌能请求通吗
curl -X POST http://127.0.0.1:8787/v1/chat/completions \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer my-token-1" \
     -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"hi"}],"max_tokens":10}'

# 4. 看用量（请求数是 0 = 插件根本没发出来）
curl -H "Authorization: Bearer <AI_ADMIN_TOKEN>" http://127.0.0.1:8787/stats
```

**错误码含义**：`401` 令牌错 · `429` 限流 · `500` 没填 `AI_API_KEY` · `502` 上游连不上

`examples/python-example.py` 自带这个排查流程，直接跑就行。

---

## 安全性

- `AI_HOST` 默认 `127.0.0.1`，**只有本机能连**。除非确实要跨机器用，不要改成 `0.0.0.0`
- 真 Key 只存在于代理进程内存中，插件拿到的只有令牌
- 某个令牌泄露了，从 `AI_TOKENS` 里删掉它就行，不用换 Key
- **不要提交 `config.json`** —— `.gitignore` 已经排除它，配置模板是 `config.example.json`

---

## 依赖

**零第三方依赖** —— 只用 Python 标准库。Python 3.8+ 即可。

---

## License

[MIT](LICENSE) —— 自由使用、修改、再分发，保留版权声明即可。

---

作者：**AWA**　　本项目全由 **DSH**（DeepSeek Harness）开发
