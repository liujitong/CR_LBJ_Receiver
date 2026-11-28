# CR-LBJ-Receiver

> **文档由 AI 辅助生成（DeepSeek Harness / deepseek-v4.1-flash），已与代码行为核对；如有出入以程序实际行为为准。**

> 适用版本：**v4.0.0**（2026-11-29） ｜ 适用端：Windows 桌面 / Android ｜ 最后更新：2026-11-29

中国铁路 LBJ 列车预警信号接收与解码程序，同时提供 **Windows 桌面端** 与 **Android 客户端**。

程序在 821.2375 MHz 频点接收机车发出的 LBJ 预警报文，完成比特同步、BCH 纠错与报文解析，输出车次、机车、线路、公里标、方向、速度与经纬度，并在地图上跟踪列车、估算到达时间、查询车次与机车配属。

---

## 功能

| 能力 | 说明 |
|---|---|
| 报文接收 | 支持 RTL-SDR USB 直连、RTL-TCP、OpenWebRX（OWRX）三种数据源，可在运行时切换与保存多套配置 |
| 信号解调 | 1024 点 FFT 频谱、半带抽取 + 信道 FIR、FM 鉴频、DPLL 位同步、BCH(31,21) 纠错、POCSAG 帧同步 |
| 报文解析 | 短报文 / 合并报文 / 独立长报文三类；解析车次、方向、速度、公里标、线路名、机车代号与型号、经纬度 |
| 频谱显示 | 256 点频谱曲线 + 瀑布图（Turbo 色标、自动增益、时间滚动） |
| 地图跟踪 | Leaflet 地图，7 种底图（天地图 / OSM / 高德 / 百度，免 Key）+ OpenRailwayMap 铁路图层；GCJ-02 / BD-09 坐标适配；离线瓦片缓存；自动跟随与轨迹 |
| 历史记录 | SQLite 存储，支持搜索、备注、多选删除、导出 CSV；同一车次按质量择优去重 |
| 车次查询 | RailGo → 12306 双通道，查询时刻表、担当局段、配属、车型 |
| 机车查询 | 本地号段表 + 车型参数表，支持配属局段与制造厂反查 |
| 到达估算 | 依据公里标与线路方向估算到达本站时间 |
| 干扰统计 | 解析不出车次的帧按上行/下行计入干扰，仅记日志、不入库 |
| 数据更新 | 车次/配属数据可在线检查更新，原子写入用户目录并保留回退快照 |

---

## 技术栈

**桌面端（Windows 10/11 x64）**

- Python 3.14，GUI：PySide6 6.11（Qt 6）
- 频谱曲线：pyqtgraph；瀑布图：NumPy + QImage 自绘
- 数值计算：NumPy / SciPy（FIR 设计、FFT、滤波）
- 打包：PyInstaller（单文件 EXE）
- 版本资源与 Authenticode 代码签名：Windows SDK signtool

**Android（8.0+，arm64-v8a / armeabi-v7a / x86_64）**

- Kotlin + Jetpack Compose（Material 3）
- 解码核心：C++17 + JNI，与桌面端 Python 实现逐行对应（同一套参数与算法）
- USB 直连：librtlsdr 1.0.27 + libusb 1.0.27（内置）
- 存储：Room（历史记录）、DiskLruCache（地图瓦片）
- 构建：Gradle + Android Gradle Plugin + CMake / NDK r27

**两端共享**

- 地图页面 `shared/web/railmap.html`（单文件 Leaflet 应用，两端加载同一份）
- 数据表 `shared/data/*.csv`、`shared/data/loco_specs.json`
- 关于信息 `shared/about.json`（版本、作者、开源致谢、协议只维护一处）

---

## 快速开始

### 桌面端

1. 运行 `CR-LBJ-Receiver.exe`。
2. 「设置 → 数据源与射频」选择数据源：
   - **USB 直连**：插入 RTL-SDR，程序自动识别 tuner 并推荐采样率/增益；
   - **RTL-TCP**：填入 `主机:端口`（如 `127.0.0.1:1234`）；
   - **OWRX**：填入 OWRX 的 `主机:端口` 与 profile。
3. 频点设为 `821.2375 MHz`，采样率 `960 kS/s`（或 `240 kS/s`），带宽 `35 kHz`。
4. 点击「开始接收」。

配置与历史记录存放于 `%LOCALAPPDATA%\CR-LBJ-Receiver\`，程序目录不产生任何文件。

### Android

1. 安装 APK。
2. 若使用 USB 直连：OTG 连接 RTL-SDR，首次会请求 USB 访问权限。
3. 其余步骤与桌面端一致。
4. 权限：USB 设备访问（必需）；定位（可选，用于「转到自己位置」）；网络（地图、车次查询）。

---

## 目录结构

```
CR_LBJ_Receiver/
├── desktop/          Windows 桌面端（Python 包 cr_lbj）
│   ├── cr_lbj/core/      DSP、解码器、数据源、去重、到达估算
│   ├── cr_lbj/ui/        主窗口、面板、对话框
│   └── build.py          PyInstaller 打包脚本
├── android/          Android 客户端（Gradle 工程 + C++ 解码核心）
├── shared/           两端共享资源
│   ├── web/railmap.html  地图页面
│   ├── data/             CSV 数据表
│   └── about.json        关于信息
├── docs/             文档
└── tests/            桌面端单元测试
```

---

## 文档

| 文档 | 内容 |
|---|---|
| [用户手册](docs/用户手册.md) | 界面操作、参数含义、常见问题 |
| [技术参考](docs/技术参考.md) | 协议结构、解调算法、报文格式、参数 |
| [架构说明](docs/架构说明.md) | 模块划分、数据流、线程模型 |
| [安卓版说明](docs/安卓版说明.md) | 安卓功能、权限、构建与签名 |
| [地图与图源](docs/地图与图源.md) | 底图清单、坐标系、缓存策略 |
| [车次与配属查询](docs/车次与配属查询.md) | 查询通道、数据更新 |
| [USB 直连与设备自适应](docs/USB直连与设备自适应.md) | tuner 识别、增益推荐、OTG |
| [代码签名](docs/代码签名.md) | Windows / Android 签名流程与材料管理 |
| [CHANGELOG](docs/CHANGELOG.md) | 版本变更记录 |
| [NOTICE](docs/NOTICE.md) | 许可与第三方组件 |

---

## 许可

GPL-3.0。第三方组件与数据来源的完整清单见 [`shared/about.json`](shared/about.json)。

本程序仅接收并解码公开空口报文，不发射、不注入、不解密任何加密内容。使用须遵守所在地无线电管理法规。

## 作者

刘纪彤（BG2GBQ） · bg2gbq@mlxkj.xyz · https://github.com/liujitong/CR_LBJ_Receiver