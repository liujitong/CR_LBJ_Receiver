# 更新记录

版本号规则（自 v3 起）：

- **大版本**：`v3`（架构/形态级变更才升），以后由用户指定新大版本。
- **小版本**：`v3.x`——功能更新，**桌面与安卓同时升**。
- **最小版本**：`v3.x.y`——只改了一个端才编最小版本号，改哪个端就编哪个端的号。

桌面端与安卓端**共用同一个版本号**（本版两端都是 `v3.1.0`），因为 v3 的目标就是
"一次发布、两端同步"。

---

## v3.1.0 · 2026-11-26

> 版本号：桌面 `cr_lbj.__version__ = 3.1.0`，安卓 `versionName = 3.1.0` / `versionCode = 310`。
> 主题：**桌面工程分目录、车次编排纯自动、地图方案定型（Leaflet + 7 底图 + 百度 BD-09 +
> 离线缓存 + QtWebEngine 修复）、安卓设置页菜单化与界面收敛、敏感地址清理。**

### 一、桌面

- **工程分目录**：`main.py`、`build.py`、`SDR_LBJ.spec`、`cr_lbj/`、`国铁.ico`、`lbj_config.json`
  全部移入 `desktop/`，与 `android/` 平级；运行/打包命令改为
  `python desktop/main.py`、`python desktop/build.py`（仓库根执行），
  `tests/`、`tools/` 与 `build.py` 的路径引用同步更新。
- **车次编排纯自动**：删除 `trainScheme` 配置与界面上的「车次规则」选择器，
  分类逻辑只按日期驱动——过渡期（2027-01-01 前）按字头 + 速度判定，**2027-01-01 起**
  高铁/普速全量按 2026 新方案，速度不再参与判定；旧配置里的 `trainScheme` 键加载时忽略。
- **地图（与安卓共用页面）**：
  - 渲染引擎**回退 Leaflet 1.9.4**（本地化 `shared/web/vendor/leaflet/`，离线可用、零构建），
    删除上一轮实验性的 WebGL 地图引擎与 `vendor/maplibre-gl/`。
  - 底图收敛为 **7 张**：**新增 4 张免 Key 底图**——高德街道/卫星（GCJ-02）、
    百度街道/卫星（BD-09）；保留 OSM 标准与天地图矢量/影像（CGCS2000，需 tk）；
    **删除** Esri、CARTO、OpenTopoMap 等 6 张国外底图。默认底图改为 `amap` 高德街道
    （2026-11-26 实测最快最稳：HTTP 200、63~279 ms，且免 Key）。
  - **百度 BD-09 自定义坐标系**：页面纯 JS 实现百度墨卡托 CRS（`L_BAIDU_CRS` +
    `ll2mc`/`mc2ll`）与百度瓦片编号换算（`BaiduTileLayer`）；切百度时重建地图实例，
    标记/轨迹自动加偏；高德/百度这类偏移坐标系底图与 WGS-84 铁路图层不能混叠，
    页面自动关闭铁路图层并提示，换回 OSM/天地图自动恢复。
  - **离线瓦片缓存**：页面图层面板「缓存本区域」（当前 zoom~zoom+3），进度经
    `LBJ.onCacheProgress` 回传、占用经 `LBJ.cacheStats` 回传；宿主实现
    `LBJHost.cacheArea` 则交给宿主落盘（安卓），否则页面降级为图片预取（桌面）。
  - **修复 QtWebEngine 远程内容拦截**：`map_host.py` 显式打开
    `WebAttribute.LocalContentCanAccessRemoteUrls`（及 `…FileUrls`）——
    QtWebEngine 默认禁止 `file://` 页面访问远程 URL，是 v3.0 桌面地图瓦片不显示的真实原因。
  - 新增两端统一的 `tdtReferer` 机制：天地图请求按白名单域名附加 `Referer`，
    百度请求固定附加 `Referer: https://map.baidu.com/`（无 Referer 会 403）；
    天地图 tk 仍为空则选中只提示、不加载。
  - 配置页/工具栏/页面下拉三处图层清单保持逐字一致（7 底图）；
    `docs/地图与图源.md` 整篇重写（图源清单、可达性实测、tk 申请、坐标系、缓存、契约、排错）。
