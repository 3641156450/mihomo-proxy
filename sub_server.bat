@echo off
cd /d "%~dp0"
title mihomo 订阅服务 (手机拉取用)
echo 正在放行防火墙端口 9099...
netsh advfirewall firewall delete rule name="mihomo-sub-9099" >nul 2>&1
netsh advfirewall firewall add rule name="mihomo-sub-9099" dir=in action=allow protocol=TCP localport=9099 >nul 2>&1
if %errorlevel% neq 0 (
    echo 需要管理员权限，正在弹出授权窗口...
    powershell -Command "Start-Process netsh -ArgumentList 'advfirewall firewall add rule name=\"mihomo-sub-9099\" dir=in action=allow protocol=TCP localport=9099' -Verb RunAs" >nul 2>&1
)

echo 正在启动订阅服务 (Python 版，常驻 9099)...
set "PY=%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if not exist "%PY%" ( for %%P in (py python python3) do ( %%~P --version >nul 2>&1 && set "PY=%%~P" ) )
start "" /min "%PY%" sub_server.py
echo 订阅服务已启动，手机填 http://<你的电脑主机名>:9099/sub.yaml （须与电脑同一 WiFi；换网络以启动时提示的地址为准）
pause
