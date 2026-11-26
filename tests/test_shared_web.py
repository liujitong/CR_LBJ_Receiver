# -*- coding: utf-8 -*-
"""共享地图页（shared/web/railmap.html）v3.1 的结构与契约测试。

v3.1 地图方案（用户最终指定，与代码逐条对应）：

    * 渲染引擎 = **Leaflet 1.9.4**，本地化在 shared/web/vendor/leaflet/，无 CDN；
      vendor/maplibre-gl 已删除、页面不得再引用；
    * 底图 = **7 张**（BASE_SOURCES）：高德街道/卫星、百度街道/卫星（4 张免 Key）、
      OSM、天地图矢量/影像（需 tk）；默认 amap；
    * 坐标系三类：wgs / gcj / bd（百度自定义墨卡托 CRS + 专用瓦片编号）；
    * 离线缓存：页面「缓存本区域」→ LBJHost.cacheArea，进度 LBJ.onCacheProgress，
      占用 LBJ.cacheStats；宿主不支持时降级为图片预取；
    * 天地图 tk 用 {key} 占位、页面不硬编码；Referer 由两端宿主在网络层附加。

本文件重点防的回归：
    1. 渲染引擎被换回（或页面重新引用已删除的 vendor 目录）、引入 CDN；
    2. 底图 id/中文名与 config_ext.BASE_LAYERS 不再逐字一致（工具栏/配置页与页面对不上）；
    3. 百度 BD-09 的 CRS/瓦片换算、GCJ/BD 的偏移函数丢失（标记整体偏 300~500 m）；
    4. 离线缓存 / LBJHost / centerLatLng 契约丢失；
    5. 旧图源（国外底图/腾讯）或硬编码 tk 回流；
    6. 页面内联 JS 语法坏掉（node --check），或配置注入后语法坏掉。
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, 'shared', 'web')
HTML = os.path.join(WEB, 'railmap.html')
DESKTOP = os.path.join(ROOT, 'desktop')
DESKTOP_UI = os.path.join(DESKTOP, 'cr_lbj', 'ui')
DOCS = os.path.join(ROOT, 'docs')

#: v3.1 底图清单（id 与「逐字中文名」）。
#: 名字必须与 railmap.html 的 BASE_SOURCES[*].name 完全一致。
EXPECTED_BASE_LAYERS = {
    'amap': '高德 街道（免 Key）',
    'amap_img': '高德 卫星（免 Key）',
    'baidu': '百度 街道（免 Key）',
    'baidu_sat': '百度 卫星（免 Key）',
    'osm': 'OSM 标准',
    'tdt_vec': '天地图 矢量（CGCS2000）',
    'tdt_img': '天地图 影像（CGCS2000）',
}
DEFAULT_BASE = 'amap'
TDT_LAYERS = {'tdt_vec', 'tdt_img'}
RAIL_STYLES = ('standard', 'maxspeed', 'signals', 'electrified', 'gauge')

#: 页面 DEFAULT_CONFIG 必须有的键（宿主注入/applyConfig 依赖）。
REQUIRED_CONFIG_KEYS = {
    'base', 'rail', 'railOpacity', 'night', 'zoom', 'follow', 'showTrail',
    'tdtKey', 'cacheEnabled', 'cacheZoomDelta', 'center', 'colors',
}
#: 对外 API 契约（桌面 map_host.py / 安卓 MapPage.kt 都按这个调用）。
REQUIRED_API = {
    'update', 'pushTrain', 'focus', 'clear', 'setFollow', 'follow', 'locked',
    'unlock', 'center', 'setNight', 'isNight', 'centerTo', 'centerLatLng',
    'resize', 'setBase', 'base', 'setRailway', 'setRailStyle', 'railOpacity',
    'rail', 'coordMode', 'status', 'layers', 'applyConfig', 'ready',
}
#: 旧图源/旧引擎残留（页面与桌面源码都不该出现）。
BANNED_SOURCES = ('esri', 'carto', 'opentopo', 'tencent', 'maplibre')


def read_text(path: str) -> str:
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def read_html() -> str:
    return read_text(HTML)


def read_ui(name: str) -> str:
    return read_text(os.path.join(DESKTOP_UI, name))


def inline_js(text: str) -> str:
    blocks = re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', text, re.S)
    return '\n'.join(blocks)


def config_keys(text: str) -> set:
    m = re.search(r'var DEFAULT_CONFIG = \{(.*?)\n  \};', text, re.S)
    if not m:
        return set()
    return set(re.findall(r'^\s{4}([A-Za-z_]\w*)\s*:', m.group(1), re.M))


def api_keys(text: str) -> set:
    m = re.search(r'var api = \{(.*?)\n  \};\s*\n  window\.LBJ = api;', text, re.S)
    if not m:
        return set()
    return set(re.findall(r'^\s{4}([A-Za-z_]\w*)\s*:', m.group(1), re.M))


def base_sources(text: str) -> dict:
    """解析 BASE_SOURCES 登记表 → {id: 中文名}（页面格式固定，4 空格缩进）。"""
    m = re.search(r'var BASE_SOURCES = \{(.*?)\n  \};', text, re.S)
    if not m:
        return {}
    out = {}
    for block in re.split(r'\n    (?=[A-Za-z_]\w*: \{)', m.group(1)):
        idm = re.match(r'([A-Za-z_]\w*): \{', block)
        nm = re.search(r"name: '([^']*)'", block)
        if idm and nm:
            out[idm.group(1)] = nm.group(1)
    return out


def base_source_blocks(text: str) -> dict:
    """解析 BASE_SOURCES 每个 id 的完整登记块（用于查 coord / url / 级别）。"""
    m = re.search(r'var BASE_SOURCES = \{(.*?)\n  \};', text, re.S)
    if not m:
        return {}
    out = {}
    for block in re.split(r'\n    (?=[A-Za-z_]\w*: \{)', m.group(1)):
        idm = re.match(r'([A-Za-z_]\w*): \{', block)
        if idm:
            out[idm.group(1)] = block
    return out


def load_config_ext():
    """按文件路径导入 config_ext（不依赖包内其它模块、不触发 Qt）。"""
    path = os.path.join(DESKTOP_UI, 'config_ext.py')
    spec = importlib.util.spec_from_file_location('_crlbj_config_ext_test', path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, DESKTOP)      # install() 会尝试 import cr_lbj.core.decoder
    try:
        spec.loader.exec_module(mod)
    finally:
        try:
            sys.path.remove(DESKTOP)
        except ValueError:
            pass
    return mod


class MapPageStructureTest(unittest.TestCase):
    def setUp(self):
        self.text = read_html()
        self.low = self.text.lower()

    # ---------------- 渲染引擎 ----------------
    def test_vendored_leaflet(self):
        self.assertIn('vendor/leaflet/leaflet.js', self.text)
        self.assertIn('vendor/leaflet/leaflet.css', self.text)
        for name in ('leaflet.js', 'leaflet.css', 'LICENSE'):
            p = os.path.join(WEB, 'vendor', 'leaflet', name)
            self.assertTrue(os.path.exists(p), '缺少本地化 Leaflet 文件 %s（页面会白屏）' % name)
        # 上一轮 WebGL 引擎的 vendor 目录必须已删除，页面不许残留引用
        self.assertFalse(os.path.exists(os.path.join(WEB, 'vendor', 'maplibre-gl')),
                         'vendor/maplibre-gl 应已删除')
        self.assertNotIn('maplibre', self.low, '页面不应再引用旧渲染引擎')

    def test_no_cdn(self):
        for cdn in ('unpkg.com', 'cdn.jsdelivr.net', 'bootcdn', 'baomitu', 'cdnjs'):
            self.assertNotIn(cdn, self.text, '地图页不应依赖 CDN：%s' % cdn)

    # ---------------- 底图清单 ----------------
    def test_base_sources_exactly_seven(self):
        layers = base_sources(self.text)
        self.assertEqual(len(layers), 7, 'BASE_SOURCES 应恰有 7 张底图，实际：%s' % sorted(layers))
        self.assertEqual(set(layers), set(EXPECTED_BASE_LAYERS),
                         'BASE_SOURCES id 与 v3.1 约定不一致：%s' % sorted(layers))

    def test_base_names_match_config_ext(self):
        layers = base_sources(self.text)
        self.assertEqual(layers, EXPECTED_BASE_LAYERS,
                         '页面底图中文名必须与 v3.1 约定逐字一致')
        ext = load_config_ext()
        self.assertEqual(dict(ext.BASE_LAYERS), EXPECTED_BASE_LAYERS,
                         'config_ext.BASE_LAYERS 与页面 BASE_SOURCES 不逐字一致')
        self.assertEqual(len(ext.BASE_LAYERS), 7)
        self.assertEqual(set(ext.TDT_LAYERS), TDT_LAYERS)

    def test_default_base_is_amap(self):
        m = re.search(r'var DEFAULT_CONFIG = \{.*?base: \'(\w+)\'', self.text, re.S)
        self.assertTrue(m, 'DEFAULT_CONFIG.base 缺失')
        self.assertEqual(m.group(1), DEFAULT_BASE,
                         '默认底图应为高德街道（实测最快最稳 + 免 Key）')
        cfg_path = os.path.join(DESKTOP, 'lbj_config.json')
        cfg = json.loads(read_text(cfg_path))
        self.assertEqual(cfg.get('mapBase'), DEFAULT_BASE,
                         '桌面配置模板 mapBase 应与页面默认一致')

    def test_base_coord_and_key(self):
        blocks = base_source_blocks(self.text)
        self.assertEqual(len(blocks), 7)
        for lid, block in blocks.items():
            self.assertIn('coord:', block, '底图 %s 缺少 coord 声明' % lid)
            self.assertIn('url:', block, '底图 %s 缺少 url' % lid)
            if lid in TDT_LAYERS:
                self.assertIn('{key}', block, '天地图 %s 应使用 {key} 占位' % lid)
                self.assertIn('coord: \'wgs\'', block)
            elif lid.startswith('amap'):
                self.assertIn('coord: \'gcj\'', block, '%s 应为 GCJ-02' % lid)
            elif lid.startswith('baidu'):
                self.assertIn('coord: \'bd\'', block, '%s 应为 BD-09' % lid)
            else:
                self.assertIn('coord: \'wgs\'', block, '%s 应为 WGS-84' % lid)

    def test_no_hardcoded_tdt_tk(self):
        # 页面只留 {key} 占位；32 位十六进制 tk 不许写死在页面里
        self.assertIn('{key}', self.text)
        hard = re.findall(r'tk=[0-9a-fA-F]{24,}', self.text)
        self.assertFalse(hard, '页面不应硬编码天地图 tk：%s' % hard[:2])
        # 页面模板里出现 tk= 时必须是空值或 {key}
        for m in re.finditer(r'[?&]tk=([^&\'\s]*)', self.text):
            self.assertIn(m.group(1), ('', '{key}'), '天地图 tk 参数写法不对：%r' % m.group(0))

    # ---------------- 坐标系与百度 CRS ----------------
    def test_coord_transforms(self):
        for fn in ('wgs2gcj', 'gcj2wgs', 'gcj2bd', 'bd2gcj', 'wgs2bd',
                   'function toMap(', 'function fromMap('):
            self.assertIn(fn, self.text, '缺少坐标换算函数：%s' % fn)

    def test_baidu_custom_crs(self):
        for token in ('L_BAIDU_CRS', 'BaiduTileLayer', 'll2mc', 'mc2ll',
                      'LL2MC', 'MC2LL', 'getTileUrl'):
            self.assertIn(token, self.text, '缺少百度自定义 CRS 组件：%s' % token)
        # 百度瓦片编号换算：世界中心为原点
        self.assertIn('Math.pow(2, coords.z - 1)', self.text,
                      '百度瓦片编号换算（x-offset / offset-y-1）丢失')
        # 标准墨卡托 ↔ 百度墨卡托要重建地图实例
        self.assertIn('needRecreate', self.text,
                      '切换百度 CRS 时必须重建地图实例')
        self.assertIn("opts.crs = L_BAIDU_CRS", self.text,
                      '百度底图必须给 L.map 传自定义 CRS')

    def test_coord_mode_three_kinds(self):
        self.assertIn("function coordMode()", self.text)
        self.assertIn("'bd'", self.text)
        self.assertIn("'gcj'", self.text)
        # 偏移坐标系底图下不叠 WGS-84 铁路图层
        self.assertIn('isOffsetBase()', self.text)
        self.assertIn('铁路图层已暂停', self.text)

    # ---------------- 铁路图层 ----------------
    def test_orm_urls_and_styles(self):
        orm_urls = re.findall(r"https://[^\s'\"]*openrailwaymap[^\s'\"]*", self.text)
        orm_tiles = [u for u in orm_urls if '{z}/{x}/{y}' in u]
        self.assertTrue(orm_tiles, '应至少有一个 OpenRailwayMap 瓦片地址')
        for u in orm_tiles:
            self.assertIn('{s}.tiles.openrailwaymap.org', u, 'ORM 域名写法不对：%s' % u)
            self.assertNotIn('electrification', u)
        for style in RAIL_STYLES:
            self.assertIn('/%s/{z}/{x}/{y}.png' % style, self.text, '缺少 ORM 样式 %s' % style)

    # ---------------- 配置 / API / 宿主契约 ----------------
    def test_config_placeholder(self):
        self.assertIn('/*__LBJ_CONFIG_START__*//*__LBJ_CONFIG_END__*/', self.text,
                      '桌面端靠这一行注入配置，别改标记')

    def test_config_keys(self):
        missing = REQUIRED_CONFIG_KEYS - config_keys(self.text)
        self.assertFalse(missing, 'DEFAULT_CONFIG 缺键：%s' % sorted(missing))

    def test_api_surface(self):
        missing = REQUIRED_API - api_keys(self.text)
        self.assertFalse(missing, 'LBJ API 缺方法：%s' % sorted(missing))
        # 这几个在 api 对象字面量之外挂载（缓存回调 / 显式居中 / 旧名兼容）
        for extra in ('api.setCenter', 'api.onCacheProgress', 'api.cacheStats',
                      'api.refreshCacheStats', 'window.updateTrain'):
            self.assertIn(extra, self.text, '缺少 API 入口：%s' % extra)
        # status() 的瓦片统计字段（两端轮询都读它）
        self.assertIn('tilesTotal', self.text)
        self.assertIn('tilesFailed', self.text)

    def test_center_latlng_contract(self):
        # 「转到本机位置」：WGS-84 入参、居中、停止自动跟随
        self.assertIn('centerLatLng: function', self.text)
        self.assertIn('已转到本机位置', self.text)

    def test_cache_contract(self):
        for token in ('缓存本区域', 'cacheArea', 'onCacheProgress', 'cacheStats',
                      'cacheZoomDelta', 'prefetchLocal'):
            self.assertIn(token, self.text, '缺少离线缓存契约：%s' % token)
        # 宿主支持就交宿主落盘，否则降级预取
        self.assertIn('window.LBJHost', self.text)
        self.assertIn('host.cacheArea', self.text)
        self.assertIn('host.cacheStats', self.text)

    def test_host_onlayers_contract(self):
        self.assertIn('LBJHost', self.text, '图层变化要能回报宿主')
        self.assertIn('onLayers', self.text)
        for key in ('base', 'rail', 'railOpacity', 'night'):
            self.assertIn(key, self.text)

    # ---------------- 清理项 ----------------
    def test_no_legacy_sources(self):
        for bad in BANNED_SOURCES:
            self.assertNotIn(bad, self.low,
                             '页面不应再有 v3.1 之前的图源/引擎残留：%s' % bad)

    def test_desktop_source_no_legacy_sources(self):
        for dirpath, _dirnames, filenames in os.walk(os.path.join(DESKTOP, 'cr_lbj')):
            for name in filenames:
                if not name.endswith('.py'):
                    continue
                low = read_text(os.path.join(dirpath, name)).lower()
                for bad in BANNED_SOURCES:
                    self.assertNotIn(bad, low,
                                     '%s 不应有旧图源/引擎残留：%s' % (name, bad))


class DesktopHostContractTest(unittest.TestCase):
    """桌面宿主与页面之间的关键约定（只读源码，不导入 Qt）。"""

    def test_local_content_can_access_remote_urls(self):
        # v3.1 关键修复：QtWebEngine 默认拦 file:// 页面的远程瓦片请求
        host = read_ui('map_host.py')
        self.assertIn('LocalContentCanAccessRemoteUrls', host,
                      'map_host 必须显式打开远程内容访问（否则桌面地图不显示）')
        self.assertIn('LocalContentCanAccessFileUrls', host)

    def test_referer_interceptor(self):
        host = read_ui('map_host.py')
        self.assertIn('QWebEngineUrlRequestInterceptor', host)
        self.assertIn('tianditu.gov.cn', host)
        self.assertIn('bdimg.com', host)
        self.assertIn('map.baidu.com', host)
        self.assertIn('tdtReferer', host)
        # v3.2.2 合规整改：OSM / ORM 要求可识别 UA（伪装浏览器会被 418 封禁）
        self.assertIn('APP_UA', host)
        self.assertIn("b'User-Agent'", host)
        self.assertIn('openstreetmap.org', host)
        self.assertIn('openrailwaymap.org', host)
        # 政策不允许伪造 ORM Referer，已移除
        self.assertNotIn('ORM_REFERER', host,
                         'ORM 不允许伪造 Referer（其政策要求真实来源）')
        # setHttpHeader 的 header 名必须是 bytes（传 str 静默失效，踩过坑）
        self.assertIn("b'Referer'", host)
        ext = read_ui('config_ext.py')
        self.assertIn("'tdtKey'", ext)
        self.assertIn("'tdtReferer'", ext)

    def test_osm_policy_compliance(self):
        """v3.2.2：OSM/ORM 使用政策合规（可识别 UA + 禁止批量预取）。"""
        cache = read_text(os.path.join(
            ROOT, 'android', 'app', 'src', 'main', 'java', 'xyz', 'mlxkj',
            'crlbj', 'core', 'TileCache.kt'))
        self.assertIn('CR-LBJ-Receiver/', cache, '必须用含应用名的可识别 UA')
        self.assertIn('isPolicyStrictHost', cache, 'OSM/ORM 需要单独判定')
        self.assertIn('userAgentFor', cache)
        self.assertNotIn('https://www.openrailwaymap.org/', cache,
                         '不应再伪造 ORM Referer')
        mappage = read_text(os.path.join(
            ROOT, 'android', 'app', 'src', 'main', 'java', 'xyz', 'mlxkj',
            'crlbj', 'ui', 'pages', 'MapPage.kt'))
        self.assertIn('isPolicyStrictHost', mappage,
                      '安卓批量缓存必须过滤 OSM/ORM')
        html = read_html()
        self.assertIn('isPolicyStrictSource', html,
                      '页面「缓存本区域」必须拒绝 OSM/ORM')
        self.assertIn('onCacheBlocked', html)
        self.assertIn('禁止预取', html)

    def test_tile_stats_split_by_layer(self):
        """v3.2：底图/铁路瓦片统计必须分离，否则铁路全挂会把底图误判成不可达。"""
        html = read_html()
        for name in ('baseTileOk', 'baseTileFail', 'railTileOk', 'railTileFail'):
            self.assertIn(name, html, '缺少分图层统计变量 %s' % name)
        self.assertIn("tileHooks(baseLayer, 'base')", html)
        self.assertIn("tileHooks(railLayer, 'rail')", html)
        # 全屏「底图不可达」判定必须只看底图
        self.assertIn('baseTileFail', html)
        self.assertIn('reallyDead', html)
        self.assertNotIn('tilesFailed++', html,
                         '不应再有全局 tilesFailed 计数（会被铁路失败污染）')
        self.assertIn('railTilesTotal', html, 'status() 应暴露铁路瓦片统计')

    def test_orm_referer_in_android_cache(self):
        """v3.2.2：安卓代拉 OSM/ORM 走合规 UA，不再伪造 Referer。"""
        base = os.path.join(ROOT, 'android', 'app', 'src', 'main', 'java',
                            'xyz', 'mlxkj', 'crlbj')
        cache = read_text(os.path.join(base, 'core', 'TileCache.kt'))
        self.assertIn('UA_APP', cache)
        self.assertIn('CR-LBJ-Receiver/', cache)
        self.assertNotIn('https://www.openrailwaymap.org/', cache,
                         '不应伪造 ORM Referer（政策要求真实来源）')

    def test_train_info_display_contract(self):
        """v3.2.1：地图页**不再**标注线路/机车/类别/车次信息/车底/配属。

        这些信息改在宿主面板展示（桌面「车次信息 / 机车信息」卡片、安卓解码卡）；
        页面的 setTrainInfo 仅保留为宿主推送通道，不渲染。
        """
        html = read_html()
        self.assertIn('setTrainInfo', html, '兼容接口应保留（宿主仍会推送）')
        # 弹窗只保留核心行车字段
        self.assertIn('轨迹里程', html)
        # 页面上不应再有信息渲染器与那几行弹窗字段
        self.assertNotIn('infoRows', html, '地图弹窗不应再渲染 info 行')
        self.assertNotIn("['线路'", html, '地图弹窗不应显示线路')
        self.assertNotIn("['机车'", html, '地图弹窗不应显示机车')
        self.assertNotIn("['类别'", html, '地图弹窗不应显示类别')
        # 标记副标题只剩速度/公里标
        self.assertNotIn('info.grade', html, '标记副标题不应再显示车次等级')
        # 桌面：查询服务与信息卡片仍要在（这些信息改在这两处展示）
        lookup = read_ui('info_lookup.py')
        self.assertIn('class TrainInfoService', lookup)
        self.assertIn('train_info', lookup)
        self.assertIn('loco_roster', lookup)
        self.assertIn("'section'", lookup, 'runner → section 映射')
        # 安卓：payload 仍带 info（供宿主面板），解码页展示担当段
        base = os.path.join(ROOT, 'android', 'app', 'src', 'main', 'java',
                            'xyz', 'mlxkj', 'crlbj')
        mappage = read_text(os.path.join(base, 'ui', 'pages', 'MapPage.kt'))
        self.assertIn('trainInfoMap', mappage)
        decode = read_text(os.path.join(base, 'ui', 'pages', 'DecodePage.kt'))
        self.assertIn('ti.runner', decode, '安卓解码页应展示担当段')

    def test_marker_footnote_readability(self):
        """v3.2.1：地图标记下的速度/公里标小字要能看清（字号/底色/描边）。"""
        html = read_html()
        self.assertIn('.lbj-marker .sub', html)
        sub_css = html.split('.lbj-marker .sub', 1)[1].split('}', 1)[0]
        self.assertIn('font-size: 11px', sub_css, '脚注字号应 ≥11px')
        self.assertIn('font-weight: 600', sub_css)
        self.assertIn('text-shadow', sub_css, '脚注需要描边/阴影保证可读')

    def test_config_applied_gate(self):
        """v3.2.1 底图回退 bug：页面在宿主 applyConfig 之前不得上报图层。

        安卓端 file:// 加载时页面先按默认底座(amap)起来；若此时 notifyHost 上报，
        宿主会把它落盘成配置，冲掉用户选的底图。
        """
        html = read_html()
        self.assertIn('configApplied', html)
        self.assertIn('if (!configApplied) return;', html,
                      'notifyHost 必须在 applyConfig 前静默')
        self.assertIn('configApplied = true;', html)

    def test_android_tile_cache_host(self):
        # 安卓侧：原生代拉 + DiskLruCache + LBJHost 桥（v3.1）
        base = os.path.join(ROOT, 'android', 'app', 'src', 'main', 'java',
                            'xyz', 'mlxkj', 'crlbj')
        cache = read_text(os.path.join(base, 'core', 'TileCache.kt'))
        self.assertIn('DiskLruCache', cache)
        self.assertIn('tile_cache', cache)
        self.assertIn('MAX_BYTES', cache)
        self.assertIn('refererFor', cache)
        self.assertIn('map.baidu.com', cache)
        mappage = read_text(os.path.join(base, 'ui', 'pages', 'MapPage.kt'))
        self.assertIn('LBJHost', mappage)
        self.assertIn('shouldInterceptRequest', mappage)


class MapPageSyntaxTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), '本机没有 node，跳过 JS 语法检查')
    def _node_check(self, js: str):
        fd, path = tempfile.mkstemp(suffix='.js')
        os.close(fd)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(js)
            proc = subprocess.run(['node', '--check', path],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    def test_js_syntax(self):
        js = inline_js(read_html())
        self.assertTrue(js.strip(), '没找到内联脚本')
        self._node_check(js)

    def test_config_injection_is_valid_js(self):
        """模拟桌面端注入：把占位行替换成 INJECTED = {...}; 后语法仍需成立。"""
        cfg = {
            'base': 'amap', 'rail': 'orm_standard', 'railOpacity': 0.85,
            'night': True, 'zoom': 11, 'follow': True, 'showTrail': True,
            'trailMax': 240, 'tdtKey': '', 'cacheEnabled': True,
            'cacheZoomDelta': 3,
            'center': {'lat': 28.68, 'lng': 115.86},
            'colors': {'up': '#4C8DFF', 'down': '#F0604F', 'unknown': '#E0A400'},
        }
        text = read_html().replace(
            '/*__LBJ_CONFIG_START__*//*__LBJ_CONFIG_END__*/',
            'INJECTED = %s;' % json.dumps(cfg))
        js = inline_js(text)
        self.assertTrue(js.strip(), '注入配置后没找到内联脚本')
        self._node_check(js)


class DocsVersionTest(unittest.TestCase):
    """发版时文档版本号必须同步（避免文档还停在旧版）。"""

    def test_readme_version(self):
        readme = read_text(os.path.join(ROOT, 'README.md'))
        self.assertIn('v3.2.6', readme, 'README 版本号应为 v3.2.6')
        self.assertNotIn('**版本** v3.0.0', readme)
        self.assertNotIn('**版本** v3.1.0', readme)
        self.assertNotIn('**版本** v3.2.5', readme)
        self.assertIn('v3.2.6', readme.split('## 更新记录', 1)[-1],
                      'README 更新记录表应有 v3.2.6 行')

    def test_docs_version(self):
        for name in ('地图与图源.md', '技术参考.md', '用户手册.md', '架构说明.md'):
            text = read_text(os.path.join(DOCS, name))
            self.assertIn('v3.2.6', text, '%s 文首版本号应为 v3.2.6' % name)
        changelog = read_text(os.path.join(DOCS, 'CHANGELOG.md'))
        self.assertIn('## v3.2.6', changelog, 'CHANGELOG 顶部应有 v3.2.6 条目')


if __name__ == '__main__':
    unittest.main()
