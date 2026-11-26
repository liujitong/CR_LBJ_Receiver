# 更新记录

版本号规则（自 v3 起）：

- **大版本**：`v3`（架构/形态级变更才升），以后由用户指定新大版本。
- **小版本**：`v3.x`——功能更新，**桌面与安卓同时升**。
- **最小版本**：`v3.x.y`——只改了一个端才编最小版本号，改哪个端就编哪个端的号。

桌面端与安卓端**共用同一个版本号**（本版两端都是 `v3.2.1`），因为 v3 的目标就是
"一次发布、两端同步"。

> 关于版本编号：本版是 `v3.2.0`（地图可达误判修复 / ORM 铁路图层叠加修复）之后的
> **修复与打磨版**，版本号 **v3.2.1**（安卓 `versionCode 321` > `320`，已装 v3.2.0 可直接覆盖升级）。
> 这批 UI/交互改动开发期间曾按内部口径记作 `v3.1.1`，最终统一为 `v3.2.1` 发布。

---

## v3.2.5 · 2026-11-26

> 版本号：桌面 `cr_lbj.__version__ = 3.2.5`，安卓 `versionName = 3.2.5` / `versionCode = 325`。
> 主题：**安卓端多数据源 + 设置页「数据源与射频」合并、瀑布图平滑化、地图页浮层重排。**

### 一、安卓：数据源与射频合并 + 多数据源

* 设置页菜单由 7 组收敛为 **6 组**：`数据源` + `射频` 合并为 **「数据源与射频」**（旧子页 id `rf` 仍兼容，点过就不会打开空白页）。
* 新增**多数据源**（`core/ReceiverSettings.kt`）：
  * `SourceProfile(name/type/host/port/sampleRate/gainDb/ppm/dcOffsetHz)` 与
    `sources: List<SourceProfile>` + `activeSource`；
  * 默认三条：本机 USB 直连（240k / 19.7dB / DC 50k）、本地 rtl_tcp（127.0.0.1:1234）、
    OWRX（127.0.0.1:8073）；JSON 落盘到 SharedPreferences；
  * 设置页「数据源（点击切换）」列表：点非当前项即**切换并重建 DSP 链路**；
    「＋ 把当前配置存为新数据源」新增一条；每项可「删除」（至少保留一条）；
    编辑连接/射频字段会自动回写到当前项（`withActiveSnapshot()`）；
  * `ReceiverViewModel` 新增 `selectSource / addSource / removeSource / renameSource`，
    切换后写一行 `[数据源] 已切换到「…」` 日志。
* 射频字段（频率/增益/PPM/带宽/DC 偏移）与连接字段合并到同一张「连接与射频」卡。

### 二、安卓：瀑布图平滑化（不再"糊成马赛克"）

* 窄带频谱固定 **32 bin**，原实现逐 bin 画矩形铺满全宽（每块约 30px），视觉上就是方块。
* 现在（`DecodePage.buildWaterfallBitmap`）：
  * **横向线性插值**：每两个 bin 之间插 8 列，再用 `FilterQuality.Medium` 拉伸到全宽；
  * **smoothstep 对比度拉伸**：弱信号层次更清楚、强信号更亮；
  * 帧缓存 80 → **140 帧**（≈21s 瀑布），高度 160 → 176dp；
  * 位图渲染（`Bitmap.setPixels` + `Image`）比逐矩形绘制更省 CPU。

### 三、安卓：地图页浮层重排

* 原布局：左上「数据源状态胶囊」+ 右上 **5 个独立浮动胶囊**（跟随/图层/回中心/转到自己位置/缓存本区域）——散、挡地图。
* 现在：
  * **右上角**：状态胶囊（OWRX 接收中等）+ 一张**紧凑工具卡**，内含
    「跟随 / 图层 / 回中心 / 缓存本区域」四项（图标 + 短文字，当前项强调色）；
    缓存进行中直接显示 `缓存 done/total`；
  * **右下角**：「转到自己位置」独立为 **圆形定位 FAB**（`Icons.Filled.MyLocation`，
    地图 App 通行位置），权限/定位失败提示逻辑不变；
  * 移除 `FloatPill` 依赖（该页不再用）。

