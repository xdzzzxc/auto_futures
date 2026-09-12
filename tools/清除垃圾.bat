@echo off
chcp 65001
echo ==============================
echo  强制结束浏览器相关进程
echo ==============================
taskkill /f /im 360chrome.exe >nul 2>&1
taskkill /f /im chrome.exe >nul 2>&1
taskkill /f /im msedge.exe >nul 2>&1
taskkill /f /im WeChat.exe >nul 2>&1
taskkill /f /im QQ.exe >nul 2>&1
taskkill /f /im Doubao.exe >nul 2>&1

echo.
echo ==============================
echo  清理用户临时文件
echo ==============================
del /f /s /q %temp%\* >nul 2>&1
rd /s /q %temp%\* >nul 2>&1

echo.
echo ==============================
echo  清理系统临时文件
echo ==============================
del /f /s /q C:\Windows\Temp\* >nul 2>&1
rd /s /q C:\Windows\Temp\* >nul 2>&1

echo.
echo ==============================
echo  清理Windows更新缓存
echo ==============================
net stop wuauserv >nul 2>&1
rd /s /q C:\Windows\SoftwareDistribution\Download >nul 2>&1
net start wuauserv >nul 2>&1

echo.
echo ==============================
echo  清理360浏览器全部缓存
echo ==============================
rd /s /q "%localappdata%\360Chrome\Chrome\User Data\Default\Cache" >nul 2>&1
rd /s /q "%localappdata%\360Chrome\Chrome\User Data\Default\Code Cache" >nul 2>&1
rd /s /q "%localappdata%\360Chrome\Chrome\User Data\Default\Cache Storage" >nul 2>&1
rd /s /q "%localappdata%\360Chrome\Chrome\User Data\Default\Service Worker" >nul 2>&1

echo.
echo ==============================
echo  清理Chrome浏览器缓存
echo ==============================
rd /s /q "%localappdata%\Google\Chrome\User Data\Default\Cache" >nul 2>&1

echo.
echo ==============================
echo  清理Edge浏览器缓存
echo ==============================
rd /s /q "%localappdata%\Microsoft\Edge\User Data\Default\Cache" >nul 2>&1

echo.
echo ==============================
echo  清理NVIDIA缓存
echo ==============================
rd /s /q "%localappdata%\NVIDIA\Cache" >nul 2>&1

echo.
echo ==============================
echo  清理豆包缓存
echo ==============================
rd /s /q "%localappdata%\Doubao" >nul 2>&1
rd /s /q "%localappdata%\ByteDance\Doubao" >nul 2>&1

echo.
echo ==============================
echo  清理系统日志
echo ==============================
rd /s /q C:\Windows\Logs\* >nul 2>&1

echo.
echo ✅ 全部垃圾清理完成！
echo 按任意键退出...
pause >nul