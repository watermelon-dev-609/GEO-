@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   GEO生成式搜索优化系统 — 重启脚本
echo ============================================
echo.

echo [1/4] 停止旧的后端进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000.*LISTENING"') do (
    echo   终止 PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo [2/4] 停止旧的前端进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173.*LISTENING"') do (
    echo   终止 PID %%a
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5174.*LISTENING"') do (
    echo   终止 PID %%a
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5175.*LISTENING"') do (
    echo   终止 PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo [3/4] 启动后端（自动重载 — 修改代码即时生效）...
start "GEO Backend" cmd /c "cd backend && python run.py"

echo [4/4] 启动前端（HMR热更新 — 修改代码即时生效）...
start "GEO Frontend" cmd /c "cd frontend && npx vite --port 5173"

echo.
echo ============================================
echo   启动完成!
echo   后端: http://127.0.0.1:8000
echo   前端: http://localhost:5173
echo   API文档: http://127.0.0.1:8000/docs
echo.
echo   关闭此窗口即可，服务在独立窗口中运行
echo   在新窗口中按 Ctrl+C 可停止服务
echo ============================================
pause