### 四、验证

* 安卓 `assembleDebug` 编译通过；单测 40/40；`pytest` 全绿。
* 模拟器实测（结构与文本证据）：设置页 6 组菜单、「数据源（点击切换）」列表三项 +
  「使用中」标记、切换后日志 `[数据源] 已切换到…`；地图页右上工具卡 4 项 + 右下定位按钮。

---

## v3.2.4 · 2026-11-26

> 版本号：桌面 `cr_lbj.__version__ = 3.2.4`，安卓 `versionName = 3.2.4` / `versionCode = 324`。
> 主题：**桌面端二级窗口「大得超出屏幕 / 不自适应」修复；顺带修复配置对话框 `CONFIG_PAGES`
> 崩溃回归；核对 ORM 透明度链路并清理死方法。**

### 一、新增 `fit_dialog_to_screen()`（`ui/widgets.py`）

各对话框原先写死 `resize(spx(1040), spx(700))` 这类尺寸。在 1366×768、或 1280×800@200%
（逻辑可用区只有 640×400）的副屏上，`spx()` 还会按 UI_SCALE 放大 → 窗口顶出屏幕、
右侧/底部内容被裁、按钮点不到。

新函数（经 `cr_lbj.runtime` 转发，所有 `from cr_lbj.runtime import *` 的模块都能用）：

* 取窗口所在屏（`windowHandle().screen()`）；**未 show 时用鼠标所在屏**兜底
  （与主窗口 `_currentScreen` 同一思路）；
* 目标尺寸 = `min(spx(design), 可用区 - 边距)`；**下限同样不超屏幕**；
* 居中到该屏可用区；异常时退回"按设计尺寸"，绝不让自适应本身把窗口搞崩。

### 二、六个二级窗口改造

| 窗口 | 原 | 现 |
|---|---|---|
| 历史记录 `history_dialog.py` | `spx(760)×spx(460)` / `spx(1040)×spx(700)` | `fit(1040, 700, 760, 460)` |
| 车次/机车配属 `query_ui.py` | `spx(620)×spx(480)` / `spx(860)×spx(720)` | `fit(860, 720, 620, 480)` |
| 用户手册 `ManualDialog` | `resize(spx(700), spx(640))` | `fit(700, 640, 460, 400)` |
| 关于 `AboutDialog` | **`setFixedSize(spx(540), spx(480))`（不可缩放）** | `fit(540, 480, 420, 360)`，**改为可缩放** |
| 状态仪表板 `StatusDashboard` | `resize(spx(720), spx(660))` | `fit(720, 660, 520, 440)` |
| 配置 `ConfigDialog` | **裸像素** `setMinimumSize(720,560)` / `resize(820,660)` | `fit(820, 660, 720, 560)`（设计像素） |

### 三、表格列宽自适应

* **历史记录**：原先 9 列全 `ResizeToContents` + 线路列 `Stretch` —— 列一宽窗口就被撑大、
  出现横向滚动条。现在只让「时间」列按内容自适应，其余 `Interactive`（可压缩），
  「线路」吃余量；`table.setMinimumWidth(0)` + `ScrollBarAsNeeded`。
* **车次时刻表**：站名 `Stretch`；只让「到点/发点」两个关键列 `ResizeToContents`，
  「停留/里程」`Interactive` 并给默认宽度；同样放开最小宽度。

### 四、状态仪表板网格列数自适应

`_grid_cols()`：窗口宽度 **< spx(520) → 2 列**、**< spx(700) → 3 列**、否则 **4 列**；
`resizeEvent` 里列数档位变化时按上次分组自动重排（`_lastGroups` / `_builtCols`）。
窄窗口不再把每个指标方块压成一团。

### 五、ORM 透明度核对 + 死方法清理

