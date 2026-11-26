# CR-LBJ-Receiver · 中国铁路 LBJ 列车预警器解码器（桌面 + 安卓）

> 用一支几十元的 RTL-SDR，接收 821.2375 MHz 上的 LBJ 列车防护报警信号，
> 实时解出车次、机车、线路、公里标、速度与经纬度，并在地图上跟着车跑。
> v3.0 起**桌面端与安卓端同仓库、同版本号、同数据**，一次发布两端同步。

**版本** v3.2.1（2026-11-26） ｜ **平台** Windows 10/11 · Android 8.0+ ｜ **许可** GPL v3 ｜ **作者** BG2GBQ

**目录**：[两端功能对照](#两端功能对照) ｜ [桌面端界面](#桌面端界面) ｜ [安卓端](#安卓端) ｜
[快速开始](#快速开始) ｜ [车次与配属查询](#车次与配属查询) ｜ [地图与图源](#地图与图源) ｜
[共享数据与自动更新](#共享数据与自动更新) ｜ [文档](#文档) ｜ [运行与构建](#运行与构建) ｜
[目录结构](#目录结构) ｜ [更新记录](#更新记录) ｜ [常见问题](#常见问题) ｜ [声明](#声明)

---

## 两端功能对照

| 功能 | 桌面端 | 安卓端 |
|---|---|---|
| RTL-SDR 接收（USB 直连 / rtl_tcp / OWRX） | ✅ 直连 + 中转 + 网络 | ✅ OTG 直连（fd 注入）+ rtl_tcp |
| POCSAG/FFSK 解码、车次/机车/线路/公里标/速度 | ✅ | ✅（C++ 与桌面 1:1，对拍 0 差异） |
| 长报文经纬度 → 实时地图、轨迹、跟随 | ✅ | ✅ |
| 地图：OpenRailwayMap 铁路图层（已内置 ORM 所需 Referer）+ **7 种底图** + 离线瓦片缓存 | ✅ | ✅（同一份页面 + 原生瓦片缓存） |
| 车次查询（RailGo + 12306 兜底） | ✅ 工具菜单 | ✅ 设置页「查询·数据」/ 解码页自动查询 |
| 机车配属查询（16622 行号段表） | ✅ 工具菜单 / 机车卡 | ✅ 设置页「查询·数据」/ 解码页自动展示 |
| **车次·机车信息自动展示**（地图弹窗/右侧面板/解码卡） | ✅ | ✅ |
| 历史记录 / 去重 / CSV 导出 | ✅ SQLite | ✅ Room |
| 频谱与接收状态 | ✅ 图形/终端 + 仪表板 | ✅ 指标块 |
| 日/夜主题 | ✅ 即时切换 | ✅ 跟随系统 |
| 后台/便携 | 桌面常驻 | 前台服务（不做 24h 挂机） |

---

## 桌面端界面

v2.3 起是**全景式布局**：一屏分三段，所有内容同屏可见；v2.4 换 Fluent Design；
v3.0 起地图是两端共用的 Leaflet 页面（`shared/web/railmap.html`），v3.1 收敛为
**7 张底图 + 离线缓存**（默认高德街道，免 Key）；v3.2 修复 ORM 铁路图层（Referer）与
瓦片误判，并让标记弹窗/「列车信息」卡片显示车次·机车信息。

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ 视图   配置   工具   帮助                                    [▶ 接收] [已连接] │
├──────────────────────────────────────────┬────────────────────────────────────┤
│                                          │ 当前解码 / 历史记录                │
│                                          │ 时间 车次 方向 速度 公里标 … 报文  │
│      实时位置（Leaflet）                 ├────────────────────────────────────┤
│      铁路图层 OpenRailwayMap             │ 列车信息                           │
│      底图 高德 / 百度 / OSM / 天地图…    │ 车次 方向 速度 公里标 机车 线路 …  │
│ [夜间][中心][跟随][清除][底图▾][铁路☑]   │                                    │
├────────────────────┬─────────────────────┴──────────────┬─────────────────────┤
│ 接收频谱   [图形▾] │ 车次信息                           │ 机车信息            │
│  ~~~──~──~──       │ 12306 / RailGo 结果 · 查看时刻表   │ 机型 / 配属 / 参数  │
├────────────────────┴────────────────────┴────────────────────┴────────────────────┤
│ ● 16:04:35 [解码] G1234 下行 82 km/h │ 接收正常 · 信号 -63 dB · AFC 0.06       │
└──────────────────────────────────────────────────────────────────────────────────┘
```

- 分隔线可拖；`F11` 全屏、`Ctrl+L` 完整日志、`Ctrl+D` 运行状态仪表板、`Ctrl+T` 日/夜切换。
- 地图工具栏：**底图下拉**、**铁路图层开关**、夜间、中心、跟随、清除、用浏览器打开。
- 地图右上角还有一层页面内图层面板（底图 / 铁路样式 / 不透明度），和工具栏联动。

---

## 安卓端

- **五页**：地图 / 解码 / 历史 / 状态 / 设置，悬浮玻璃胶囊 Dock 切换（参考 LBJ_Console 的视觉骨架）。
- **地图页**直接加载 `shared/web/railmap.html`（与桌面同一份代码），支持 7 种底图/铁路图层切换、跟随、轨迹、**离线瓦片缓存**（原生 DiskLruCache，300 MB 上限，可查占用/清除）。
- **查询入口**：车次查询（RailGo → 12306 兜底）、机车配属查询（号段表 + 车型参数）已并入设置页「查询·数据」分组；解码页收到报文会自动查询并在卡片内展示。
- **解码页**：一键开始，卡片式记录（车次 + 方向 + 速度/公里标/线路/机车），点开看详情。
- **历史页**：Room 库，按车次号/机车号分组，多选删除，CSV 导出（SAF）。
- **设置页**（菜单式）：数据源（OTG / rtl_tcp）、采样率与增益、去重窗口、地图（7 种底图 / 铁路图层 / 天地图 tk+Referer / 默认中心 / 瓦片缓存）、车次数据源、数据更新。
- 详见 [`docs/安卓版说明.md`](docs/安卓版说明.md)、[`docs/安卓构建与环境.md`](docs/安卓构建与环境.md)。

---

## 快速开始

### 桌面端

1. **装驱动**（一次性）：Zadig 把 RTL2832U 的 WinUSB 驱动装上（或用官方驱动包）。
2. **选数据源**：`配置 → 数据源`，默认「本机 RTL-SDR（USB 直连）」；也可用 `rtl_tcp` 或 OWRX。
3. **开始接收**：顶栏「▶ 接收」或 `Ctrl+R`。
4. **看地图**：收到长报文就有经纬度，地图自动跟随；跟丢了点「中心」或关掉「跟随」自己拖。

### 安卓端

1. 装 `app-debug.apk`（自行构建，产物在 `android/app/build/outputs/apk/debug/`）。
2. OTG 接 RTL-SDR（或用局域网 rtl_tcp），在设置里选数据源与采样率（默认 240 kS/s）。
3. 回「解码」页点 **开始接收**；首次会申请 USB 权限与通知权限。
4. 地图页选底图：默认「高德 街道」（免 Key、实测最快）；想看铁路图层就换「OSM」或「天地图」（天地图先在设置里填 tk 与 Referer 域名）；高德/百度是偏移坐标系，切过去会自动暂停铁路图层。

---

## 车次与配属查询

- **车次查询**：接 [RailGo](https://railgo.dev/) 公开接口（列车等级、担当局、客运段、**配属段**、车型、
  时刻表、开行日、交路），失败自动退回 12306 官方时刻表；下拉可强制指定数据源。
- **机车配属查询**：内置 **16622 行**「机型 + 号段 → 配属局段」表，按报文机车号自动匹配，
  带别名（DF4B→DF4）、相近型号提示、歧义候选；同时显示车型技术参数。
- 数据来源与匹配规则、失败边界、更新机制：见 [`docs/车次与配属查询.md`](docs/车次与配属查询.md)。

---

## 地图与图源

- **引擎**：Leaflet 1.9.4（本地化在 `shared/web/vendor/leaflet/`，离线可用、零构建、无 CDN）；
  页面 `shared/web/railmap.html` 桌面与安卓共用。
- **铁路图层**：OpenRailwayMap（standard / maxspeed / signals / electrified / gauge）。
  ORM 官方瓦片要求 `Referer: https://www.openrailwaymap.org/`（只带 UA 仍 403），
  v3.2 起两端宿主在网络层内置，无需用户配置；桌面实测 OSM 底图 + ORM 标准 **16/16 瓦片成功**。
- **底图（7 张）**：**高德街道/卫星**、**百度街道/卫星**（4 张免 Key，默认**高德街道**）、
  OSM 标准、天地图矢量/影像（CGCS2000，需 tk）。
- **坐标系**：列车点/轨迹/铁路图层对外一律 WGS-84。高德是 GCJ-02、百度是 BD-09（页面纯 JS
  实现自定义墨卡托 CRS），标记与轨迹按底图自动加偏；偏移坐标系底图与 WGS-84 铁路图层不混叠，
  切过去会自动暂停铁路图层并提示，换回 OSM/天地图自动恢复。
- **可达性**：2026-11-26 本机实测高德/百度 HTTP 200（63~279 ms，真实瓦片）、天地图无 tk 418、
  OSM 15 s 超时；ORM 无 Referer 时 403（v3.2 起宿主补 Referer 后实测 16/16 成功）。
  可达性随网络变化，以现场复测为准（脚本见地图文档）。
- **车次·机车信息**：收到长报文后自动查车次（等级/担当局/担当段/配属段/车型/区间）与
  机车配属（型号/配属单位/制造厂），显示在**地图标记弹窗**、桌面右侧「列车信息」卡片、
  安卓解码卡；标记副标题带车次等级。异步查询、失败静默，不影响解码。
- **离线缓存**：页面图层面板「缓存本区域」（当前 zoom~zoom+3）；安卓宿主 DiskLruCache 落盘
  （300 MB，设置页可查占用/清除），桌面降级为图片预取（进浏览器 HTTP 缓存）。
- 完整清单、天地图 tk 申请与 Referer 白名单、百度 CRS、自建铁路层、排错：
  见 [`docs/地图与图源.md`](docs/地图与图源.md)。

---

## 共享数据与自动更新

`shared/` 是两端唯一数据来源，构建时进 APK、打包时进 exe：

| 文件 | 内容 | 自动更新 |
|---|---|---|
| `shared/data/loco_roster.csv` | 机车配属号段表（16622 行，LBJ_Console GPL-3.0） | ✅ 7 天一次，可关 |
| `shared/data/loco_types.csv` | 机车代号 → 短型号/中文名（176 条） | ❌ 随版本 |
| `shared/data/loco_specs.json` | 45 个车型技术参数 | ❌ 随版本 |
| `shared/data/places.csv` | 49 个预设中心坐标 | ❌ 随版本 |
| `shared/web/railmap.html` | 两端共用的地图页（Leaflet 本地化） | ❌ 随版本 |

自动更新链路：GitCode 镜像拉取 → **严格校验**（行数/型号数/中文配属/畸形率）→ 原子写入
`%LOCALAPPDATA%\CR-LBJ-Receiver\data\` → 内置快照保留可回退（`updater.restore_backup()`）。
配置项：`dataAutoUpdate`（默认开）、`dataUpdateIntervalDays`（默认 7）；
环境变量 `CRLBJ_DATA_DIR`（便携）、`CRLBJ_DATA_SOURCE_URL`（自建镜像）。
第三方授权与条款：[`shared/NOTICE.md`](shared/NOTICE.md)。

---

## 文档

| 文档 | 内容 |
|---|---|
| [用户手册](docs/用户手册.md) | 界面、数据源、调参、地图、配置、排错、FAQ（桌面端为主） |
| [技术参考](docs/技术参考.md) | 线程模型、DSP 链、POCSAG 帧、BCD/长报文字段、打包、扩展点 |
| [架构说明](docs/架构说明.md) | 目录分层、依赖方向、共享层设计、两端对照 |
| [地图与图源](docs/地图与图源.md) | 底图清单、ORM 条款、坐标系与偏移、自建瓦片 |
| [车次与配属查询](docs/车次与配属查询.md) | 数据源、字段、匹配规则、自动更新、已知限制 |
| [安卓版说明](docs/安卓版说明.md) | 功能、权限、与桌面差异、验收记录 |
| [安卓构建与环境](docs/安卓构建与环境.md) | JDK/NDK/CMake 版本、CMake 崩溃绕过、模拟器调试 |
| [更新记录](docs/CHANGELOG.md) | 版本规则与各版本要点 |
| [v3.0 验收记录](docs/验收记录-v3.0.md) | 本次交付实际跑过的测试、读数与未验证项 |

---

## 运行与构建

### 桌面端：从源码运行

```bash
python -m pip install PySide6 PySide6-Addons PySide6-Fluent-Widgets scipy pyqtgraph
python desktop/main.py         # 需要 Python 3.13+，本机实测 3.14（仓库根执行）
```

### 桌面端：一键打包

```bash
python desktop/build.py        # 产物 dist/CR-LBJ-Receiver.exe + README + docs（dist 在仓库根）
```

`desktop/build.py` 会清理构建产物 → PyInstaller → 清理运行期数据 → 校验 → 汇总。
`shared/` 通过 `desktop/SDR_LBJ.spec` 的 datas 打进 `_MEIPASS/shared/`。

### 安卓端：构建 APK

```powershell
cd android
# local.properties（不入库）：
#   sdk.dir=D\:\\Android\\SDK
#   cmake.dir=D\:\\Python\\Python314\\Lib\\site-packages\\cmake\\data
pwsh -File tools/fix_ninja.ps1            # 一次性：把 ninja>=1.12 放进 <cmake.dir>\bin
$env:JAVA_HOME='D:\Java\jdk-21.0.11'
.\gradlew.bat :app:assembleDebug          # 产物 app/build/outputs/apk/debug/app-debug.apk
pwsh -File tools/test.ps1                 # 单元测试（必须走它，见下）
```

> 本机有三处必须知道的坑（详见 [安卓构建与环境](docs/安卓构建与环境.md)）：
> ① Android SDK 自带的 CMake 3.22.1 / 3.31.6 二进制在本机配置阶段必崩，要用 pip 版
> CMake（`pip install cmake==4.4.5`）并写 `cmake.dir`，且**不要**写死 `cmake.version`；
> ② ninja 1.10 用 ANSI 代码页解析中文路径会 `FindFirstFileExA` 报错，用
> `tools/fix_ninja.ps1` 装 ninja ≥1.12；
> ③ JVM 单元测试在中文路径下会 `ClassNotFoundException`（JDK 解析 `@argfile` 的非 ASCII
> classpath 失败），必须用 `tools/test.ps1`（内部 `subst` 到 ASCII 盘符）。
> 依赖下载同样要走国内镜像：`settings.gradle.kts` 已把阿里云 Maven 排在最前。

### 测试

```bash
python -m pytest tests -q          # 90 个用例：共享数据/号段匹配/车次查询/车次编排/地图页/自动更新/路径分层
python tools/gen_shared_data.py    # 重新生成并校验 shared/data
```

---

## 目录结构

```
CR_LBJ_Receiver/
├── desktop/                桌面端工程
│   ├── main.py             桌面入口
│   ├── build.py            PyInstaller 构建脚本（仓库根执行 python desktop/build.py）
│   ├── SDR_LBJ.spec        打包配置（含 shared/ 与 docs/ 的 datas）
│   ├── lbj_config.json     默认配置模板（运行期配置/历史库也生成在 desktop/）
│   ├── 国铁.ico             程序图标
│   └── cr_lbj/             桌面端 Python 包
│       ├── runtime.py/ app.py/ gui.py
│       ├── core/           解码器、DSP 桥、数据源（USB 直连 / rtl_tcp）
│       ├── data/           loco_info、history、loco_roster、train_info、updater、paths
│       └── ui/             theme、widgets、map_panel、components、dialogs、windows
├── android/                安卓工程（Kotlin + Compose + C++ DSP/JNI）
│   └── app/src/main/{java,cpp,res}
├── shared/                 两端共用（唯一数据来源）
│   ├── web/railmap.html    Leaflet 地图页 + vendor/leaflet
│   ├── data/*.csv|json     配属号段、车型代号、参数、预设中心
│   └── NOTICE.md           第三方授权与条款
├── docs/                   全部文档
├── tests/                  pytest 用例
├── tools/                  gen_shared_data.py、rtl/ 与对拍工具
└── dist/                   打包产物（不入库）
```

---

## 更新记录

| 版本 | 要点 |
|---|---|
| **v3.2.1** | 安卓：状态页重排（3 组等高指标 + 日志限高滚动）、解码页常驻图改为点状态胶囊弹出小瀑布、**修复地图打开即退回高德的 bug**（配置生效前的图层回报不再落盘）、空态文案弱化、全面屏安全区适配；桌面：历史记录移入「工具→历史记录」（查看/删除）、数据源与射频合并一页、「列车信息」去掉车次/配属行、车次卡与机车卡显示全程与**担当/配属全称**（含 RailGo 结果）、记录详情新增 RailGo 区块；共享地图页：地图弹窗只留车次/方向/速度/公里标/时间/坐标，标记脚注加大加粗提高可读性 |
| **v3.2.0** | 修复地图「可达却判不可达」误判（瓦片统计按底图/铁路分离，全屏提示只由底图触发）；修复 ORM 铁路图层叠加（两端宿主补 `Referer: https://www.openrailwaymap.org/`，桌面实测 16/16 瓦片成功）；README/NOTICE/「关于」致谢正式化 |
| **v3.1** | 桌面工程分目录 `desktop/`；车次编排 2027-01-01 纯自动；地图回退 Leaflet + 7 底图（高德/百度免 Key、OSM、天地图）+ 百度 BD-09 自定义 CRS + 离线瓦片缓存 + QtWebEngine 远程内容修复；安卓设置页菜单化 + 自动保存 + 自动查询 + 日志折叠 + 转到自己位置；共享地图页迁移 |
| **v3.0.0** | 安卓并入仓库统一版本；共享层 `shared/`；车次/配属查询；地图改 OpenRailwayMap + 11 种底图；安卓界面改版；第三方数据自动更新 |
| v2.6.1 | 菜单栏即顶栏、详情窗口收窄、USB 直连隐藏主机端口 |
| v2.6 | 本机 USB 改 librtlsdr 直连、设备自适应参数、自动回退 rtl_tcp |
| v2.5 | 双屏混合 DPI、源码分层为 `cr_lbj/` 包、移除机车图片 |
| v2.4 | Fluent Design、底栏重做、列统一、地图日夜联动 |
| v2.3 | 三段全景布局、即时换肤、状态仪表板 |

完整列表与版本号规则见 [`docs/CHANGELOG.md`](docs/CHANGELOG.md)。

---

## 常见问题

**Q：地图一片灰 / 提示瓦片失败？**
当前网络访问不到那个底图。默认是**高德街道**（免 Key、实测最快）；OSM 本机常超时、ORM 可能 403。
想看铁路图层就切「OSM」或「天地图」（先在设置里填 tk 与 Referer 域名）。

**Q：铁路图层开了却什么都没有？**
先看底图：高德/百度是偏移坐标系，页面会自动暂停铁路图层——换 OSM 或天地图。
再看版本：OpenRailwayMap 官方瓦片要求 `Referer: https://www.openrailwaymap.org/`
（**只带 UA 也会 403**），v3.2 起两端宿主已内置；旧版会整层 403、甚至误判「底图不可达」。
最后看地区：ORM 数据来自 OSM，`signals` / `maxspeed` 在中国普遍稀疏，缺数据属正常。
状态栏「铁路 N/失败 M」会写明当前状态，详见 [`docs/地图与图源.md`](docs/地图与图源.md) §3.5。

**Q：为什么高德/百度底图下不能叠铁路图层？**
高德是 GCJ-02、百度是 BD-09，ORM 是 WGS-84，栅格瓦片无法逐块纠偏，叠加会整体错 300–500 m。
详见 [`docs/地图与图源.md`](docs/地图与图源.md) §4。

**Q：机车配属查不到？**
先看提示：是「型号未收录」还是「号段表内无该编号」。号段表是静态快照，新造车会有滞后；
`工具 → 检查数据更新` 可拉最新；仍未命中就是上游没收录，不会编造。

**Q：车次查询失败？**
RailGo 是个人托管服务，可能临时不可用；把数据源切到「12306」，或稍后重试。

**Q：安卓构建卡在 CMake？**
见上文「安卓端：构建 APK」的说明——用 pip 版 CMake 并写 `cmake.dir`。

更多排错见 [`docs/用户手册.md`](docs/用户手册.md) 第 12 章。

---

## 数据来源

- 解码规则：TB/T 3504 相关公开资料 + 实收报文逆向核对。
- 机车配属号段表：[LBJ_Console](https://github.com/undef-i/LBJ_Console)（GPL-3.0）。
- 车型参数：中车官网产品页、维基百科、百度百科、Trainfanz（2026-11 联网核对）。
- 车次数据：RailGo 公开接口、铁路 12306 公开查询接口。
- 地图：OpenStreetMap / 天地图 / 高德 / 百度（图源清单与可达性实测见 [`docs/地图与图源.md`](docs/地图与图源.md)）；
  铁路图层 [OpenRailwayMap](https://www.openrailwaymap.org/)，前端引擎 Leaflet 1.9.4。
- 第三方授权与条款逐项说明：[`shared/NOTICE.md`](shared/NOTICE.md)。

## 致谢

本项目的若干核心数据与实现思路来自开源社区，特此正式致谢：

### LBJ_Console（作者：undef-i）

[LBJ_Console](https://github.com/undef-i/LBJ_Console)（GPL-3.0）是一个优秀的 LBJ
报文接收与显示项目。**本项目使用或参考了它以下内容**：

| 使用内容 | 说明 |
|---|---|
| 机车配属号段表 | `resources` 分支的 `loco_info.csv` → 本仓库 [`shared/data/loco_roster.csv`](shared/data/loco_roster.csv)（16622 行，未改字段），是「机车配属查询」与地图/解码页「配属单位」的数据基础 |
| 机车类型代号表 | `loco_type_info.csv` 的代号/短型号 → [`shared/data/loco_types.csv`](shared/data/loco_types.csv) 的 `code` / `shortCode` 列 |
| 安卓端界面骨架 | 五页导航 + 悬浮玻璃 Dock 的视觉结构参考其实现 |
| 地图图源方案 | OSM 标准瓦片 + OpenRailwayMap 铁路图层的组合方式（其 Flutter 端栅格实现）与本项目共享地图页思路一致 |
| 铁路图层离线兜底 | 其 PMTiles/本地矢量铁路层的思路 → 本项目的 `rail_local.geojson` 离线铁路图层 |

感谢 **undef-i** 及其贡献者以 GPL-3.0 开放这些数据与代码。

### 其他开源项目与服务

感谢 [RailGo](https://railgo.dev/)、
[SX1276_Receive_LBJ](https://github.com/undef-i/SX1276_Receive_LBJ)、
[Scorpio-yzy/LBJReceiver](https://github.com/Scorpio-yzy/LBJReceiver)、
[Arch-Jason/RailwayPagerDemod](https://github.com/Arch-Jason/RailwayPagerDemod)
等开源项目提供的思路、数据与先期验证；感谢
[OpenStreetMap](https://www.openstreetmap.org/) 贡献者（ODbL）、
[OpenRailwayMap](https://www.openrailwaymap.org/)（CC-BY-SA）、
[Leaflet](https://leafletjs.com/)（BSD-2-Clause）、
[天地图](https://www.tianditu.gov.cn/)、
[高德地图](https://www.amap.com/)、
[百度地图](https://map.baidu.com/)、
铁路 12306 公开查询接口提供数据与服务。

完整授权与使用条款见 [`shared/NOTICE.md`](shared/NOTICE.md)。

## 声明

本项目仅供**铁路爱好者技术研究与学习**使用。接收无线电信号请遵守当地法律法规；解码所得数据
不得用于行车指挥、运营决策或任何商业用途。因使用本程序产生的一切后果由使用者自行承担。

## License

GPL v3 — 见 [`LICENSE`](LICENSE)。
