@echo off
cd /d "%~dp0"
title mihomo 代理 - 一键关闭（仅电脑端）
echo 正在停止 mihomo 进程...
taskkill /F /IM mihomo.exe >nul 2>&1

echo 正在清除 Windows 系统代理（用 Python，绕开 PowerShell 禁脚本）...
set "PY=C:\Users\36411\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if not exist "%PY%" ( for %%P in (py python python3) do ( %%~P --version >nul 2>&1 && set "PY=%%~P" ) )
"%PY%" set_proxy.py off

echo.
echo 已关闭电脑端代理，系统恢复直连。
echo （手机订阅服务 9099 保持运行，手机仍可继续用）
echo （日志保留在 mihomo.log / mihomo.err）
pause