* 链路确认已通：`ConfigDialog` 的滑块 → `cfg.mapRailOpacity` → 保存后
  `MainWindow._onConfigChanged()` → `mapPanel.setConfig()` → `host.apply_config()` →
  payload `railOpacity` → 页面 `applyConfig()` 里的 `railOpacity(cfg.railOpacity)` → 生效。
  冒烟断言 `_config_json()['railOpacity'] == 0.55` 通过，**未重复实现**。
* 删除 `map_panel.setRailOpacity()`：全仓库无调用方（透明度只走 `apply_config`），
  属僵尸方法。

### 六、顺带修复的回归（重要）

**配置对话框打开即崩**：`ConfigDialog.__init__` 用 `CONFIG_PAGES`，但 v3.1.1 把
`HistoryPanel` 删掉后这些常量留在 `ui/components/history_panel.py`，而
`config_ui.py` / `main_window.py` 是 `from cr_lbj.runtime import *`、**从未导入该模块** →
`NameError: CONFIG_PAGES is not defined`（配置菜单构建、首次运行预设 `default_sources()` 同样会炸）。
现在把 `CONFIG_PAGES` / `SOURCE_TYPE_LABELS` / `SOURCE_TYPE_TAGS` / `default_sources()`
移到 `cr_lbj/runtime.py` 共享层；`history_panel.py` 退化为兼容壳（只 re-export）。

### 七、验证

* `pytest`：**110 passed**（新增 `tests/test_desktop_ui_v324.py`：适配函数、六个窗口改造、
  表格列策略、仪表板列数、ORM 透明度 payload、死方法清理、CONFIG_PAGES 回归防护）。
* 离屏冒烟（800×800 可用区）：6 个窗口全部落在屏内且下限不超屏
  （history 768×700 / query 768×720 / manual 700×640 / about 540×480 / config 768×660 /
  dashboard 720×660）；dashboard 列数 480px→2、640px→3、720/900px→4。
* 桌面 `pytest` 与 `desktop/build.py` 均通过。

---

## v3.2.3 · 2026-11-26

> 版本号：桌面 `cr_lbj.__version__ = 3.2.3`，安卓 `versionName = 3.2.3` / `versionCode = 323`。
> 主题：**修复安卓 USB 直连（OTG 接 RTL-SDR）打不开设备：`rtlsdr_open_fd 失败 rc=-1`。**

### 根因（真机 SELinux 日志为证）

真机（Xiaomi 2510DRK44C / Android 17，OTG 接 RTL2832U）点「一键开始」报：

```
[usb] rtlsdr_open_fd 失败 rc=-1
native start 失败 rc=-1
```

`adb logcat` 里能看到 App 进程（域 `untrusted_app_34`）被 SELinux 拒绝：

```
avc: denied { read }    name="usb"  tcontext=u:object_r:usb_device:s0        tclass=dir
avc: denied { search }  name="usb1" tcontext=u:object_r:vendor_sysfs_usb_node:s0
comm="DefaultDispatch"
```

原因：`rtlsdr_open_fd()`（本项目补丁）里直接调 `libusb_init()`。**libusb 初始化默认会扫描
`/dev/bus/usb` 与 sysfs 做设备枚举**，而 Android 的普通 App 域没有这个权限（SELinux 直接拒绝）。
在 Android 上用「Java 传 fd + `libusb_wrap_sys_device`」的模式，必须显式关闭设备发现，
否则初始化/包装阶段就会失败，最终表现为 `rtlsdr_open_fd rc=-1`。

### 修复（`android/app/src/main/cpp/thirdparty/librtlsdr/src/librtlsdr.c`）

1. **Android 下用 `libusb_init_context()` + `LIBUSB_OPTION_NO_DEVICE_DISCOVERY`**
   （libusb 1.0.27 官方推荐搭配 `libusb_wrap_sys_device` 的用法），不再枚举 USB 设备；
2. **`libusb_claim_interface` 失败时先 `libusb_detach_kernel_driver` 再重试一次**
   （RTL2832U 可能被内核 DVB 驱动 `dvb_usb_rtx28xxu` 自动绑定，或上次会话未干净释放）；
