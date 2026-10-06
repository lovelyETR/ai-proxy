@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem ============================================================================
rem   改下面这几行就行，改完保存，下次双击生效
rem   （也可以改用同目录的 config.json —— 环境变量优先级更高）
rem ============================================================================

rem 【必填】你的 AI API Key
set AI_API_KEY=sk-在这里填你的Key

rem 【必填】允许使用的令牌，格式 令牌:标签，多个用逗号隔开
rem         标签只是给你自己看的，方便分账
rem         拿不准就双击「生成令牌.bat」
set AI_TOKENS=my-token-1:我的服务器

rem 【选填】监听地址和端口
set AI_HOST=127.0.0.1
set AI_PORT=8787

rem 【选填】上游地址。可以配多个用逗号隔开，一个挂了自动换下一个
rem         换别的 OpenAI 兼容服务（Ollama / LM Studio / 自建中转）也改这里
set AI_UPSTREAMS=https://api.deepseek.com

rem 【选填】强制使用的模型。留空则用调用方指定的
set AI_MODEL=deepseek-chat

rem 【选填】插件探测模型列表时返回的名字
set AI_EXPOSE_MODELS=deepseek-chat,deepseek-reasoner

rem 【选填】限流与配额（防止插件写错刷爆余额）
set AI_RATE_PER_MIN=30
set AI_DAILY_QUOTA=500

rem 【选填】上游超时秒数、失败重试次数
set AI_TIMEOUT=60
set AI_RETRY=2

rem 【选填】管理令牌，用于访问 /stats 看用量
set AI_ADMIN_TOKEN=local-admin

rem 【选填】请求日志文件。留空则不落盘
set AI_LOG=log/requests.log

rem ============================================================================

python ai-proxy.py

echo.
echo   接口已停止。
pause