- 删除旧版高德 Key 配置（`amapKey` / `amapSecurity`）的全部残余引用。

### 二、安卓

- **设置页菜单化**：从长表单改为「图标 + 标题 + 副标题 + 箭头」的菜单式链接列表，
  点击进入子页；取消底部保存按钮——开关/单选改完**即时保存并下发**，
  文本输入在失焦/回车/离开页面时自动保存（带防抖）；连接类参数变更自动重建 DSP 链路。
- **解码页**：收到报文后**自动查询**车次与机车配属并内联展示；手动查询并入设置页
  「查询·数据」分组，**删除底部 Dock 的「查询」页签**（Dock 收敛为五页）。
- **日志**：日志卡片改为**折叠 + 只显示最新一条**，按级别着色。
- **图标**：用桌面 `国铁.ico` 生成 launcher 图标（全密度 mipmap）。
- **删除 IQ 录制**：界面入口、录制线程、文件写出与相关权限/设置项全部移除（附对拍工具保留）。
- **地图对齐 v3.1 方案**：
  - `MAP_BASES` / `FALLBACK_LAYERS` 改为 7 张底图（高德街道/卫星、百度街道/卫星、OSM、
    天地图矢量/影像），删除 Esri/CARTO/OpenTopo 与高德旧 JS 方案残留；
  - WebView 拦截器扩展：天地图按 `tdtReferer` 加 `Referer`，百度固定
    `Referer: https://map.baidu.com/`，统一浏览器 UA；
  - **原生瓦片代拉 + 离线缓存**：`core/TileCache.kt`（DiskLruCache，`cacheDir/tile_cache`，
    上限 300 MB、LRU 淘汰），命中直接返回、未命中 `HttpURLConnection` 代拉并落盘；
    页面 `LBJHost.cacheArea` 桥接 + `LBJ.onCacheProgress` 回传；设置页显示
    「地图瓦片缓存：N 张 / X MB」并可**清除地图缓存**；
  - 地图「**转到自己位置**」：定位权限流程取最后已知位置后调 `LBJ.centerLatLng`（WGS-84）；
  - 图层状态与设置页**单一数据源**（`onLayers` 双向一致）；状态页链路指标溢出修复。

### 三、共享

- `shared/web/railmap.html` 随任务整体迁移：Leaflet 1.9.4 + `vendor/leaflet/`（本地化），
  删除 `vendor/maplibre-gl/`；`BASE_SOURCES` 7 项、`RAIL_SOURCES` 5 种 ORM 样式。
- 页面新增：三类坐标系处理（wgs/gcj/bd）、百度自定义 CRS 与瓦片编号、
  `LBJ.centerLatLng`、离线缓存（`LBJHost.cacheArea` / `LBJ.onCacheProgress` / `LBJ.cacheStats`）、
  `{key}` 天地图 tk 占位（页面不硬编码）。
- `tests/test_shared_web.py` 重写：Leaflet 本地化、7 底图 id/中文名与
  `config_ext.BASE_LAYERS` 逐字一致、百度 CRS/坐标函数、缓存与 `LBJHost` 契约、
  `tdtReferer` 机制、无旧图源残留、`node --check` 语法、文档版本 v3.1。
- `docs/`：`地图与图源.md` 整篇重写；`README.md`、`技术参考.md`、`用户手册.md`、
  `架构说明.md` 的地图章节与版本号同步到 v3.1。

### 四、安全

- **OWRX 服务器真实地址清理**：默认配置、`ReceiverSettings.kt` 默认值、`lbj_config.json`、
  对拍工具脚本、解码器 docstring 与安卓文档中的真实域名统一替换为占位
  （`127.0.0.1` / `owrx.example.com` / 「地址已略」），避免公开仓库泄露第三方服务地址。
- 仓库历史中的同一地址属于**发布前待办**（用 `git filter-repo`/`filter-branch` 重写历史并
  force push，删除仓库外含旧历史的 bundle）；**GitHub 可能短期缓存旧对象**，建议该 OWRX
  服务轮换访问凭据或限制来源。本条目只说明工作区清理已完成，历史重写以发布记录为准。
- 底图全部改为免 Key 直连（天地图 tk 由用户自备并只存本地配置），不再有内置 Key/
  签名等敏感凭据。

---

