# 第三方资源与授权说明

> 适用版本：**v3.2.8**（2026-11-26） ｜ 适用端：桌面 / 安卓 ｜ 最后更新：2026-11-26
>
> 本文件逐项说明随程序分发的第三方数据、地图页与联网接口的来源与授权。
> 这些资源位于 `shared/`（桌面端与安卓端共用）；对外分发（打包成 exe / apk 发布）时
> 请保留本文件与各项目自带的 LICENSE。

## 目录

1. [Leaflet 1.9.4 —— shared/web/vendor/leaflet/](#1-leaflet-194--sharedwebvendorleaflet)
2. [机车配属号段表 —— shared/data/loco_roster.csv](#2-机车配属号段表--shareddataloco_rostercsv)
3. [机车类型代号表 —— shared/data/loco_types.csv](#3-机车类型代号表--shareddataloco_typescsv)
4. [机型技术参数 —— shared/data/loco_specs.json](#4-机型技术参数--shareddataloco_specsjson)
5. [预设中心点 —— shared/data/places.csv](#5-预设中心点--shareddataplacescsv)
6. [地图瓦片与图源（运行时联网获取，不随仓库分发）](#6-地图瓦片与图源运行时联网获取不随仓库分发)
7. [车次数据接口（运行时联网获取）](#7-车次数据接口运行时联网获取)
8. [其它](#8-其它)

---

## 1. Leaflet 1.9.4 —— `shared/web/vendor/leaflet/`

- 来源：<https://leafletjs.com/>（1.9.4 发行包，已本地化，运行时不联网取 JS/CSS）
- 授权：**BSD-2-Clause**，全文见 `shared/web/vendor/leaflet/LICENSE`
- 用途：内嵌地图页 `shared/web/railmap.html` 的唯一前端依赖
- 沿革：v3.0 曾短暂尝试 MapLibre GL JS，v3.1 因百度瓦片需要自定义投影 CRS 而回退 Leaflet。

## 2. 机车配属号段表 —— `shared/data/loco_roster.csv`

- 来源：项目 **LBJ_Console**（<https://github.com/undef-i/LBJ_Console>，作者 **undef-i**）
  的 `resources` 分支根目录 `loco_info.csv`，共 16622 行，未做字段改动
  （仅在文件头补了 4 行注释说明来源与格式）。
- 授权：**GPL-3.0**（该仓库 LICENSE 为 GPLv3）。本仓库同为 GPL-3.0，兼容。
- 字段：`机车型号,起号,止号,配属单位(路局/机务段),备注,制造厂`
- 已知数据缺口：3 行配属为空（原表即缺），界面显示为「原表未标注配属」，不做臆测填充。
- 更新方式：替换该 CSV 后运行 `python tools/gen_shared_data.py` 重新校验。
- **致谢**：本项目的「机车配属查询」、地图弹窗与解码页的「配属单位」全部建立在该表之上；
  此外安卓端五页导航 + 悬浮玻璃 Dock 的界面骨架、OSM + OpenRailwayMap 的地图图源组合、
  本地矢量铁路层（本项目 `rail_local.geojson`）的离线兜底思路，均参考 LBJ_Console 的实现。
  感谢 undef-i 及其贡献者以 GPL-3.0 开放这些数据与代码。

### 2.1 信号瀑布图（v3.2.8 参考其算法）

安卓端「信号瀑布」的实现方式参考了 LBJ_Console 的
`lib/widgets/audio_waterfall_widget.dart`（GPL-3.0）：

| 参考点 | 本项目实现 |
|---|---|
| `poolSpectrumToWidth()`：频谱 bin 池化到屏幕宽度时**取区间最大值**（保峰，避免窄带峰被插值抹平） | `DecodePage.buildWaterfallBitmap()` 的横向 max-pooling |
| `_intensityToArgb()` + 256 级 `_colorLUT`：深蓝 → 蓝 → 青 → 绿 → 黄 → 红 | `DecodePage.spectrumColor()` 同款光谱色阶 |
| `pixels.setRange` 整体上移一行 + 新行写顶部（瀑布滚动） | 新帧追加、旧帧淘汰的环形帧缓存 |
| 定时器拉帧 + `ui.decodeImageFromPixels` 位图绘制 | `StatusFramePoller`（70 ms）+ `Bitmap.setPixels` + 后台线程 |

差异：本项目的频谱是**射频窄带 FFT（32 bin，native 输出）**，而 LBJ_Console 是
**音频解调后的频谱（多协议条带、bin 数更多）**，因此本项目额外做了纵向帧间插值
与对数动态范围压缩以适配本地信噪比；原始分辨率仍受 native `kSpectrumBins` 限制。

## 3. 机车类型代号表 —— `shared/data/loco_types.csv`

- 由 `tools/gen_shared_data.py` 生成，不手工编辑。
- `code`（LBJ 报文里的机车类型代号）与 `shortCode` 部分来自 LBJ_Console 的 `loco_type_info.csv`
  （GPL-3.0，同上）；`name` 来自本项目解码器 `desktop/cr_lbj/core/decoder.py` 的 `LOCO_TABLE`
  （历代实测积累 + TB/T 3504 相关公开资料）。

## 4. 机型技术参数 —— `shared/data/loco_specs.json`

- 由 `desktop/cr_lbj/data/loco_info.py` 导出（`tools/gen_shared_data.py` 生成，不手工编辑）。
- 参数口径与来源见该文件头注释（中车官网产品页、维基百科、百度百科、Trainfanz 等公开资料，
  2026-11-25 联网核对过轴式/功率/构造速度）。**仅供参考**。

## 5. 预设中心点 —— `shared/data/places.csv`

- 本项目自行整理的**城市中心近似坐标**（WGS-84，约 1 km 量级误差），仅用于把地图视野带到某地，
  不是车站精确位置。可自由增删。

## 6. 地图瓦片与图源（运行时联网获取，不随仓库分发）

v3.1 起底图按服务商分 4 类（高德 / 百度 / OSM / 天地图），共 **7 张**（各家街道/影像分别登记）；
其余（Esri/CARTO/OpenTopoMap/腾讯）已删除。

| 图源 | 用途 | 坐标基准 | 授权/条款要点 |
|---|---|---|---|
| 高德地图（街道/卫星，免 Key 公开瓦片） | 底图（默认街道） | GCJ-02 | © 高德地图 AutoNavi；公开瓦片为 Web 服务，正式分发/商用请按高德开放平台条款申请 Key 使用 |
| 百度地图（街道/卫星，免 Key 公开瓦片） | 底图 | BD-09 + 百度自有墨卡托 | © 百度地图；公开瓦片为 Web 服务，正式分发/商用请按百度地图开放平台条款申请 |
| 天地图（需自备 tk + Referer 白名单） | 底图 | CGCS2000（工程上等同 WGS-84） | 国家地理信息公共服务平台，需注册并按条款使用 |
| OpenStreetMap 标准瓦片 | 底图 | WGS-84 | 数据 © OpenStreetMap contributors（ODbL）；**瓦片使用政策**要求可识别 User-Agent、禁止批量预取、禁止绕过限流（[政策原文](https://operations.osmfoundation.org/policies/tiles/)）。本程序 v3.2.2 起按其要求发 `CR-LBJ-Receiver/x.y.z (+仓库地址)` UA，且不对该图源做批量缓存 |
| **OpenRailwayMap** | **铁路图层** | WGS-84 | 数据 © OpenStreetMap contributors（ODbL），渲染 © OpenRailwayMap（CC-BY-SA）；官方瓦片为**非商业公益服务**，要求应用公开免费、须发唯一 User-Agent、**不得伪造 Referer**、禁止预取与批量抓取，官方可无预警封禁。本程序 v3.2.2 起发合规 UA、不加伪造 Referer、不做批量预取 |
| 本地铁路线 `rail_local.geojson`（可选，不随仓库分发） | 铁路图层离线兜底 | WGS-84 | 用户自建（Geofabrik/OSM 提取，ODbL），见 [地图与图源](地图与图源.md) |

> ⚠️ **OSM / ORM 合规说明（v3.2.2 整改，必读）**
>
> 这两家是志愿者运营的公益瓦片服务，**不是免费 CDN**。我们曾因「伪装浏览器 UA + 缓存本区域
> 批量预取」被 OSM 返回 **418 `Access blocked`** 封禁（`http://osm.wiki/Blocked`）。
> 现已整改为：
>
> 1. 仅对 OSM/ORM 使用可识别 UA `CR-LBJ-Receiver/x.y.z (+https://github.com/liujitong/CR_LBJ_Receiver)`；
> 2. 「缓存本区域」对这两个图源**直接禁用**（浏览时的被动缓存保留，属正常使用）；
> 3. 不再伪造 ORM 的 Referer。
>
> 如需整片离线地图，请改用天地图/高德/百度底图做缓存，或自建瓦片。

> ⚠️ OpenRailwayMap 官方瓦片服务器在中国大陆常被 TLS 阻断，且其条款要求「公开免费的应用」。
> 若用于内部/商用分发，请自建瓦片（见 [地图与图源](地图与图源.md) 的「自建 / 离线铁路图层」一节），
> 不要长期直连官方服务器。
>
> ⚠️ 高德/百度的「免 Key 瓦片」是两家面向自家 Web 产品的公开服务端点，本程序仅作个人使用接入；
> 对外分发或商用请走各家开放平台的正式授权方式。

## 7. 车次数据接口（运行时联网获取）

| 接口 | 用途 | 说明 |
|---|---|---|
| `data.railgo.zenglingkun.cn/api/train/query` | 车次查询（等级/担当/配属/车型/时刻表/交路） | 个人托管服务，零鉴权、CORS `*`；可用性无保证，失败自动退回 12306 |
| `search.12306.cn` + `kyfw.12306.cn` | 车次时刻表（官方口径） | 铁路 12306 公开查询接口；请控制频率，勿批量抓取 |
| `api.rail.re`（**未接入**） | 车组号 ↔ 车次互查 | 接口存在性有第三方客户端代码佐证，但本环境无法验证响应结构，暂不接入 |

## 8. 其它

- 应用图标 `desktop/国铁.ico`、界面主题色（CR 红 `#DA291C` / CR 蓝 `#003DA5`）为本项目素材。
- `android/app/src/main/cpp/thirdparty/libusb`（LGPL-2.1）与 `librtlsdr`（GPL-2.0）各自带
  LICENSE 文件，随源码分发。