3. **诊断可观测**：新增 `RTLSDR_LOGE` 宏，Android 下把关键错误写到 logcat
   （tag `librtlsdr`，如 `libusb_wrap_sys_device error N (fd=M)`、
   `usb_claim_interface error N`），native 的 `stderr` 默认不进 logcat，之前完全看不到原因；
4. `fd < 0` 提前拦截并报错（避免拿无效 fd 进 libusb）。

### 顺带修的两处日志/配置问题

5. **USB 启动日志不再拼接 `host:port`**：之前 `[启动] usb 主机:端口 …` 会把网络源的
   服务器地址打进 USB 日志（用户设备上还残留着旧配置里的地址，看起来像「USB 连到了
   某域名」）。现在 USB 源显示 `USB 直连`，只有网络源才显示 `host:port`。
6. **旧配置残留归一化**：`ReceiverSettings.load()` 在 `sourceType == usb` 时把
   `host/port` 归一化回默认值（USB 本来就不用这两个字段）。旧版本在设备
   SharedPreferences 里留下的网络服务器地址不会再出现在设置页/日志里（隐私清理）。
   注意：**这是设备上的历史配置残留，代码与 APK 里已无该字符串**（发布前已从源码与
   git 历史中清理，APK dex 校验为 0 命中）。

### 验证

- 4 个 ABI（arm64-v8a / armeabi-v7a / x86 / x86_64）的 CMake 编译全部通过。
- 真机复测：装 v3.2.3 后点「一键开始」，logcat 里可见 `librtlsdr` 的具体错误或成功路径；
  若仍失败，日志会直接给出 `wrap` / `claim` 的错误码与 fd，便于进一步定位
  （如 OTG 供电不足、设备被其他 App 占用）。

---

> 版本号：桌面 `cr_lbj.__version__ = 3.2.2`，安卓 `versionName = 3.2.2` / `versionCode = 322`。
> 主题：**修复 OpenStreetMap / OpenRailwayMap 瓦片「418 Access blocked」——按两家使用政策做合规整改。**

### 为什么会 418（根因）

真机地图出现 `418`，OSM 返回的正文是：

```
Access blocked
App is not following the tile usage policy of OpenStreetMap's volunteer-run servers:
http://osm.wiki/Blocked
```

OpenStreetMap 官方瓦片与 OpenRailwayMap 都是**志愿者运营的公益服务**，其使用政策明确要求：

1. **必须提供可识别的 User-Agent**（含应用名 / 版本 / 联系方式），不得伪装成浏览器；
2. **禁止批量预取/下载瓦片**（bulk download、prefetch、离线整片抓取）；
3. 不得绕过限流、不得伪造 Referer 等来源标识。

本程序此前两点都踩了：代拉瓦片时用了**伪装浏览器的 UA**（`Mozilla/5.0 ... Chrome/128`），
且 v3.1 上线的「缓存本区域」会对当前视野 **z~z+3 一次预取几百上千张**瓦片 ——
于是被 OSM 判定违规，返回 **418 封禁**（通常为 IP 级临时封禁，数小时自动解除）。
另外 ORM 之前为了绕过 403，注入了 `Referer: https://www.openrailwaymap.org/`，
这属于**伪造来源**，同样违反其政策。

### 修复内容（两端一致）

1. **合规 UA**：OSM / ORM 请求统一使用可识别 UA
   `CR-LBJ-Receiver/3.2.2 (+https://github.com/liujitong/CR_LBJ_Receiver; ...)`；
   高德 / 百度 / 天地图仍用浏览器 UA（它们没有此类政策要求）。
   - 安卓：`core/TileCache.kt` 新增 `UA_APP` / `UA_BROWSER` / `userAgentFor()` / `isPolicyStrictHost()`；
   - 桌面：`ui/map_host.py` 拦截器对 `*.openstreetmap.org`、`*.openrailwaymap.org` 注入该 UA。