## v3.0.0 · 2026-11-26

### 一、仓库与工程统一（结构性变更）

- **安卓工程真正并入仓库**：`android/` 从原来的 junction（物理在 `C:\lbj_src`）改为
  **仓库内实体目录**，桌面端、安卓端、共享资源在同一个 Git 仓库里，一次提交两端同步。
  原"中文路径会让 CMake/Ninja 静默崩溃"的结论经实测**不成立**——真实原因是本机
  Android SDK 自带的 CMake 3.22.1/3.31.6 二进制在 Windows 10.0.26300 上配置阶段必然崩溃
  （`STATUS_STACK_BUFFER_OVERRUN`），改用 pip 版 CMake 4.4.5 并把 SDK 自带版本从
  `externalNativeBuild` 里移除后，中文路径下 `assembleDebug` 正常通过。
- 新增 **`shared/` 共享层**（桌面与安卓唯一数据来源）：
  - `shared/web/railmap.html`（Leaflet 地图页，两端共用同一份代码）
  - `shared/web/vendor/leaflet/`（Leaflet 1.9.4 本地化，离线可用，BSD-2-Clause）
  - `shared/data/loco_roster.csv`（机车配属号段表，16622 行，来自 LBJ_Console，GPL-3.0）
  - `shared/data/loco_types.csv`（176 个机车代号 → 短型号/中文名）
  - `shared/data/loco_specs.json`（45 个车型技术参数）
  - `shared/data/places.csv`（49 个预设中心）
  - `shared/NOTICE.md`（第三方授权与条款说明）
- 新增 `tools/gen_shared_data.py`（生成/校验共享数据）、`cr_lbj/data/paths.py`
  （数据目录分层：可写覆盖层 → 内置快照）、`tests/`（51 个用例）。

### 二、车次 / 机车配属查询（两端新增）

- **车次查询**：接 RailGo 公开接口（等级/担当局/客运段/配属段/车型/时刻表/开行日/交路），
  失败自动退回 12306 官方时刻表；统一结果结构，两端字段语义逐字一致。
- **机车配属查询**：新增号段表匹配（型号 + 号段闭区间），支持 `HXD1D-0123` / `韶山4-0123`
  等写法，带别名（DF4B/DF4R→DF4）、相近型号提示、歧义候选、数据来源与更新日期。
- **车型参数**：随配属结果一并展示（轴式/功率/构造速度/简介）。
- 桌面端入口：`工具 → 车次查询…`、`工具 → 机车配属查询…`，机车信息卡与记录详情直接显示配属。
- 安卓端入口：新增「查询」页（车次 / 机车配属两个页签）。

### 三、地图：铁路图源改 OpenRailwayMap，底图可选

- 铁路图层改为 **OpenRailwayMap**（standard / maxspeed / signals / electrified / gauge 五种样式）。
- 底图可选 **11 种**：OSM、CARTO（浅色/深色/路由）、Esri（卫星/街道）、OpenTopoMap、
  天地图（矢量/影像，需 tk）、高德（街道/卫星）。
- **坐标系按底图区分**：WGS-84 系底图可与 ORM 叠加（零偏移）；切到高德（GCJ-02）时
  自动关闭铁路图层（栅格无法逐块纠偏，混叠会整体错 300–500 m），并对列车点自动加偏。
- 默认中心改为「预设城市 + 经纬度」双通道（离线也能用，不再依赖高德地理编码）。
- 高德 JS API 下线：`amapKey`/`amapSecurity` **配置项整个移除**（老配置里的键加载时被忽略），
  底图全部免 Key，配置页不再有这两行。
- 地图页图层切换面板（底图/铁路样式/透明度）内嵌在页面右上角，两端一致。

### 四、安卓端界面改版

- 参考 LBJ_Console（Flutter 版）的视觉骨架重做：**悬浮玻璃胶囊 Dock**（6 页签）、
  无重顶栏（大标题 + 右侧状态胶囊）、中性灰阶 + CR 红/蓝强调色、卡片化分组、
  详情走 `ModalBottomSheet`、等宽数字。
- 六页：地图 / 解码 / 历史 / 状态 / 查询 / 设置。
- 地图页改为加载 `shared/web/railmap.html`（不再用高德 JS API），支持底图/铁路图层切换。
- 历史页支持分组（按车次号 / 按机车号）与多选删除。

