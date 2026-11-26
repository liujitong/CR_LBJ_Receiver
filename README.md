# CR-LBJ-Receiver · 中国铁路 LBJ 列车预警器（桌面 + 安卓）

> 用一支几十元的 RTL-SDR，接收 **821.2375 MHz** 上的 LBJ 列车防护报警信号，实时解出车次、机车、
> 线路、公里标、速度与经纬度，并在地图上跟着列车跑。桌面端与安卓端同仓库、同版本号、同数据。

> 适用版本：**v3.2.9**（2026-11-26） ｜ 适用端：桌面 / 安卓 ｜ 最后更新：2026-11-26

**平台** Windows 10/11 · Android 8.0+ ｜ **许可** GPL v3 ｜ **作者** BG2GBQ

---

## 项目简介

- **RTL-SDR 接收**：桌面支持 USB 直连、RTL-TCP 与 OWRX；安卓支持 OTG 直连（fd 注入）与 RTL-TCP。
- **报文解码**：POCSAG/FFSK 全链在两端 1:1 实现（桌面 Python、安卓 C++/JNI），对拍 0 差异；
  输出车次、机车、线路、公里标、速度与经纬度。
- **共享地图页**：两端共用 `shared/web/railmap.html`（Leaflet 1.9.4 本地化，离线可用）；
  7 张底图（高德、百度、OSM、天地图）+ OpenRailwayMap 铁路图层 + 离线瓦片缓存。
- **车次与配属查询**：接 RailGo（失败退 12306）查车次等级/担当/配属/时刻表；内置 16622 行
  机车号段表查配属与车型参数，结果自动展示在解码卡、地图弹窗与详情窗口。
- **共享数据**：`shared/` 是两端唯一数据来源，构建时进 APK、打包时进 exe；号段表支持自动更新。
- **两端差异**：桌面为全景式一屏布局；安卓为五页（地图/解码/历史/状态/设置）+ 前台服务。
  详细对照见 [用户手册](docs/用户手册.md) 与 [架构说明](docs/架构说明.md)。

---

## 快速开始

### 桌面端

1. **装驱动**（一次性）：用 Zadig 给 RTL2832U 安装 WinUSB 驱动（或使用 RTL-SDR 官方驱动包）。
2. **选数据源**：`配置 → 数据源与射频`，默认「本机 RTL-SDR（USB 直连）」；也可选 RTL-TCP 或 OWRX。
3. **开始接收**：点顶栏「▶ 接收」（`Ctrl+R`），收到长报文后地图自动跟随。

### 安卓端

1. 自行构建并安装 `app-debug.apk`（产物在 `android/app/build/outputs/apk/debug/`，构建步骤见
   [安卓构建与环境](docs/安卓构建与环境.md)）。
2. OTG 接 RTL-SDR，或在设置里填局域网 RTL-TCP / OWRX 地址；采样率默认 240 kS/s。
3. 回「解码」页点 **开始接收**；第一次会申请 USB 与通知权限，地图页默认「高德 街道」底图。

### 从源码运行 / 构建

```bash
# 桌面端：源码运行（仓库根执行，Python 3.13+）
python -m pip install PySide6 PySide6-Addons PySide6-Fluent-Widgets scipy pyqtgraph
python desktop/main.py

# 桌面端：一键打包（产物 dist/CR-LBJ-Receiver.exe + README.md + docs/）
python desktop/build.py

# 测试
python -m pytest tests -q
```

安卓端构建命令、本机三处环境坑（CMake / ninja / JDK argfile）见
[安卓构建与环境](docs/安卓构建与环境.md)。

---

## 文档导航

全部文档位于 **`docs/`** 目录，本 README 只保留入口信息。

| 文档 | 内容 |
|---|---|
| [用户手册](docs/用户手册.md) | 界面、数据源、调参、地图、配置、排错、FAQ、术语（以桌面端为主） |
| [技术参考](docs/技术参考.md) | 线程模型、DSP 链、POCSAG 帧、BCD/长报文字段、数据模型、扩展点、打包 |
| [架构说明](docs/架构说明.md) | 目录分层、依赖方向、共享层设计、两端对照、历史文件对照 |
| [地图与图源](docs/地图与图源.md) | 底图清单、ORM 条款、坐标系与偏移、天地图 tk、离线缓存、两端契约 |
| [车次与配属查询](docs/车次与配属查询.md) | 数据源、字段、匹配规则、自动更新、已知限制 |
| [USB 直连与设备自适应](docs/USB直连与设备自适应.md) | USB 直连原理、按 tuner 自适应推荐参数、验证记录与风险 |
| [安卓版说明](docs/安卓版说明.md) | 安卓端功能、权限、与桌面差异、测试与验收 |
| [安卓构建与环境](docs/安卓构建与环境.md) | JDK/NDK/CMake 版本、中文路径三坑、模拟器调试 |
| [更新记录](docs/CHANGELOG.md) | 版本规则与各版本变更明细（最新在顶部） |
| [v3.0 验收记录](docs/验收记录-v3.0.md) | v3.0 交付实际跑过的测试、读数与未验证项（历史存档） |
| [安卓移植日志](docs/安卓移植日志.md) | 安卓端 M0–M3 移植过程与构建错误记录（历史存档） |
| [安卓模块划分方案](docs/安卓模块划分方案.md) | v3.0 安卓端开工前的模块/JNI 契约确认稿（历史存档） |
| [第三方资源与授权](docs/NOTICE.md) | 数据、地图图源、前端库与联网接口的逐项来源与授权条款 |

---

## 致谢要点

- **[LBJ_Console](https://github.com/undef-i/LBJ_Console)**（作者 **undef-i**，GPL-3.0）：机车配属号段表
  （`shared/data/loco_roster.csv`）、机车类型代号表、安卓端五页导航 + 悬浮 Dock 的界面骨架、
  OSM + OpenRailwayMap 图源组合与离线铁路层思路。
- 感谢 [RailGo](https://railgo.dev/)、[OpenStreetMap](https://www.openstreetmap.org/) 贡献者（ODbL）、
  [OpenRailwayMap](https://www.openrailwaymap.org/)（CC-BY-SA）、[Leaflet](https://leafletjs.com/)（BSD-2-Clause）、
  天地图、高德、百度与铁路 12306 公开查询接口提供数据与服务。
- 第三方资源的逐项授权与使用条款见 [docs/NOTICE.md](docs/NOTICE.md)。

---

## 声明

本项目仅供**铁路爱好者技术研究与学习**使用。接收无线电信号请遵守当地法律法规；解码所得数据
不得用于行车指挥、运营决策或任何商业用途。因使用本程序产生的一切后果由使用者自行承担。

## License

GPL v3 — 见 [LICENSE](LICENSE)。