RTL-SDR 命令行工具（随程序分发）
================================

本目录内的文件来自 osmocom 的 rtl-sdr 项目（Windows 预编译构建），
用于让 CR-LBJ-Receiver 做到“插上 RTL-SDR 即可使用”，无需用户另外安装工具包。

文件说明
--------
rtl_tcp.exe      RTL-SDR TCP 服务端，程序启动接收时自动拉起
rtl_test.exe     设备检测工具，配置面板「检测设备」调用
rtlsdr.dll       RTL-SDR 驱动封装库（USB 通信）
msvcr100.dll     Visual C++ 2010 运行库（rtl_tcp 依赖）
pthreadVC2.dll   POSIX 线程库（rtl_tcp 依赖）

来源与许可
----------
- rtl-sdr: https://github.com/osmocom/rtl-sdr  (GPLv2)
- 预编译 Windows 版: https://ftp.osmocom.org/binaries/windows/rtl-sdr/
- 本程序按 GPLv3 分发，与上述组件兼容；各组件的著作权归其原作者。

使用方式
--------
程序按以下顺序查找 rtl_tcp.exe，找到即用：
  1. 配置里手动指定的路径
  2. 程序目录及其上级（最多 4 层）、每层的 tools/rtl 与 RTL_TCP_Server 子目录
  3. 打包运行时的 _MEIPASS/rtl（即本目录被打进 EXE 后的位置）
  4. 系统 PATH

Windows 首次使用仍需用 Zadig 给 RTL2832U 安装 WinUSB 驱动（这是驱动，不能随包分发）。
