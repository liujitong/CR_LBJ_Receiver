# 第三方资源与授权说明（v3.0）

本仓库 `shared/` 目录存放**桌面端与安卓端共用**的地图页与数据文件。以下逐项说明来源与授权，
分发（尤其是打包成 exe / apk 对外发布）时请保留本文件与各项目自带的 LICENSE。

## 1. Leaflet 1.9.4 —— `shared/web/vendor/leaflet/`

- 来源：npm 包 `leaflet@1.9.4`（`dist/leaflet.js`、`dist/leaflet.css`、`dist/images/*`）
- 授权：**BSD-2-Clause**，全文见 `shared/web/vendor/leaflet/LICENSE`
- 用途：内嵌地图页 `shared/web/railmap.html` 的唯一前端依赖（已本地化，运行时不联网取 JS）

## 2. 机车配属号段表 —— `shared/data/loco_roster.csv`

- 来源：项目 **LBJ_Console**（https://github.com/undef-i/LBJ_Console）的 `resources` 分支
  根目录 `loco_info.csv`，共 16622 行，未做字段改动（仅在文件头补了 4 行注释说明来源与格式）。
- 授权：**GPL-3.0**（该仓库 LICENSE 为 GPLv3）。本仓库同为 GPL-3.0，兼容。
- 字段：`机车型号,起号,止号,配属单位(路局/机务段),备注,制造厂`
- 已知数据缺口：3 行配属为空（原表即缺），界面显示为「原表未标注配属」，不做臆测填充。
- 更新方式：替换该 CSV 后运行 `python tools/gen_shared_data.py` 重新校验。

## 3. 机车类型代号表 —— `shared/data/loco_types.csv`

- 由 `tools/gen_shared_data.py` 生成，不手工编辑。
- `code`（LBJ 报文里的机车类型代号）与 `shortCode` 部分来自 LBJ_Console 的 `loco_type_info.csv`
  （GPL-3.0，同上）；`name` 来自本项目解码器 `cr_lbj/core/decoder.py` 的 `LOCO_TABLE`
  （历代实测积累 + TB/T 3504 相关公开资料）。

## 4. 机型技术参数 —— `shared/data/loco_specs.json`

- 由 `cr_lbj/data/loco_info.py` 导出（`tools/gen_shared_data.py` 生成，不手工编辑）。
- 参数口径与来源见该文件头注释（中车官网产品页、维基百科、百度百科、Trainfanz 等公开资料，
  2026-11-25 联网核对过轴式/功率/构造速度）。**仅供参考**。

## 5. 预设中心点 —— `shared/data/places.csv`

- 本项目自行整理的**城市中心近似坐标**（WGS-84，约 1 km 量级误差），仅用于把地图视野带到某地，
  不是车站精确位置。可自由增删。

## 6. 地图瓦片与图源（运行时联网获取，不随仓库分发）

| 图源 | 用途 | 坐标系 | 授权/条款要点 |
|---|---|---|---|
| OpenStreetMap 标准瓦片 | 底图 | WGS-84 | 数据 © OpenStreetMap contributors，ODbL；瓦片服务有使用政策 |
| CARTO Basemaps | 底图 | WGS-84 | © OpenStreetMap contributors &copy; CARTO，需署名 |
| Esri World Imagery / Street | 底图 | WGS-84 | © Esri 及其数据提供方，需署名 |
| OpenTopoMap | 底图 | WGS-84 | © OpenStreetMap contributors, SRTM \| © OpenTopoMap (CC-BY-SA) |
| 天地图（需自备 tk） | 底图 | CGCS2000（工程上等同 WGS-84） | 国家地理信息公共服务平台，需注册并按条款使用 |
| 高德地图（GCJ-02） | 底图（应急） | **GCJ-02** | © 高德地图 AutoNavi；正式分发应走高德开放平台授权 |
| **OpenRailwayMap** | **铁路图层** | WGS-84 | 数据 © OpenStreetMap contributors（ODbL），渲染 © OpenRailwayMap（CC-BY-SA）；官方瓦片为**非商业公益服务**，要求应用公开免费、须发唯一 User-Agent、禁止预取与伪造 Referer，官方可无预警封禁 |

> ⚠️ OpenRailwayMap 官方瓦片服务器在中国大陆常被 TLS 阻断，且其条款要求「公开免费的应用」。
> 若用于内部/商用分发，请自建瓦片（见 `docs/地图与图源.md` 的「自建 / 离线铁路图层」一节），
> 不要长期直连官方服务器。

## 7. 车次数据接口（运行时联网获取）

| 接口 | 用途 | 说明 |
|---|---|---|
| `data.railgo.zenglingkun.cn/api/train/query` | 车次查询（等级/担当/配属/车型/时刻表/交路） | 个人托管服务，零鉴权、CORS `*`；可用性无保证，失败自动退回 12306 |
| `search.12306.cn` + `kyfw.12306.cn` | 车次时刻表（官方口径） | 铁路 12306 公开查询接口；请控制频率，勿批量抓取 |
| `api.rail.re`（**未接入**） | 车组号 ↔ 车次互查 | 接口存在性有第三方客户端代码佐证，但本环境无法验证响应结构，暂不接入 |

## 8. 其它

- 应用图标 `国铁.ico`、界面主题色（CR 红 `#DA291C` / CR 蓝 `#003DA5`）为本项目素材。
- `android/app/src/main/cpp/thirdparty/libusb`（LGPL-2.1）与 `librtlsdr`（GPL-2.0）各自带
  LICENSE 文件，随源码分发。
