@echo off
cd /d "%~dp0"
:: 双击场景下重开自身，保持结果窗口不闪退
if "%~1"=="" ( start "" cmd /c "%~f0" RUN & exit /b )

title mihomo 代理 - 一键开启（自动选最优节点）
echo ============================================================
echo   mihomo 代理  一键开启
echo   自动剔除大陆/只留活节点，AUTO 组每 5 分钟自动选延迟最低节点
echo ============================================================
echo.

:: ---------- 1) 定位 Python（优先用本机配好的 venv）----------
set "PY="
if exist "C:\Users\36411\.workbuddy\binaries\python\envs\default\Scripts\python.exe" (
    set "PY=C:\Users\36411\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
) else (
    for %%P in (py python python3) do ( %%~P --version >nul 2>&1 && ( set "PY=%%~P" & goto :havepy ) )
)
:havepy
if not defined PY (
    echo [!] 未找到 Python，无法生成节点。请安装 Python 3 或放入现成 config.yaml。
    pause & exit /b 1
)

:: ---------- 2) 刷新节点：抓源->剔大陆/剔法国->TCP实测活->截延迟前60->默认AUTO选最优 ----------
echo [1/4] 正在刷新节点并剪枝（约 30~60 秒，请稍候）...
"%PY%" build_live.py
if not exist config.yaml (
    echo [!] 节点生成失败，请检查网络后重跑。
    pause & exit /b 1
)

:: ---------- 3) 拉起 mihomo（最小化窗口，日志写 mihomo.log）----------
set /p PROXY_PORT=<proxy_port.txt
echo [2/4] 启动 mihomo（端口 %PROXY_PORT%）...
if exist mihomo.exe (
    taskkill /F /IM mihomo.exe >nul 2>&1
    start "" /min mihomo.exe -d . -f config.yaml
) else (
    echo [!] 缺少 mihomo.exe，无法启动。请先放入 mihomo.exe。
    pause & exit /b 1
)
timeout /t 3 >nul

:: ---------- 4) 设置 Windows 系统代理（用 Python 改注册表，绕开 PowerShell 禁脚本）----------
echo [3/4] 设置系统代理 127.0.0.1:%PROXY_PORT%...
"%PY%" set_proxy.py on %PROXY_PORT%

:: ---------- 5) 拉起手机订阅服务（Python 版，常驻 9099）----------
echo [4/4] 启动手机订阅服务（9099）...
start "" /min "%PY%" sub_server.py

echo.
echo ============================================================
echo   已开启！AUTO 组会每 5 分钟自动测速，选延迟最低的节点
echo   代理地址 : 127.0.0.1:%PROXY_PORT%
echo   换节点   : 双击 dashboard.url 打开面板
echo   关闭代理 : 运行 stop.bat
echo   测试谷歌 : 运行 test-google.bat
echo   手机订阅 : 手机填 http://HP-ABC:9099/sub.yaml （手机须与电脑同一 WiFi；若换了网络，以 sub_server 启动时提示的当前地址为准）
echo ============================================================
start "" dashboard.url
echo.
echo 本窗口保持打开，查看信息后按任意键关闭。
pause