### 五、第三方数据自动更新

- 配属号段表支持**自动检查更新**（默认 7 天一次，可关闭）：GitCode 镜像拉取 → 严格校验
  （行数/型号数/中文配属/畸形率）→ 原子写入用户目录 → 内置快照保留可回退。
- 桌面端：`工具 → 检查数据更新（机车配属表）`，设置里显示当前行数/更新日期/来源。
- 安卓端：设置页「数据」组显示当前数据来源与日期，可手动检查。
- 支持环境变量 `CRLBJ_DATA_DIR`（便携部署）与 `CRLBJ_DATA_SOURCE_URL`（自建镜像）。

### 六、修复的潜在问题

- 安卓 map_panel/MapPage 坐标链路：之前 Python/Kotlin 侧统一把 WGS-84 转 GCJ-02 再画，
  一旦换底图就全错；现在**坐标统一传 WGS-84**，由地图页按底图基准决定是否纠偏。
- 地图页去掉了对高德私有 API（`Marker.getZIndex` 等不存在的方法）的依赖，
  标记层改为自管 DOM 与 zIndex，避免"来车后地图不再跟随"的同类问题。
- 安卓端 `android/` 目录不再依赖 `C:\lbj_src`，换机器 clone 即可构建（`local.properties`
  需要按 `docs/安卓构建与环境.md` 生成）。
- 车次/配属查询的所有网络调用都有超时与中文错误文案，不会卡死 UI 或抛栈。
- 数据更新失败不会破坏现有数据（校验不过即丢弃 + `.bak` 回退）。
- 修复 `lbj_config.json` 模板里历史遗留的重复数据源条目说明（见架构文档）。

### 七、文档

- 新增：`docs/地图与图源.md`、`docs/车次与配属查询.md`、`docs/安卓版说明.md`、
  `docs/安卓构建与环境.md`、`docs/CHANGELOG.md`（本文件）。
- 更新：`README.md`、`docs/用户手册.md`、`docs/技术参考.md`、`docs/架构说明.md`。
- 下线：`docs/高德地图配置手册.md`（高德 JS API 已不在使用路径上）。

### 八、测试

- `python -m pytest tests -q` → 51 passed（共享数据完整性、号段匹配、别名/歧义、
  车次查询离线逻辑 + 联网用例自动跳过、地图页结构与 JS 语法、自动更新全流程、路径分层）。
- 桌面端离屏冒烟（`QT_QPA_PLATFORM=offscreen`）：主窗口构造、地图页加载与标记推送、
  查询对话框两个页签、主题切换、多档分辨率无溢出。
- 安卓：`assembleDebug` 通过 + 模拟器安装启动验收（详见 `docs/安卓版说明.md` 的验收记录）。

---

## 历史版本（v2.x 桌面端 / v3.0 安卓 M0–M3）

| 版本 | 要点 |
|---|---|
| v2.6.1 | 顶栏重排（菜单栏即顶栏）、记录详情窗口收窄、USB 直连隐藏主机端口 |
| v2.6 | 本机 USB 改 librtlsdr 直连（ctypes，零新依赖）、设备自适应参数、失败自动回退 rtl_tcp |
| v2.5 | 双屏混合 DPI 修复、源码按职责分层（`cr_lbj/` 包）、移除机车图片区域 |
| v2.4 | 迁移 Fluent Design（qfluentwidgets）、底栏重做、列统一、地图日夜联动 |
| v2.3 | 三段全景布局、即时换肤（无需重启）、运行状态仪表板分块标色 |
| v2.3.1 | 地图三项修复（跟随失效、定位点偏移、默认中心支持地名） |
| v2.2 | CR 红/蓝双主题、下段改页签、配置窗口六页惰性建页、轨迹抽稀与避让 |
| v2.1 | 布局重构、重复报文合并去重（2.5s 窗口 + 质量打分）、一站式启动、日志总线 |
| v2.0 | 经纬度解析、高德地图、多数据源、2026 车次规则 |
| 安卓 M0–M3 | 工程骨架与 JNI、C++ DSP 与对拍 0 差异、Kotlin 业务层、Room 历史库/CSV/前台服务/IQ 录制/地图页 |
