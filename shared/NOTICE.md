# 第三方资源与授权说明（v3.2）

本仓库 `shared/` 目录存放**桌面端与安卓端共用**的地图页与数据文件。以下逐项说明来源与授权，
分发（尤其是打包成 exe / apk 对外发布）时请保留本文件与各项目自带的 LICENSE。

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

v3.1 按用户要求只保留 4 类底图（高德/百度/OSM/天地图），其余（Esri/CARTO/OpenTopoMap/腾讯）已删除。

| 图源 | 用途 | 坐标基准 | 授权/条款要点 |
|---|---|---|---|
| 高德地图（街道/卫星，免 Key 公开瓦片） | 底图（默认街道） | GCJ-02 | © 高德地图 AutoNavi；公开瓦片为 Web 服务，正式分发/商用请按高德开放平台条款申请 Key 使用 |
| 百度地图（街道/卫星，免 Key 公开瓦片） | 底图 | BD-09 + 百度自有墨卡托 | © 百度地图；公开瓦片为 Web 服务，正式分发/商用请按百度地图开放平台条款申请 |
| 天地图（需自备 tk + Referer 白名单） | 底图 | CGCS2000（工程上等同 WGS-84） | 国家地理信息公共服务平台，需注册并按条款使用 |
| OpenStreetMap 标准瓦片 | 底图 | WGS-84 | 数据 © OpenStreetMap contributors（ODbL）；瓦片服务有使用政策 |
| **OpenRailwayMap** | **铁路图层** | WGS-84 | 数据 © OpenStreetMap contributors（ODbL），渲染 © OpenRailwayMap（CC-BY-SA）；官方瓦片为**非商业公益服务**，要求应用公开免费、须发唯一 User-Agent、并按官方要求携带 `Referer: https://www.openrailwaymap.org/`（v3.2 起两端宿主已内置），禁止伪造第三方 Referer、预取与批量抓取，官方可无预警封禁 |
| 本地铁路线 `rail_local.geojson`（可选，不随仓库分发） | 铁路图层离线兜底 | WGS-84 | 用户自建（Geofabrik/OSM 提取，ODbL），见 `docs/地图与图源.md` |

> ⚠️ OpenRailwayMap 官方瓦片服务器在中国大陆常被 TLS 阻断，且其条款要求「公开免费的应用」。
> 若用于内部/商用分发，请自建瓦片（见 `docs/地图与图源.md` 的「自建 / 离线铁路图层」一节），
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
