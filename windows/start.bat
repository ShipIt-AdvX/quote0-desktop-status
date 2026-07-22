@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   Quote/0 Windows 一键启动
echo   配置页: http://localhost:7891
echo ========================================

where python >nul 2>&1
if errorlevel 1 (
  echo [错误] 未找到 python，请先安装 Python 3.11+ 并勾选 Add to PATH
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] 创建虚拟环境...
  python -m venv .venv
  if errorlevel 1 (
    echo [错误] 创建 venv 失败
    pause
    exit /b 1
  )
)

echo [2/3] 安装依赖...
".venv\Scripts\python.exe" -m pip install -q -U pip
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 (
  echo [错误] 依赖安装失败
  pause
  exit /b 1
)

echo [3/3] 启动服务...
echo.
echo 浏览器将打开 http://localhost:7891
echo 关闭本窗口即停止服务
echo.
".venv\Scripts\python.exe" run.py
pause
