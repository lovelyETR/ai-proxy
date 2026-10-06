@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   生成一个随机令牌（复制到 启动接口.bat 的 AI_TOKENS 里）：
echo.
python ai-proxy.py --gen-token
echo.
pause