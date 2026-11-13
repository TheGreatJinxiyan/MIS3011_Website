@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   ResumeCube 简历魔方 - 启动器
echo ============================================================
echo.
where py >nul 2>&1
if errorlevel 1 goto TRYPYTHON
echo [检查] 本地服务是否已在运行...
py -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8787/health',timeout=2).status==200 else 1)" >nul 2>&1
if not errorlevel 1 goto OPEN
echo [启动] 正在启动本地服务，请保持本窗口开启...
echo    页面地址 : http://127.0.0.1:8787/
echo    健康检查 : http://127.0.0.1:8787/health
echo    停止服务 : 在本窗口按 Ctrl + C
echo.
py proxy.py
echo.
echo 服务已停止。若上方出现报错，请截图发给开发者。
pause
exit /b

:OPEN
echo [完成] 服务已在运行，正在打开页面...
start "" "http://127.0.0.1:8787/"
echo    页面地址：http://127.0.0.1:8787/
echo    若浏览器没弹出，请手动把上面这行地址复制到地址栏。
echo    本窗口可以直接关掉，服务仍在后台运行。
echo.
pause
exit /b

:TRYPYTHON
where python >nul 2>&1
if errorlevel 1 goto NOPY
echo [启动] 使用 python 命令启动，请保持本窗口开启...
echo    页面地址：http://127.0.0.1:8787/
python proxy.py
pause
exit /b

:NOPY
echo [错误] 没有检测到 Python 3（py / python 命令都不可用）。
echo.
echo 请安装 Python：https://www.python.org/downloads/
echo 安装时勾选 "Add Python to PATH"，装完重新双击本文件。
echo 也可以只上传 index.html 到 GitHub Pages 静态查看（AI 需另配 app- 密钥）。
echo.
pause
exit /b