2. **移除伪造 Referer**：ORM 不再注入官方站点 Referer（带合规 UA 实测 200）。
3. **禁止批量预取**：
   - 页面 `railmap.html`：`isPolicyStrictSource()` 判定当前底图/铁路图源，命中 OSM/ORM 时
     「缓存本区域」直接拒绝并解释原因；新增 `LBJ.onCacheBlocked()` 回传宿主；
   - 安卓 `MapPage.runCacheArea()`：二次过滤 OSM/ORM 的 URL（`isPolicyStrictHost`），
     即使页面漏传也不会批量下载；
   - **浏览时的被动缓存保留**（用户看过的区域仍会缓存，离线可用），这不违反政策。
4. **底图不可达提示**：OSM 被封时明确解释「需合规 UA、禁止预取，本程序已整改；
   仍被封通常是临时封禁」；一键换底图改为推荐 **高德 / 天地图**（不再推荐 OSM）。
5. 文档：`docs/地图与图源.md` 增加「OSM / ORM 使用政策与合规要求」小节；
   `shared/NOTICE.md` 补充两条政策链接与我们的合规做法。

### 验证

- 本机实测：OSM（合规 UA）200；ORM（合规 UA、**无 Referer**）200 —— 证明去掉伪造 Referer 后仍可用。
- 桌面 `pytest` **110 passed**（新增合规断言：合规 UA 存在、伪造 ORM Referer 已移除、
  页面与安卓均过滤批量预取）。
- 真机（2510DRK44C，无线 adb）复测见交付说明：若该机 IP 仍在 OSM 封禁时效内，
  需等待解封（本程序已合规，解封后即可恢复）。

---

## v3.2.2 · 2026-11-26

> 版本号：桌面 `cr_lbj.__version__ = 3.2.2`，安卓 `versionName = 3.2.2` / `versionCode = 322`。
> 主题：**修复 OpenStreetMap / OpenRailwayMap 瓦片「418 Access blocked」——按两家使用政策做合规整改。**

## v3.2.1 · 2026-11-26

> 版本号：桌面 `cr_lbj.__version__ = 3.2.1`，安卓 `versionName = 3.2.1` / `versionCode = 321`。
> 主题：**移动端 UI 打磨与地图行为修复、桌面端信息重新归位（历史记录/全称/RailGo）、地图页精简。**

### 一、安卓端

1. **状态页重排**：指标按「信号·门控（2 列大块）/ 数据流（3 列）/ 射频·链路（3 列）」三组等高分栏，
   数值加 `weight` + 省略号防撑高；`调谐` 改「调谐 MHz」+ 3 位小数、`累计块/丢块` 百万级紧凑显示；
   日志卡折叠 2 条 + 条数 + 展开限高 240dp 内部滚动并自动滚到最新（最多 60 条，前缀着色）。
2. **解码页去掉常驻频谱图**：改为一行信号摘要条（`信号 · dB · 有/无信号 · 瀑布 ›`）；
   点顶部**数据源状态胶囊**（如「OWRX · 等待首帧」）弹出 `ModalBottomSheet` 小瀑布
   （真实窄带频谱热力瀑布；无起伏时退回 RSSI 色条 + 门限虚线），关闭后不留占位。
3. **修复「设置里配了底图，打开地图仍退回高德」**：根因是 `railmap.html` 以 `file://` 加载时
   按默认底座渲染并 `notifyHost()` 上报，安卓 `HostBridge.onLayers` 无条件落盘把 `mapBase`
   冲成 `amap`（还会永久写坏设置）。修法三层：页面加 `configApplied` 门禁（`applyConfig`
   前不上报）；`MapPage` 加 `pageSynced` 门禁（`status().base` 与设置一致前，图层回报只记日志不落盘）；
   `persistLayers` 在偏移底图下不接受 `rail=off`（免得切回 OSM 后铁路层永不恢复）。
   实测：设置选百度 → 进地图即百度（prefs 保持 `baidu/orm_standard`），杀进程重启仍为百度。
