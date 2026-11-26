# USB 直连与设备自适应连接

> 适用版本：**v3.2.7**（2026-11-26） ｜ 适用端：桌面 ｜ 最后更新：2026-11-26
>
> 本文说明桌面端 **USB 直连 RTL-SDR** 的实现方式、按 tuner 型号自适应推荐参数的依据与验证记录。
> 结论与方案先行，实施记录与取舍见第 6 节；插入设备后仍需补做的实测项见第 8 节。
> 文中 `cr_lbj/…` 均指桌面端 `desktop/cr_lbj/…`。

## 目录

1. [结论先行](#1-结论先行)
2. [原理与现状](#2-原理与现状)
3. [参考项目与要点](#3-参考项目与要点)
4. [本机验证记录（2026-11-25，全部实测）](#4-本机验证记录2026-11-25全部实测)
5. [有依据的推荐参数（自动推荐的填充值）](#5-有依据的推荐参数自动推荐的填充值)
6. [实现与取舍（v2.6 起）](#6-实现与取舍v26-起)
7. [风险](#7-风险)
8. [待实测（插入 RTL-SDR 后按顺序做）](#8-待实测插入-rtl-sdr-后按顺序做)

---

## 1. 结论先行

1. **USB 不必经过 TCP。** RTL-TCP 只是 librtlsdr 的网络前端；librtlsdr 本身
   就是通过 libusb 直接访问 RTL2832U 的。程序随包的 `rtlsdr.dll` 已经是完整
   的直连库，只是现在被 `rtl_tcp.exe` 包了一层再用。
2. **随包 dll 可以被 Python 直接调用，零新增依赖。** 已实测：64 位 Python 用
   ctypes 成功加载 `tools/rtl/rtlsdr.dll`，所需导出函数齐全，libusb 已静态
   链接（无需额外的 libusb-1.0.dll）。
3. **pyrtlsdr 两条路都走不通，放弃它。** 0.5.1 需要 dll 里没有的
   `rtlsdr_set_dithering`；0.2.92 依赖 Python 3.14 已移除的 `pkg_resources`。
   自己用 ctypes 写一个约 150 行的薄绑定（`RtlSdrDirectSource`）即可。
4. **「自动推荐连接设置」有充分依据可做**：老版本本地配置、Sdr-Is-Fun 系列
   与 LBJReceiver 的实测参数高度一致（960 kS/s、手动增益、禁 AGC、块 65536），
   并可通过 `rtlsdr_get_tuner_type()` 识别 tuner 型号给出针对性建议。

## 2. 原理与现状

`sourceType` 现有三种：`rtl_tcp`（远程/本地 rtl_tcp）、`owrx`（OpenWebRX 兼容）、
`rtl_usb`（本机 USB）。其中 `RtlUsbSource` 的实现是：**自动拉起 rtl_tcp.exe，
再连 127.0.0.1 的 TCP**——即 USB 之路现在确实绕了一层本地 TCP 和一个子进程
（进程生命周期管理、端口占用检测都是它的额外复杂度）。

## 3. 参考项目与要点

| 项目 | 与本调研的关系 |
|---|---|
| `Sdr-Is-Fun/RTL_SDR_LBJ_RECEIVER`（及 zhengruiw02 原仓库） | 本项目 DSP 链的同源参考：固定 960 kS/s IQ → 软件 DDC → 信道滤波 → FM 鉴频 → DPLL → BCH。证明 960 kS/s 是 LBJ 的验证过的甜点采样率 |
| `Scorpio-yzy/LBJReceiver`（Android，GPL-3.0） | **已实现 USB 直连**（SDR Touch 驱动），解码核心即 Sdr-Is-Fun 那份。实测经验：手动增益默认 **19.7 dB、不提供 AGC（实测后删掉）**；960 kS/s；块 65536；扫描时才升 2.4 MS/s |
| `undef-i/LBJ_Console`（GPL-3.0） | 同类软件，同时支持 **USB 直连 RTL2832U/ADALM-PLUTO** 与 RTL-TCP 两种模式，证明双模式并存是成熟做法 |
| `KejPi/rtlsdr`（librtlsdr 改进版） | 关键坑：**osmocom 版 librtlsdr 在 Windows 慢 PC 上用 LibUSB 会丢块**（WinUSB RAW_IO 问题），KejPi 版直接调 WinUSB 解决；若直连后出现丢块，升级此版 dll 是首选方案 |
| `rtlsdrblog/rtl-sdr-blog`（librtlsdr Blog fork） | **RTL-SDR Blog V4（R828D tuner）必须用 Blog fork 的 librtlsdr**，osmocom 旧版对 V4 支持不完整 → 设备自适应推荐必须区分 tuner 型号 |
| `pyrtlsdr` | ctypes 封装。0.5.1 需要 `rtlsdr_set_dithering`（随包老 dll 没有）；0.2.92 需要 `pkg_resources`（Py3.14 已移除）。均不适用，且它只是十几个函数的薄封装，自己写更干净 |
| 老版本配置（git `de283c5` / `53e536b`） | 本地 USB/TCP 数据源的历史默认值（见第 5 节） |

## 4. 本机验证记录（2026-11-25，全部实测）

| 检查项 | 结果 |
|---|---|
| Python 3.14.5 位数 | 64 bit |
| `tools/rtl/rtlsdr.dll` PE Machine | **0x8664（x64，与 Python 匹配）** |
| rtl_tcp.exe / rtl_test.exe | 同为 x64 |
| dll 内 `libusb-1.0.dll` 按名导入 | **无**（"libusb" 字符串 40 处 → libusb 已静态链接，无需额外 DLL） |
| ctypes 加载 rtlsdr.dll | 成功 |
| 所需导出函数（open / set_sample_rate / set_center_freq / set_freq_correction / set_tuner_gain(_mode) / set_agc_mode / reset_buffer / read_sync / read_async / cancel_async / close / get_tuner_type / get_index_by_serial / set_bias_tee） | **全部存在** |
| `rtlsdr_set_dithering` | 缺（正是 pyrtlsdr 0.5.1 不可用的原因） |
| ctypes 调用链（open → 配置 → read_sync → close） | 调用链正常；`rtlsdr_open(0)` 返回 -1 |
| 交叉确认 | `rtlsdr_get_device_count()=0`、`rtl_test -t` 报 "No supported devices found" → **此刻棒子未插**，open 失败是设备不在，不是代码问题 |

> 待验证缺口：实际开流后的丢块率 / CPU 占用 / 与 RTL-TCP 桥的延迟对比，
> 需在设备插上的机器上跑一次实测（脚本已具备，只是 `open` 那一步）。

## 5. 有依据的推荐参数（自动推荐的填充值）

统一基线（三个来源互相印证）：**960 kS/s、块 65536、手动增益、禁 AGC**。

| 参数 | 推荐值 | 依据 |
|---|---|---|
| 采样率 | 960 kS/s | sdr-is-fun 固定值；老版本本地配置；LBJReceiver 实测 |
| 块大小 | 65536 采样 | 老版本配置 + LBJReceiver，一致 |
| 增益 | R820T/R828D：15.7 ~ 19.7 dB 手动 | 老版本 15.7；LBJReceiver 实测 19.7 并明确弃用 AGC |
| AGC | 关 | 同上 |
| ppm | 沿用用户现值（默认 1） | 每支棒不同，检测页可加「校准向导」后续再做 |
| dcOffsetHz | 本机 USB/TCP 沿用 50000 Hz | 老版本本地数据源均为 50000 |
| 频率 | 821.2375 MHz | 老版本默认（LBJ 下行） |

**按 tuner 型号的差异提示（检测到后自动给出）：**
- `R828D` → 很可能是 RTL-SDR Blog **V4**：提示「V4 需要 Blog fork 的 librtlsdr；
  当前 dll 若为 osmocom 旧版，建议更换 dll 或继续用 RTL-TCP 桥」。
- `R820T` → 普通 V3/杂牌棒：直接给上表推荐值。
- `FC0013`（常见低价棒）：可用，增益表不同，建议先「自动增益跑通再手动收敛」。

## 6. 实现与取舍（v2.6 起）

原计划「新增第 4 种类型 `rtl_usb_direct`」，实际实施时改了主意：**把
`rtl_usb` 本身升级为直连**，另起 `rtl_usb_tcp` 表示旧的 RTL-TCP 中转。理由：
用户心智里只有「本机 USB」一件事，不该让他先判断该走哪条路；老配置里的
`rtl_usb` 也能直接吃到改进，不必手工改配置。

已落地的代码：

| 文件 | 内容 |
| --- | --- |
| `cr_lbj/core/rtl_paths.py`（新） | 从 decoder 抽出 `runtime_dirs()` / `find_rtl_tool()`，新增 `findRtlsdrDll()`。exe 与 dll 共用同一套目录回溯规则 |
| `cr_lbj/core/source_stats.py`（新） | `recordBlock()` / `buildDiagnostics()`：块率、块间隔抖动、丢块、队列积压的统一口径；`medium='net'|'usb'` 只影响提示语措辞 |
| `cr_lbj/core/usb_direct.py`（新） | `loadDll()` + 33 个导出函数签名绑定；`listDevices()` / `probeDevice()` / `recommendProfile()` / `probeDevices()`；`RtlSdrDirectSource` |
| `cr_lbj/core/decoder.py` | `RtlTcpSource.getDiagnostics()` 改为调用共享实现（输出逐字不变，已回归比对）；`RtlUsbAutoSource` 负责「直连失败 → 自动回退中转」；`_buildChain()` 按 `rtl_usb` / `rtl_usb_tcp` / `rtl_tcp` / `owrx` 分发 |
| `cr_lbj/ui/dialogs/config_ui.py` | 类型下拉 4 项；「检测设备」改为直连枚举（拿 tuner + 增益表），失败再退回 `rtl_test -t`；检测结果里给推荐参数，一键「应用推荐参数」 |
| `cr_lbj/ui/components/history_panel.py` | 默认预设 4 条（USB 直连 / USB 中转 / 本地 RTL-TCP / OWRX）、`SOURCE_TYPE_LABELS`、列表短标签 `SOURCE_TYPE_TAGS` |
| `cr_lbj/ui/windows/main_window.py` | 仪表板「数据源」只对网络源显示 `host:port`；回退中转时状态名带「(已回退中转)」 |

关键设计取舍：

- **`open()` 同步开设备**：`RtlSdrDirectSource.open()` 里就把 `rtlsdr_open`
  和设备配置做完，失败立刻抛错——这样自动回退能在几百毫秒内决定，而不是
  像 TCP 源那样「先返回成功，再在读取时才发现连不上」。
- **回调只做转换**：`read_async` 的 libusb 回调里只做 uint8→complex64 与入队，
  队列满就计入 `droppedBlocks` 直接丢，绝不阻塞（否则会拖垮 libusb 事件线程）。
- **回调对象常驻**：`CFUNCTYPE` 实例保存在 `self._cb`，被 GC 掉就是野指针崩溃。
- **增益就近取值**：推荐值（15.7 / 19.7 dB）先按设备真实增益表就近匹配，
  避免把 R820T 的表套到 FC0013 上。
- **`dll` 目录入搜索路径**：`os.add_dll_directory()` + `PATH`，保证同目录的
  `msvcr100.dll` / `pthreadVC2.dll` 能被找到（否则在干净机器上加载失败）。

验证记录（无棒可用，已做的部分）：

```
py -3.14 -m compileall cr_lbj            → 全包通过（32 个模块）
RtlTcpSource.getDiagnostics() 三场景     → 与重构前输出逐字相同
_onSamples 转换结果 vs TCP 路径           → bit-exact True，complex64 65536 点
80 块灌入 60 容量队列                     → droppedBlocks 正确累加
LbjCore(sourceType='rtl_usb') 启动        → 直连报 -1，日志提示后自动回退 RTL-TCP
离屏 _verify_usb.py                      → 22 项全过（类型/标签/推荐/序列化/分发）
```

## 7. 风险

- **Windows 丢块**：osmocom 老版 dll + libusb 在慢 PC 有丢块历史（KejPi 报告）。
  现有 RTL-TCP 桥用的是同一个 dll，所以风险相同而非新增；若直连实测丢块，
  优先换 KejPi/rtlsdr 或 Blog fork 的 x64 `rtlsdr.dll`（需同步验证 rtl_tcp.exe
  仍可运行，API 兼容）。
- **dll 互换**：rtl_tcp.exe/rtl_test.exe 与 dll 是配套编译的，换 dll 属于
  「同一 API 的实现替换」，风险低但必须实测。
- **设备独占**：直连后设备被本进程独占，其他程序（SDR# 等）无法同时使用；
  与 RTL-TCP 桥行为一致（RTL-TCP 桥也是独占）。
- **拔棒后的 libusb 行为**：`read_async` 在设备消失时可能长时间不返回，
  已按「cancel_async → join(3s)」处理退出，但真拔插恢复要实测。

## 8. 待实测（插入 RTL-SDR 后按顺序做）

1. 直连开流 10 分钟：看 `[诊断]` 的块率是否稳定在 14.6/s（960k ÷ 65536）、
   `droppedBlocks` 是否长期为 0、任务管理器里进程 CPU 占用。
2. 同一根棒子分别用 `rtl_usb`（直连）与 `rtl_usb_tcp`（中转）各跑 10 分钟，
   对比解码条数与 RSSI —— 直连应当不劣于中转。
3. 运行中拔棒 5 秒再插回：日志应出现「USB 数据流中断 → 设备已重连」，
   且能自动恢复出报文，不需要重启程序。
4. 有 V4（R828D）棒时：确认「检测设备」给出的 tuner 提示与推荐增益是否合理。
5. 检测按钮连续点两次：第二次应提示「设备已被占用」（第一次探测完成后
   设备应已释放，正常情况不该占用）。
