@echo off
cd /d "%~dp0"
:: 双击场景下，用 cmd /k 重新打开自身，确保结果窗口不会一闪而过
if "%~1"=="" (
    start "" cmd /c "%~f0" RUN
    exit /b
)

:MAIN
cd /d "%~dp0"
title mihomo 代理连通测试
echo ============================================================
echo         mihomo 代理连通性测试（Google / 节点概况）
echo ============================================================
echo 提示：本窗口会保持打开，请等待测试结束后查看结果，再关闭。
echo.

if not exist mihomo.exe (
    echo [!] 未检测到 mihomo.exe，请先双击 start.bat 开启代理。
    goto :END
)

:: mihomo 没在跑就先帮你启动（隐藏窗口）
tasklist /FI "IMAGENAME eq mihomo.exe" | find /I "mihomo.exe" >nul
if errorlevel 1 (
    echo [*] 检测到 mihomo 未运行，正在自动启动（后台）...
    powershell -NoProfile -Command "Start-Process -FilePath '.\mihomo.exe' -ArgumentList '-d','.','-f','config.yaml' -WindowStyle Hidden -RedirectStandardOutput 'mihomo.log' -RedirectStandardError 'mihomo.err'"
    echo     等待 6 秒让内核就绪...
    timeout /t 6 >nul
    tasklist /FI "IMAGENAME eq mihomo.exe" | find /I "mihomo.exe" >nul
    if errorlevel 1 (
        echo [!] mihomo 启动失败，请查看同目录的 mihomo.err / mihomo.log
        goto :END
    )
    echo [+] mihomo 已启动
)

if exist proxy_port.txt ( set /p PROXY_PORT=<proxy_port.txt ) else ( set PROXY_PORT=7890 )

echo.
echo [1/2] 通过 127.0.0.1:%PROXY_PORT% 访问 www.google.com ...
curl -sS -x http://127.0.0.1:%PROXY_PORT% --max-time 20 -o nul -w "      [HTTP 状态码] %%{http_code}\n" https://www.google.com
if errorlevel 1 echo      [失败] curl 测试未通过（节点可能刚过期，重跑 start.bat 刷新）

echo.
echo [2/2] 节点概况（AUTO 组节点数 / 当前选中）...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $h=@{Authorization='Bearer mihomo-desktop'}; $d=Invoke-RestMethod -Uri 'http://127.0.0.1:9090/proxies/AUTO' -Headers $h; Write-Host ('     AUTO 组共 ' + $d.all.Count + ' 个节点，当前选中: ' + $d.now) } catch { Write-Host ('     [!] 读取控制器失败(密钥不对或 mihomo 未完全启动): ' + $_.Exception.Message) }"

echo.
echo 说明：
echo   - 若 [1/2] 显示 HTTP 200，恭喜，代理已通，浏览器/软件已可上外网。
echo   - 若 [1/2] 失败但节点数正常，多半是免费节点刚过期，重跑 start.bat 刷新即可。
echo   - 若节点数=0 或读取控制器失败，运行 stop.bat 后再 start.bat 一次。
echo   - 想让整个电脑都走代理，请双击 start.bat（它会帮你设好系统代理 + 控制面板）。

:END
echo.
echo ============================================================
echo   测试结束。按任意键关闭本窗口。
echo ============================================================
pause