4. **空态文案弱化**：`暂无列车坐标` 16sp 主文字色 → 12sp 三级灰，提示行 11sp；`EmptyState` 统一 13sp/11sp。
5. **全面屏适配**：非地图页用 `safeDrawing(Top+Horizontal)`、Dock 用 `safeDrawing(Bottom+Horizontal)`；
   地图页浮层加 `safeDrawing` insets（WebView 仍全屏铺满）。实测系统状态栏 74px，胶囊顶边从 37px 移到 111px。

### 二、桌面端

1. **历史记录移入「工具 → 历史记录…」（Ctrl+H）**：主界面取消「当前解码/历史记录」页签，只留当前解码；
   新对话框支持列表（时间/车次/方向/速度/公里标/线路/机车/类别/坐标）、双击/查看详情（复用记录详情）、
   删除选中 / 删除全部（二次确认）、刷新、导出 CSV。顺带修复 `HistoryDb.clear()` 在事务内
   `VACUUM` 导致「清空」实际失败的问题（Python 3.14）。
2. **配置对话框：数据源 + 射频合并**为「数据源与射频」一页（类型/设备 → 主机端口 → 采样率/频率/增益/
   PPM/带宽/DC 偏移/块大小 → RSSI 门控与 AFC 两列），配置分页由 7 页减为 6 页。
3. **「列车信息」面板瘦身**：去掉 v3.2 新增的「车次信息」「机车配属」两行（11 字段），
   车次/机车信息回归「车次信息」「机车信息」两卡展示。
4. **车次卡 / 机车卡：全称与 RailGo**：`TrainQueryPanel` 改为 RailGo 优先异步查询，显示
   「车次 始发→终到(到发时刻) / 等级 · 担当 全称 / 配属 · 车型 / 来源」；新增
   `data/depot_names.py` 做标准局段/制造厂简称→全称（如「南局南段→南昌局南昌机务段」，
   未收录的地方铁路原样返回不猜）；`LocoInfoPanel` 配属与制造厂分行显示全称。
5. **记录详情新增 RailGo 区块**：等级、担当局+段全称、配属段、车型、始发→终到（含时刻）、
   主要停站时间（最多 6 站），带「时刻表」按钮；查不到显示「未查询到 … 的车次信息」。

### 三、共享地图页（两端共用）

1. **地图弹窗精简**：只保留「车次 / 方向 / 速度 / 公里标 / 收到时间 / 轨迹里程 / 坐标」，
   去掉线路、机车、类别、车次信息、车底、配属（这些信息在桌面「车次信息/机车信息」卡片与
   安卓解码卡展示）。`LBJ.setTrainInfo` 保留为宿主推送通道，页面不再渲染。
2. **标记脚注可读性**：速度/公里标小字 9.5px → 11px、字重 600、加文字阴影与描边，
   夜间/日间底色分别加深到 0.88/0.94 不透明度；弹窗字号 12→12.5px。
3. **`configApplied` 门禁**（见安卓第 3 条），是两端「页面图层回报不冲掉用户配置」的基础。

### 四、测试与验证

- 桌面 `pytest`：**109 passed**（新增 `tests/test_desktop_ui_v311.py` 17 项与地图页 2 项契约断言）。
- 安卓 `tools/test.ps1`：**40/40**（DataUpdater 10 / LocoRoster 13 / TrainInfoClient 9 /
  TrainClassifier 3 / MapTrainInfo 5）。
- 桌面 `desktop/build.py` 打包成功；安卓 `assembleDebug` 成功。
- 实测：安卓设置选百度→地图即百度（重启仍保持）；桌面历史对话框造 6 条记录完成查看/删除/清空；
  RailGo 真实查询（G7 → 北京局天津客运段、D2234 → 成都局重庆客运段）；
  地图页 `configApplied` 冒烟（applyConfig 前零上报、之后上报用户底图）。

---

## v3.2.0 · 2026-11-26

> 版本号：桌面 `cr_lbj.__version__ = 3.2.0`，安卓 `versionName = 3.2.0` / `versionCode = 320`。
> 主题：**修复地图「可达却判不可达」误判与 ORM 铁路图层叠加（Referer）、双端展示车次·机车信息、致谢正式化。**

