@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==========================================================
echo  CR-LBJ-Receiver 代码签名证书安装
echo ==========================================================
echo.
echo 本脚本把自签名证书导入【当前用户】的
echo   - 受信任的根证书颁发机构
echo   - 受信任的发布者
echo 之后本机即认可 CR-LBJ-Receiver.exe 的签名，
echo SmartScreen 的「发行者未知」会变为「刘纪彤（BG2GBQ）」。
echo.
echo 如果弹出「安全警告」对话框，请点【是】。
echo 撤销方法：certutil -user -delstore Root <指纹>
echo.
pause
echo.
echo [1/2] 导入受信任的根证书颁发机构...
certutil -user -addstore Root "%~dp0cr-lbj-codesign.cer"
echo.
echo [2/2] 导入受信任的发布者...
certutil -user -addstore TrustedPublisher "%~dp0cr-lbj-codesign.cer"
echo.
echo 完成。现在重新双击 CR-LBJ-Receiver-desktop-v3.2.10-signed.exe 试试。
echo 若仍提示「无法识别的应用」，点【更多信息】->【仍要运行】
echo （这是 SmartScreen 云声誉机制，自签名无法完全消除，需购买 CA 证书）。
pause