@echo off
chcp 936 >nul
setlocal EnableExtensions
title 显示器切换 - 卸载器
set "APPDIR=%~dp0"
if "%APPDIR:~-1%"=="\" set "APPDIR=%APPDIR:~0,-1%"

echo ==================================================
echo   显示器切换 - 卸载器
echo ==================================================
echo.
echo  将要执行：
echo    1. 结束正在运行的「显示器切换.exe」
echo    2. 删除开机自启项 HKCU ... Run\MonitorSwitch
echo    3. 删除热键配置 HKCU\Software\MonitorSwitch
echo    4. 清理临时日志 %%TEMP%%\MonitorSwitch
echo    5. 打开本文件夹，由你把整个文件夹拖进回收站
echo.
echo  最后一步为什么要你手动拖：
echo    · 脚本删不掉"自己所在的文件夹"，Windows 会锁住正在运行的文件；
echo    · 用脚本硬删会被杀毒软件判成木马（火绒实测会直接删除脚本）；
echo    · 拖进回收站最干净，随时能还原。
echo.
set "ANS="
set /p "ANS=  继续卸载？[Y=继续 / N=取消]: "
if /i not "%ANS%"=="Y" goto :cancel

echo.
echo [1/4] 结束进程...
taskkill /f /t /im "显示器切换.exe" >nul 2>&1
if errorlevel 1 (echo        - 没有在运行，跳过) else (echo        - 已结束)

echo [2/4] 删除开机自启项...
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v MonitorSwitch /f >nul 2>&1
if errorlevel 1 (echo        - 没有该启动项，跳过) else (echo        - 已删除)

echo [3/4] 删除热键配置...
reg delete "HKCU\Software\MonitorSwitch" /f >nul 2>&1
if errorlevel 1 (echo        - 没有自定义热键，跳过) else (echo        - 已删除)

echo [4/4] 清理临时日志...
if exist "%%TEMP%%\MonitorSwitch" (
  rmdir /s /q "%%TEMP%%\MonitorSwitch" 2>nul
  echo        - 已清理
) else (
  echo        - 无残留
)

echo.
echo --------------------------------------------------
echo  只剩最后一步：把这个文件夹整体拖进回收站
echo.
echo  文件夹：%APPDIR%
echo  资源管理器已打开并选中它，按 Delete 即可。
echo.
echo  源码不会丢：github.com/Nuoili/monitor-switch-win
echo --------------------------------------------------
start "" explorer /select,"%APPDIR%"
echo.
pause
exit /b 0

:cancel
echo.
echo  已取消，未做任何修改。
ping -n 3 127.0.0.1 >nul
exit /b 0