### 一、地图（误判修复 / ORM Referer 修复 / 失败判定规则）

#### 1. 修复「可达却判不可达」误判

- **根因**：`shared/web/railmap.html` 的瓦片统计原先底图与铁路共用一个计数器
  （`tilesTotal` / `tilesFailed`）。OpenRailwayMap 官方瓦片缺 Referer 时整层 403，
  这些 `tileerror` 把计数器顶高，页面据此把**本可正常显示**的底图误判成「底图不可达」，
  弹出全屏换图提示，桌面坐标栏也变红「底图不可达，换一张」。
- **修复**：统计**按图层分离**为 `baseTileOk` / `baseTileFail`（底图）与
  `railTileOk` / `railTileFail`（铁路）；`tilesTotal()` / `tilesFailed()` 保留旧名但
  **只返回底图**统计（宿主兼容）。`LBJ.status()` 新增 `railTilesTotal` / `railTilesFailed`，
  原 `tilesTotal` / `tilesFailed` 只统计底图。
- **失败判定规则（现在）**：
  - 全屏「底图不可达」提示只在**底图**满足 `baseTileFail >= 6` 且
    （`baseTileOk === 0` 或 `baseTileFail >= baseTileOk * 19`，即失败率 ≥ 95%）时出现；
  - 铁路瓦片失败只弹一次小字 toast（`warnRailFail()`，失败 ≥ 4 张触发）并写状态行
    「铁路 N/失败 M」，**不再影响底图判定**；
  - 桌面坐标栏「底图不可达，换一张」仍按 `failed > 8` 且（`total == 0` 或
    `failed >= total × 0.9`）判定（`map_panel._TILE_FAIL_HINT`），但输入已是**纯底图**统计；
  - 安卓 `MapPage` 同步改为 `tilesFailed >= 6` 且（`tilesTotal == 0` 或
    `tilesFailed >= tilesTotal * 19`）。

#### 2. 修复 ORM 铁路图层叠加（关键）

- **根因**：OpenRailwayMap 官方瓦片要求请求带合法 `Referer: https://www.openrailwaymap.org/`；
  **只带浏览器 UA 仍返回 403**，而两端地图页都以 `file://` 加载，页面自身没有 Referer
  → 铁路图层全部失败，并连带触发上面的误判。
- **桌面**：`desktop/cr_lbj/ui/map_host.py` 的 `_TdtRefererInterceptor` 对
  `*.openrailwaymap.org` 注入 `ORM_REFERER = 'https://www.openrailwaymap.org/'`。
  **坑**：PySide6 的 `QWebEngineUrlRequestInfo.setHttpHeader` 的 **header 名和值都必须是
  `bytes`**（`info.setHttpHeader(b'Referer', ...encode('utf-8'))`）；传 `str` 不报错也不生效，
  请求照旧无 Referer → 403（排错章节已写明）。
- **安卓**：`android/.../core/TileCache.kt` 的 `refererFor(host, tdtReferer)` 对
  `*.openrailwaymap.org` 返回同一 Referer（`host.endsWith("openrailwaymap.org") -> "https://www.openrailwaymap.org/"`），
  由原生代拉 `HttpURLConnection.setRequestProperty("Referer", …)` 补上。
- **实测**：桌面 OSM 底图 + ORM 标准图层 **16/16 瓦片全部成功**（修复前整层 403）。

#### 3. 失败降级

- 铁路瓦片仍失败时页面状态行显示「铁路 ok/失败」；全部失败（`railTileFail > 4 &&
  railTileOk === 0`）时提示「铁路图层不可用：需要合法 Referer（v3.2 起客户端已内置），
  可改用本地铁路线（GeoJSON）」，底图照常显示。

#### 4. 铁路图层自动暂停状态（`railWanted` / `railAutoOff`）

- 切到高德/百度（偏移坐标系）时页面把铁路图层自动置 `off`，提示改为「**铁路图层已暂停**」；
  页面用 `railWanted` / `railAutoOff` 记住「用户想要的样式」，`notifyHost()` 上报
  `railWanted` 而不是 `off`，避免宿主把自动暂停误当成用户选择关闭；切回 OSM / 天地图时
  自动恢复原样式。

