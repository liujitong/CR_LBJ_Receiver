# -*- coding: utf-8 -*-
"""共享地图页（shared/web/railmap.html）的结构与语法测试。

重点防三类回归：
    1. Leaflet 被换回 CDN（离线/内网就白屏）；
    2. 铁路上游地址被写错（官方域名带 {s}.tiles. 前缀，电气化样式名是 electrified）；
    3. 桌面/安卓注入的配置键与页面默认配置对不上（键名改了但一端没跟）。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, 'shared', 'web')
HTML = os.path.join(WEB, 'railmap.html')

REQUIRED_CONFIG_KEYS = {
    'base', 'rail', 'railOpacity', 'night', 'zoom', 'follow', 'showTrail',
    'tdtKey', 'center', 'colors',
}
REQUIRED_API = {
    'update', 'focus', 'clear', 'setFollow', 'locked', 'center', 'setNight',
    'isNight', 'centerTo', 'resize', 'setBase', 'setRailStyle', 'railOpacity',
    'status', 'layers', 'applyConfig',
}


def read_html() -> str:
    with open(HTML, 'r', encoding='utf-8') as f:
        return f.read()


def inline_js(text: str) -> str:
    blocks = re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', text, re.S)
    return '\n'.join(blocks)


def config_keys(text: str) -> set:
    m = re.search(r'var DEFAULT_CONFIG = \{(.*?)\n  \};', text, re.S)
    if not m:
        return set()
    body = m.group(1)
    return set(re.findall(r'^\s{4}([A-Za-z_]\w*)\s*:', body, re.M))


def api_keys(text: str) -> set:
    m = re.search(r'var api = \{(.*?)\n  \};\s*\n  window\.LBJ = api;', text, re.S)
    if not m:
        return set()
    return set(re.findall(r'^\s{4}([A-Za-z_]\w*)\s*:', m.group(1), re.M))


class MapPageStructureTest(unittest.TestCase):
    def setUp(self):
        self.text = read_html()

    def test_vendored_leaflet(self):
        self.assertIn('vendor/leaflet/leaflet.js', self.text)
        self.assertIn('vendor/leaflet/leaflet.css', self.text)
        for name in ('leaflet.js', 'leaflet.css', 'images/marker-icon.png'):
            p = os.path.join(WEB, 'vendor', 'leaflet', name.replace('/', os.sep))
            self.assertTrue(os.path.exists(p), '缺少本地化 Leaflet 文件 %s' % name)

    def test_no_cdn(self):
        for cdn in ('unpkg.com', 'cdn.jsdelivr.net', 'bootcdn', 'baomitu', 'cdnjs'):
            self.assertNotIn(cdn, self.text, '地图页不应依赖 CDN：%s' % cdn)

    def test_orm_urls(self):
        # 官方域名是 {s}.tiles.openrailwaymap.org；样式名 electrified（不是 electrification）
        orm_urls = re.findall(r"https://[^\s'\"]*openrailwaymap[^\s'\"]*", self.text)
        # 只挑瓦片模板（带 {z}/{x}/{y}），署名链接 https://www.openrailwaymap.org/ 不算
        orm_tiles = [u for u in orm_urls if '{z}/{x}/{y}' in u]
        self.assertTrue(orm_tiles, '应至少有一个 OpenRailwayMap 瓦片地址')
        for u in orm_tiles:
            self.assertIn('{s}.tiles.openrailwaymap.org', u, 'ORM 域名写法不对：%s' % u)
            self.assertNotIn('electrification', u)
        for style in ('standard', 'maxspeed', 'signals', 'electrified', 'gauge'):
            self.assertIn('/%s/{z}/{x}/{y}.png' % style, self.text, '缺少 ORM 样式 %s' % style)

    def test_config_placeholder(self):
        self.assertIn('/*__LBJ_CONFIG_START__*//*__LBJ_CONFIG_END__*/', self.text,
                      '桌面端靠这一行注入配置，别改标记')

    def test_config_keys(self):
        keys = config_keys(self.text)
        missing = REQUIRED_CONFIG_KEYS - keys
        self.assertFalse(missing, 'DEFAULT_CONFIG 缺键：%s' % sorted(missing))

    def test_api_surface(self):
        keys = api_keys(self.text)
        missing = REQUIRED_API - keys
        self.assertFalse(missing, 'LBJ API 缺方法：%s' % sorted(missing))

    def test_coordinate_guard(self):
        # GCJ 底图与 WGS 铁路图层不能混叠：页面必须有这条保护
        self.assertIn('coord: \'gcj\'', self.text)
        self.assertIn('wgs2gcj', self.text)

    def test_host_hook(self):
        self.assertIn('window.LBJHost', self.text, '图层变化要能回报宿主')

    def test_notice_exists(self):
        p = os.path.join(ROOT, 'shared', 'NOTICE.md')
        self.assertTrue(os.path.exists(p), '缺少 shared/NOTICE.md（第三方授权说明）')
        with open(p, 'r', encoding='utf-8') as f:
            notice = f.read()
        for k in ('Leaflet', 'OpenRailwayMap', 'LBJ_Console', 'GPL-3.0'):
            self.assertIn(k, notice)


class MapPageSyntaxTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), '本机没有 node，跳过 JS 语法检查')
    def test_js_syntax(self):
        js = inline_js(read_html())
        self.assertTrue(js.strip(), '没找到内联脚本')
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

    @unittest.skipUnless(shutil.which('node'), '本机没有 node，跳过 JS 语法检查')
    def test_config_injection_is_valid_js(self):
        """模拟桌面端注入：把占位行替换成 INJECTED = {...}; 后语法仍需成立。"""
        text = read_html()
        cfg = {'base': 'osm', 'rail': 'orm_standard', 'railOpacity': 0.85,
               'night': True, 'zoom': 11, 'follow': True, 'showTrail': True,
               'tdtKey': '', 'center': {'lat': 28.68, 'lng': 115.86},
               'colors': {'up': '#4C8DFF', 'down': '#F0604F', 'unknown': '#E0A400'}}
        injected = text.replace('/*__LBJ_CONFIG_START__*//*__LBJ_CONFIG_END__*/',
                                'INJECTED = %s;' % json.dumps(cfg))
        js = inline_js(injected)
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


if __name__ == '__main__':
    unittest.main()