### 二、信息展示（双端车次·机车·担当路局）

- **共享页面 `shared/web/railmap.html`**：
  - 标记副标题新增**车次等级**（`markerSub()` 追加 `info.grade`）；
  - 点击弹窗新增四行：**车次信息**（等级 · 担当局 · 担当段）、**车底**（配属段 · 车型）、
    **区间**（始发 → 终到）、**机车配属**（配属单位 · 制造厂），由 `infoRows()` 生成；
  - 新 API `LBJ.setTrainInfo(idOrTrain, info)`：宿主异步查询到信息后补进标记，**不改变位置**；
    参数可传对象或 JSON 字符串，返回命中的标记数；`update()` 的 `trains[]` 元素也支持
    `info` 对象，后到的非空字段与旧值浅合并；
  - `info` 字段契约：`grade` 等级 / `bureau` 担当局 / `section` 担当段 / `owner` 配属段 /
    `model` 车型 / `from`·`to` 始发终到 / `locoDepot` 机车配属单位 / `locoMaker` 制造厂 /
    `locoModel` 机车型号。
- **桌面**：
  - 新增 `desktop/cr_lbj/ui/info_lookup.py`：`TrainInfoService`（车次走 `train_info.query`
    后台线程查询并按车次缓存，信号 `infoReady`；机车走本地 `loco_roster.lookup_loco`
    同步查询，毫秒级）与 `merge_info()`；
  - 主窗口解码后由 `_decode_info()` 组装 `info` → 地图标记 + 右侧「车次信息」面板；
  - `TrainInfoPanel` 新增「车次信息」「机车配属」两行（共 13 字段）与 `setInfo()`；
  - `MapPanel.setTrainInfo()` 在后台查询结果晚到时补推；`MapHost.set_train_info()` 落到
    `window.LBJ.setTrainInfo`。
- **安卓**：
  - `MapPage` 把 `vm.trainInfos` / `vm.locoInfos`（解码页自动查询的同一份缓存）
    组装成 `info` 带进地图 payload，标记与点击弹窗即时显示；
  - `DecodePage` 当前解码卡新增「担当段 `runner`」与「区间」两行，机车配属行显示
    **机车型号 + 配属单位 + 制造厂**（`li.model` / `li.depot` / `li.maker`）。

### 三、致谢

- `README.md`「致谢」章节重写：正式致谢 **LBJ_Console**（作者 **undef-i**，GPL-3.0），
  逐项列出使用内容——`loco_roster.csv` 配属号段表、`loco_type_info.csv` 代号表、
  安卓界面骨架、OSM + OpenRailwayMap 图源方案、本地矢量铁路层思路；并补充 RailGo、
  OSM / ORM / Leaflet / 天地图 / 高德 / 百度等数据与服务致谢。
- `shared/NOTICE.md` 第 2 节补致谢段（数据、界面骨架、图源方案、离线铁路层思路）。
- 桌面「关于」对话框新增「开源致谢」段；安卓「关于」页新增致谢段。

### 四、测试与验证

- 文档同步：`README.md`、`docs/CHANGELOG.md`、`docs/地图与图源.md`、`docs/技术参考.md`、
  `docs/用户手册.md`、`docs/安卓版说明.md`、`docs/架构说明.md`、`shared/NOTICE.md`
  版本号与内容更新到 v3.2。
- 自动化：`D:\Python\Python314\python.exe -m pytest tests -q` → **90 passed**（含新增的
  v3.2 契约测试：ORM Referer、瓦片分图层统计、车次·机车信息展示）。
- 地图实测：桌面 OSM 底图 + ORM 标准图层 16/16 瓦片成功；铁路层失败不再触发
  「底图不可达」全屏提示。
- `LBJ.status()` 字段核对：`tilesTotal` / `tilesFailed` 只含底图，
  `railTilesTotal` / `railTilesFailed` 为铁路层计数。

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
