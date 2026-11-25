#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""map_panel.py — 高德地图实时列车位置面板 (PySide6)

依赖:
    PySide6 (Essentials) + PySide6-Addons (提供 QtWebEngine)

设计:
    - 使用高德 JS API 2.0 在 QWebEngineView 中渲染地图
    - Python 侧维护列车位置字典，通过 runJavaScript 推送给页面
    - 未安装 QtWebEngine 或未配置 Key 时自动降级为提示面板

高德 Key 申请: https://console.amap.com/dev/key/app
    服务平台选择 “Web端(JS API)”，同时获得 Key 与安全密钥。
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QUrl, Signal, QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
)

import theme as TH


def _c(key: str, fallback: str = '#888888') -> str:
    """取当前主题色（theme 不可用时退回 fallback）。"""
    return TH.c(key, fallback)


try:  # QtWebEngine 由 PySide6-Addons 提供，缺失时降级
    from PySide6.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
except Exception:  # pragma: no cover - 取决于运行环境
    QWebEngineView = None
    HAS_WEBENGINE = False


_A = 6378245.0
_EE = 0.00669342162296594323


def _out_of_china(lat: float, lon: float) -> bool:
    return not (73.66 < lon < 135.05 and 3.86 < lat < 53.55)


def _transform_lat(x: float, y: float) -> float:
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lon(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return ret


def wgs84_to_gcj02(lat: float, lon: float) -> tuple:
    """WGS-84 -> GCJ-02（高德底图坐标系）。在中国境外原样返回。"""
    if _out_of_china(lat, lon):
        return lat, lon
    dlat = _transform_lat(lon - 105.0, lat - 35.0)
    dlon = _transform_lon(lon - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - _EE * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrtmagic) * math.pi)
    dlon = (dlon * 180.0) / (_A / sqrtmagic * math.cos(radlat) * math.pi)
    return lat + dlat, lon + dlon


_HTML_TEMPLATE = r"""<!DOCTYPE html><html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LBJ 实时位置</title>
<style>
  body.dark {
    --bg: #10161c; --card: #191c21; --text: #d8dee6; --dim: #8c97a3;
    --border: #2b3138; --border-soft: #232a31; --accent: #F0604F; --warn: #F0A020;
    --badge: #003DA5;
  }
  body.light {
    --bg: #f4f6f8; --card: #ffffff; --text: #1b2026; --dim: #5a6572;
    --border: #d5dce4; --border-soft: #e6ebf1; --accent: #DA291C; --warn: #A96500;
    --badge: #003DA5;
  }
  html, body, #map { height: 100%; width: 100%; margin: 0; padding: 0;
    background: var(--bg); overflow: hidden; }
  #hint { position: absolute; left: 50%; top: 46%; transform: translate(-50%,-50%);
    color: var(--text); font: 13px/1.7 "Microsoft YaHei", sans-serif; text-align: center;
    background: var(--card); padding: 14px 18px; border-radius: 6px;
    border: 1px solid var(--border); max-width: 80%; display: none; z-index: 99; }
  #hint b { color: var(--warn); }
  /* 兜底夜间底图：某些 Key 没开「个性化地图」，setMapStyle 会被静默忽略，
     这时给瓦片层加反相滤镜（标记层不参与，颜色不受影响）。 */
  body.nightfall .amap-layer-tile {
    filter: invert(1) hue-rotate(180deg) brightness(.88) contrast(.9) saturate(.7);
  }
  /* ---- 标记：只留车次，速度/公里标为可隐藏的副行 ---- */
  .mk { position: relative; white-space: nowrap;
    font: 11px/1.15 "Microsoft YaHei", sans-serif; text-align: center; }
  .mk .tag { display: inline-block; padding: 2px 6px; border-radius: 3px;
    color: #ffffff; font-weight: 700; font-size: 11px; letter-spacing: .3px;
    box-shadow: 0 1px 4px rgba(0,0,0,.45); border: 1px solid rgba(255,255,255,.35); }
  .mk .sub { display: block; margin-top: 1px; padding: 0 4px; border-radius: 2px;
    background: rgba(10,14,18,.78); color: #dbe6f1; font-size: 9.5px;
    border: 1px solid rgba(255,255,255,.12); }
  .mk.mini .sub { display: none; }          /* 缩小时或互相遮挡时收起副行 */
  .mk.dim { opacity: .62; }                  /* 非最新列车降低存在感 */
  .mk .stem { width: 1px; height: 5px; background: rgba(255,255,255,.55);
    margin: 0 auto; }
  /* 精确点位：锚点就是这颗点，标签浮在它上方，位置不再靠“标签底边猜”。
     width/height 就是 10px，环用 box-shadow 画，所以中心点严格落在 left:50%/bottom:0 上。 */
  .mk .dot { position: absolute; left: 50%; bottom: 0; width: 10px; height: 10px;
    margin-left: -5px; margin-bottom: -5px; border-radius: 50%; box-sizing: border-box;
    background: #fff;
    box-shadow: 0 0 0 2px #ffffff, 0 0 0 3px rgba(0,0,0,.55), 0 0 8px rgba(0,0,0,.5); }
  .mk .dot i { display: block; width: 100%; height: 100%; border-radius: 50%; }

  /* ---- 信息窗：实体卡片，不再是一层透明文字压在底图上 ---- */
  .info { min-width: 208px; max-width: 268px; box-sizing: border-box;
    padding: 10px 12px 11px; border-radius: 8px;
    background: var(--card); color: var(--text); border: 1px solid var(--border);
    box-shadow: 0 8px 26px rgba(0,0,0,.45);
    font: 12px/1.55 "Microsoft YaHei", sans-serif; position: relative; }
  .info::after { content: ''; position: absolute; left: 50%; bottom: -6px;
    width: 10px; height: 10px; margin-left: -5px; transform: rotate(45deg);
    background: var(--card); border-right: 1px solid var(--border); border-bottom: 1px solid var(--border); }
  .info h4 { margin: 0 40px 8px 0; font-size: 15px; color: var(--accent); letter-spacing: .5px; }
  .info .badge { display: inline-block; margin-left: 6px; padding: 0 5px;
    border-radius: 3px; font-size: 10px; font-weight: 600; color: #fff;
    background: var(--badge); vertical-align: 2px; }
  .info .row { display: flex; justify-content: space-between; gap: 12px;
    padding: 1px 0; border-bottom: 1px dashed var(--border-soft); }
  .info .row:last-child { border-bottom: none; }
  .info .k { color: var(--dim); white-space: nowrap; }
  .info .v { color: var(--text); font-weight: 600; text-align: right;
    word-break: break-all; }
  .info .close { position: absolute; right: 6px; top: 4px; width: 18px; height: 18px;
    line-height: 17px; text-align: center; border-radius: 9px; cursor: pointer;
    color: var(--dim); font-size: 14px; }
  .info .close:hover { background: var(--border-soft); color: var(--text); }
  .info .foot { margin-top: 6px; color: var(--dim); font-size: 10px; text-align: right; }
</style>
<script>
  window._AMapSecurityConfig = { securityJsCode: __SECURITY__ };
</script>
<script src="https://webapi.amap.com/maps?v=2.0&key=__KEY__&plugin=AMap.Scale,AMap.ToolBar,AMap.Geocoder"></script>
</head>
<body class="dark">
<div id="map"></div>
<div id="hint"></div>
<script>
(function () {
  var CFG = { zoom: __ZOOM__, follow: __FOLLOW__, showTrail: __TRAIL__, night: __NIGHT__ };
  var CENTER_ADDR = __CENTER_ADDR__;        // 用户填的默认中心（如“南昌站”）
  var CENTER_CACHE = [__CENTER_LNG__, __CENTER_LAT__];   // 上次解析结果，断网时兜底
  var STYLE_DAY = 'amap://styles/normal';
  var STYLE_NIGHT = 'amap://styles/darkblue';
  var COLOR = { '上行': '#4C8DFF', '下行': '#F0604F', '未知': '#E0A400' };
  var THEME = __MAPCOLORS__;   // 由 Python 侧按主题注入
  for (var _k in THEME) { if (THEME[_k]) { COLOR[_k === 'up' ? '上行' : (_k === 'down' ? '下行' : '未知')] = THEME[_k]; } }
  var MIN_ZOOM_SUB = 11.6;     // 低于这个级别不显示副行
  var COLLIDE_PX = 52;         // 标签互相遮挡的像素阈值
  var map = null, info = null, ready = false, pending = null;
  var markers = {}, lines = {}, state = {}, order = [];
  var els = {}, zmap = {};       // 自己记 DOM 元素和 zIndex，不用 Marker 的 getter（2.0 没有）
  var userTouched = false;      // 用户手动拖过/缩过 → 暂停自动跟随
  var lastAuto = null;          // 上次自动居中的坐标，用来判断“车是不是真的动了”

  function markTouched() { userTouched = true; }

  // 默认中心点：把用户填的地名（如“南昌站”）地理编码后居中，**不添加任何标记**
  function resolveCenter(cb) {
    if (!CENTER_ADDR) {
      if (cb) {
        showHint('还没设置默认中心<br>在「配置 → 地图与车次 → 默认中心」里填一个地名，例如：南昌站');
        setTimeout(hideHint, 4200);
        cb(false);
      }
      return;
    }
    var run = function () {
      try {
        var geo = new AMap.Geocoder({ city: '全国', citylimit: false });
        geo.getLocation(CENTER_ADDR, function (status, result) {
          if (status === 'complete' && result.geocodes && result.geocodes.length) {
            var loc = result.geocodes[0].location;      // GCJ-02
            CENTER_CACHE = [loc.lng, loc.lat];
            if (!userTouched) { map.setZoomAndCenter(CFG.zoom, [loc.lng, loc.lat]); }
            if (cb) { cb(true, loc); }
          } else {
            showHint('中心点「' + esc(CENTER_ADDR) + '」没解析出来<br>' +
                     '检查网络，或换个更准确的名字（例：南昌站、杭州东站）');
            setTimeout(hideHint, 5000);
            if (cb) { cb(false); }
          }
        });
      } catch (e) { if (cb) { cb(false); } }
    };
    // Geocoder 是异步按需加载的插件，直接 new 可能还没注入
    if (AMap.plugin) { AMap.plugin('AMap.Geocoder', run); }
    else { run(); }
  }

  function showHint(html) {
    var h = document.getElementById('hint');
    h.innerHTML = html; h.style.display = 'block';
  }
  function hideHint() { document.getElementById('hint').style.display = 'none'; }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function init() {
    if (!window.AMap) {
      showHint('<b>高德地图脚本加载失败</b><br>请检查网络、Key 是否正确，以及安全密钥是否填写。');
      return;
    }
    try {
      // 开机中心：有缓存坐标就用缓存，没有就等地理编码；都没有则全国概览（不再默认北京）
      var startCenter = (CENTER_CACHE[0] && CENTER_CACHE[1]) ? CENTER_CACHE : [104.2, 35.9];
      var startZoom = (CENTER_CACHE[0] && CENTER_CACHE[1]) ? CFG.zoom : 4;
      map = new AMap.Map('map', {
        zoom: startZoom, center: startCenter, viewMode: '2D',
        resizeEnable: true, showLabel: true
        // 不在这里传 mapStyle：样式统一由 applyNight() 设置并校验，
        // 否则 getMapStyle() 只会"记录"构造参数，无法判断是否真的生效
      });
      map.addControl(new AMap.Scale({ position: 'LB' }));
      map.on('zoomend', declutter);
      map.on('moveend', declutter);
      // 只认“人的手势”：程序调用 setZoomAndCenter 不会触发这几个事件，
      // 否则自动跟随会把自己锁死。AMap 的事件名可能因版本而异，
      // 所以再在容器 DOM 上补一层原生监听，双保险。
      map.on('mousedown', markTouched);
      map.on('touchstart', markTouched);
      map.on('mousewheel', markTouched);
      var box = document.getElementById('map');
      if (box) {
        ['mousedown', 'touchstart', 'wheel'].forEach(function (ev) {
          box.addEventListener(ev, markTouched, { passive: true });
        });
      }
      info = new AMap.InfoWindow({ isCustom: true, offset: new AMap.Pixel(0, -34),
                                   autoMove: true, closeWhenClickMap: true });
      ready = true;
      // 探一次夜间样式是否真的生效（没开「个性化地图」的 Key 会被忽略）
      applyNight(CFG.night);
      resolveCenter();
      if (pending) { update(pending); pending = null; }
    } catch (e) {
      showHint('<b>地图初始化失败</b><br>' + esc(e && e.message ? e.message : e));
    }
  }

  function markerEl(t) {
    // 标签只放“谁”，速度/公里标作为副行；缩小时与遮挡时自动收起副行
    var wrap = document.createElement('div');
    wrap.className = 'mk';
    wrap.title = (t.train || '') + '  ' +
                 (t.speed && t.speed !== '---' ? t.speed + ' km/h' : '') +
                 (t.km && t.km !== '---.-' ? '  K' + t.km : '');
    var tag = document.createElement('span');
    tag.className = 'tag';
    var arrow = t.direction === '下行' ? '▼' : (t.direction === '上行' ? '▲' : '•');
    tag.textContent = arrow + ' ' + (t.train || '----');
    tag.style.background = COLOR[t.direction] || COLOR.unknown;
    var sub = document.createElement('span');
    sub.className = 'sub';
    var parts = [];
    if (t.speed && t.speed !== '---') { parts.push(t.speed + ' km/h'); }
    if (t.km && t.km !== '---.-') { parts.push('K' + t.km); }
    if (parts.length) { sub.textContent = parts.join(' · '); }
    else { sub.style.display = 'none'; }
    var stem = document.createElement('div');
    stem.className = 'stem';
    wrap.appendChild(tag); wrap.appendChild(sub); wrap.appendChild(stem);
    var dot = document.createElement('span');
    dot.className = 'dot';
    var inner = document.createElement('i');
    inner.style.background = COLOR[t.direction] || COLOR.unknown;
    dot.appendChild(inner);
    wrap.appendChild(dot);
    return wrap;
  }

  function fmtTime(v) {
    if (!v) { return '--'; }
    var m = String(v).match(/(\d{1,2}:\d{2}:\d{2})/);
    return m ? m[1] : String(v);
  }

  function infoHtml(t) {
    var rows = [
      ['时间', fmtTime(t.time)],
      ['方向', t.direction || '未知'],
      ['速度', (t.speed && t.speed !== '---' ? t.speed + ' km/h' : '---')],
      ['公里标', (t.km && t.km !== '---.-' ? 'K' + t.km : '---')],
      ['线路', t.route || '----'],
      ['机车', t.loco || '----'],
      ['类别', t.category || '----']
    ];
    var n = (t.trail || []).length;
    if (n > 1) {
      rows.push(['轨迹', n + ' 个点' +
                 (t.trailSpan ? ' · ' + t.trailSpan : '')]);
    }
    rows.push(['坐标', (t.wgsLat != null ? t.wgsLat : t.lat).toFixed(5) + ', ' +
                      (t.wgsLon != null ? t.wgsLon : t.lon).toFixed(5)]);
    var badge = t.direction === '上行' ? '上行' : (t.direction === '下行' ? '下行' : '方向未知');
    var color = COLOR[t.direction] || COLOR.unknown;
    var h = '<div class="info"><div class="close" onclick="window.LBJ.closeInfo()">×</div>' +
            '<h4>' + esc(t.train || '----') +
            '<span class="badge" style="background:' + color + '">' + esc(badge) + '</span></h4>';
    rows.forEach(function (r) {
      h += '<div class="row"><span class="k">' + esc(r[0]) + '</span><span class="v">' +
           esc(r[1]) + '</span></div>';
    });
    h += '<div class="foot">WGS-84 原始坐标 · 底图 GCJ-02 已纠偏</div></div>';
    return h;
  }

  function ensureMarker(t) {
    // 越新的报文 zIndex 越高，叠在一起时最新的压在上面
    var z = 100 + Math.min(90, Math.round((t.ts || 0) % 1000));
    var mk = markers[t.id];
    var el = markerEl(t);
    if (!mk) {
      mk = new AMap.Marker({
        position: [t.lon, t.lat], content: el,
        anchor: 'bottom-center', zIndex: z, title: t.train || ''
      });
      mk.on('click', function () {
        var cur = state[t.id];
        if (!cur) { return; }
        info.setContent(infoHtml(cur));
        info.open(map, [cur.lon, cur.lat]);
      });
      map.add(mk);
      markers[t.id] = mk;
    } else {
      mk.setPosition([t.lon, t.lat]);
      // 高德 2.0 的 setter 大小写不统一，两种都试，失败就算了（视觉上只影响叠放顺序）
      try { if (mk.setzIndex) { mk.setzIndex(z); } else if (mk.setZIndex) { mk.setZIndex(z); } } catch (e) {}
      mk.setContent(el);
    }
    els[t.id] = el;
    zmap[t.id] = z;
  }

  function ensureLine(t) {
    // 有多条报文的列车画出运动轨迹：主体线 + 末端亮点
    var line = lines[t.id];
    var pts = (t.trail || []);
    if (!CFG.showTrail || pts.length < 2) {
      if (line) { line.setPath([]); }
      return;
    }
    var color = COLOR[t.direction] || COLOR.unknown;
    if (!line) {
      line = new AMap.Polyline({
        path: pts, strokeColor: color, strokeWeight: 4, strokeOpacity: 0.72,
        lineJoin: 'round', lineCap: 'round', zIndex: 80,
        showDir: pts.length >= 3, dirColor: color
      });
      map.add(line);
      lines[t.id] = line;
    } else {
      line.setPath(pts);
      line.setOptions({ strokeColor: color, showDir: pts.length >= 3, dirColor: color });
    }
  }

  /* 按屏幕距离做一次简单防重叠：离得近的车只留车次，收起副行。
     只用自己记的 els/zmap + 经纬度换算，不调用 Marker 的 getContent/getZIndex
     （高德 2.0 没有这些方法，一抛异常整个 update 就中断，地图就再也不居中）。 */
  function declutter() {
    if (!map) { return; }
    try {
      var zoom = map.getZoom();
      var boxes = [];
      order.forEach(function (id) {
        var el = els[id], st = state[id];
        if (!el || !st || !el.classList) { return; }
        var pt = null;
        try { pt = map.lngLatToContainer([st.lon, st.lat]); } catch (e) { pt = null; }
        if (!pt) { return; }
        boxes.push({ el: el, x: pt.getX(), y: pt.getY(), z: zmap[id] || 0 });
      });
      boxes.sort(function (a, b) { return b.z - a.z; });   // 新的优先
      var kept = [];
      boxes.forEach(function (b) { b.el.classList.remove('mini', 'dim'); });
      boxes.forEach(function (b) {
        var clash = false;
        for (var i = 0; i < kept.length; i++) {
          if (Math.abs(kept[i].x - b.x) < COLLIDE_PX && Math.abs(kept[i].y - b.y) < 26) {
            clash = true; break;
          }
        }
        if (clash || zoom < MIN_ZOOM_SUB) { b.el.classList.add('mini'); }
        if (clash) { b.el.classList.add('dim'); }
        if (!clash) { kept.push(b); }
      });
    } catch (e) { /* 纯视觉优化，失败绝不能影响定位 */ }
  }

  function applyNight(on) {
    on = !!on;
    CFG.night = on;
    var want = on ? STYLE_NIGHT : STYLE_DAY;
    /* ① 先按官方 API 试：高德「个性化地图」样式 */
    if (map && map.setMapStyle) {
      try { map.setMapStyle(want); } catch (e) { /* 没权限就忽略 */ }
    }
    /* ② 校验是否真的被接受。有的 Key 没开通「个性化地图」时 setMapStyle 会被
          静默丢弃，getMapStyle() 仍返回 normal，底图看上去毫无变化。
          这时退化成 CSS 反相滤镜（只作用于瓦片层，标记与轨迹颜色不受影响）。 */
    var real = '';
    try { real = (map && map.getMapStyle) ? String(map.getMapStyle()) : ''; } catch (e) { real = ''; }
    var accepted = real.indexOf('styles') >= 0 && real.indexOf('normal') < 0;
    document.body.classList.toggle('nightfall', !!on && !accepted);
    document.body.classList.toggle('dark', on);
    document.body.classList.toggle('light', !on);
  }

  function update(p) {
    if (!ready) { pending = p; return; }
    hideHint();
    CFG.follow = !!p.follow; CFG.showTrail = !!p.showTrail;
    if (typeof p.night === 'boolean' && p.night !== CFG.night) { applyNight(p.night); }
    var incoming = {};
    (p.trains || []).forEach(function (t) {
      if (typeof t.lat !== 'number' || typeof t.lon !== 'number') { return; }
      incoming[t.id] = true;
      state[t.id] = t;
      ensureMarker(t); ensureLine(t);
    });
    Object.keys(markers).forEach(function (id) {
      if (!incoming[id]) {
        map.remove(markers[id]); delete markers[id];
        if (lines[id]) { map.remove(lines[id]); delete lines[id]; }
        delete state[id]; delete els[id]; delete zmap[id];
      }
    });
    order = (p.trains || []).map(function (t) { return t.id; });
    declutter();
    if (p.focus && state[p.focus]) {
      var t = state[p.focus];
      userTouched = false;
      lastAuto = [t.lon, t.lat];
      map.setZoomAndCenter(Math.max(CFG.zoom, 13), [t.lon, t.lat], false, 260);
    } else if (CFG.follow && !userTouched && p.trains && p.trains.length) {
      // 关键：只有“当先那列车确实动了 30 米以上”才重新居中。
      // 以前每来一帧（最多 4 次/秒）都无条件 setZoomAndCenter，手指还没拖动就被拉回去，
      // 表现就是“来车后地图动不了”。
      var a = p.trains[0];
      var moved = !lastAuto ||
        (Math.abs(a.lon - lastAuto[0]) + Math.abs(a.lat - lastAuto[1])) > 3e-4;
      if (moved) {
        lastAuto = [a.lon, a.lat];
        var list = p.trains.filter(function (x) { return markers[x.id]; })
                           .map(function (x) { return markers[x.id]; });
        if (list.length === 1) {
          map.setZoomAndCenter(Math.max(CFG.zoom, 13), [a.lon, a.lat], false, 300);
        } else if (list.length > 1) {
          map.setFitView(list, false, [50, 50, 50, 50], 14);
        }
      }
    }
  }

  window.LBJ = {
    update: update,
    focus: function (id) { if (state[id]) { update({ trains: Object.values(state), follow: false, focus: id, showTrail: CFG.showTrail }); } },
    clear: function () {
      Object.keys(markers).forEach(function (id) { map.remove(markers[id]); });
      Object.keys(lines).forEach(function (id) { map.remove(lines[id]); });
      markers = {}; lines = {}; state = {}; order = []; els = {}; zmap = {};
      if (info) { info.close(); }
    },
    setTrail: function (v) { CFG.showTrail = !!v;
      Object.keys(state).forEach(function (id) { ensureLine(state[id]); }); },
    closeInfo: function () { if (info) { info.close(); } },
    setNight: applyNight,
    isNight: function () { return !!CFG.night; },
    resize: function () { if (map) { map.resize(); } },
    // ---- v2.3.1：跟随 & 中心点 ----
    locked: function () { return !!userTouched; },              // 用户是否手动移动过
    setFollow: function (on) { userTouched = false; CFG.follow = !!on; },
    center: function () {                                       // 当前视图中心 [lng, lat]
      var c = map && map.getCenter();
      return c ? [c.getLng(), c.getLat()] : null;
    },
    centerTo: function (addr) {                                 // 重新解析并居中
      CENTER_ADDR = addr || '';
      userTouched = false;
      resolveCenter(function () {});
    }
  };

  if (document.readyState === 'complete') { init(); }
  else { window.addEventListener('load', init); }
  window.addEventListener('error', function (e) {
    if (!ready) { showHint('<b>页面脚本错误</b><br>' + esc(e.message || '')); }
  });
})();
</script>
</body>
</html>
"""


class MapPanel(QWidget):
    """首页实时地图卡片。

    对外接口:
        setConfig(cfg)      配置变化时调用 (Key/缩放/跟随)
        updateTrain(d)      传入一条解码结果字典
        focusCurrent()      定位到最近一列车
        clear()             清空所有标记
    """

    mapClicked = Signal(str)
    followChanged = Signal(bool)   # 跟随开关变化（含“手动移动地图导致自动取消”）

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._trains: Dict[str, Dict[str, Any]] = {}
        self._last_push = 0.0
        self._view: Optional[QWebEngineView] = None
        self._page_ready = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        bar = QHBoxLayout()
        bar.setContentsMargins(6, 2, 6, 2)
        bar.setSpacing(6)
        title = QLabel('实时位置')
        title.setStyleSheet(
            f'color: {_c("accent")}; font-weight: bold; font-size: 12px;')
        self.coordLabel = QLabel('等待经纬度报文')
        self.coordLabel.setStyleSheet(f'color: {_c("dim")}; font-size: 11px;')
        self.coordLabel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.followBtn = QPushButton('跟随')
        self.followBtn.setCheckable(True)
        self.followBtn.setChecked(bool(getattr(config, 'mapFollow', True)))
        self.followBtn.setToolTip('自动跟着最新列车走（手动拖动地图会自动暂停）')
        self.followBtn.setStyleSheet('padding: 2px 8px; font-size: 11px;')
        self.followBtn.clicked.connect(self._onFollow)
        self.nightBtn = QPushButton()
        self.nightBtn.setCheckable(True)
        self.nightBtn.setChecked(bool(getattr(config, 'mapNight', True)))
        self.nightBtn.setToolTip('切换地图夜间 / 日间配色')
        self.nightBtn.setStyleSheet('padding: 2px 8px; font-size: 11px;')
        self.nightBtn.clicked.connect(self._onNight)
        self._syncNightBtn()
        self.clearBtn = QPushButton('清除')
        self.clearBtn.setToolTip('清除地图上的列车标记')
        self.clearBtn.setStyleSheet('padding: 2px 8px; font-size: 11px;')
        self.clearBtn.clicked.connect(self.clear)
        self.centerBtn = QPushButton('中心')
        self.centerBtn.setToolTip('回到配置里的默认中心（默认中心地址在「配置 → 地图与车次」）')
        self.centerBtn.setStyleSheet('padding: 2px 8px; font-size: 11px;')
        self.centerBtn.clicked.connect(self.centerToDefault)
        self.browserBtn = QPushButton('网页')
        self.browserBtn.setToolTip('在浏览器中用高德地图打开当前位置')
        self.browserBtn.setStyleSheet('padding: 2px 8px; font-size: 11px;')
        self.browserBtn.clicked.connect(self._openInBrowser)
        bar.addWidget(title)
        bar.addWidget(self.coordLabel, 1)
        bar.addWidget(self.nightBtn)
        bar.addWidget(self.centerBtn)
        bar.addWidget(self.followBtn)
        bar.addWidget(self.clearBtn)
        bar.addWidget(self.browserBtn)
        outer.addLayout(bar)

        self._host = QWidget()
        self._hostLayout = QVBoxLayout(self._host)
        self._hostLayout.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._host, 1)

        self._fallback = QLabel()
        self._fallback.setWordWrap(True)
        self._fallback.setAlignment(Qt.AlignCenter)
        self._fallback.setStyleSheet(
            f'color: {_c("dim")}; background-color: {_c("panel2")};'
            f' border: 1px solid {_c("border")};'
            ' border-radius: 4px; font-size: 11px; padding: 8px;')
        self._fallback.hide()
        self._hostLayout.addWidget(self._fallback)

        self._buildView()

        # 每秒问一次页面状态：用户是否手动移动过地图（决定是否暂停跟随），
        # 顺手把当前视图中心缓存进配置，断网时下次启动也有中心可用。
        self._viewTimer = QTimer(self)
        self._viewTimer.setInterval(1200)
        self._viewTimer.timeout.connect(self._pollView)
        self._viewTimer.start()

    # ------------------------------------------------------------------
    # 地图页面
    # ------------------------------------------------------------------
    @property
    def hasMap(self) -> bool:
        return self._view is not None

    def _key(self) -> str:
        return str(getattr(self.config, 'amapKey', '') or '').strip()

    def _buildView(self):
        if not HAS_WEBENGINE:
            self._showFallback(
                '未安装 <b>PySide6-Addons</b>，无法内嵌高德地图。<br>'
                '执行 <code>pip install PySide6-Addons</code> 后重启程序即可。<br>'
                '仍可在“网页”按钮中用系统浏览器查看位置。')
            return
        if not self._key():
            self._showFallback(
                '尚未配置高德地图 Key。<br>'
                '打开 <b>配置 → 地图与车次</b>，填入 Web端(JS API) Key 与安全密钥。<br>'
                '申请地址：console.amap.com/dev/key/app')
            return
        if self._view is None:
            self._view = QWebEngineView(self)
            self._view.setContextMenuPolicy(Qt.NoContextMenu)
            self._view.loadFinished.connect(self._onLoadFinished)
            self._hostLayout.addWidget(self._view)
        self._fallback.hide()
        self._view.show()
        self._page_ready = False
        self._view.setHtml(self._html(), QUrl('https://webapi.amap.com/'))

    def applyTheme(self):
        """主题切换后重建页面：地图的配色是注入 HTML 的，改不了“只重绘”。

        重建会丢掉标记点，所以紧接着 force push 一次数据（_trains 一直在内存里）。
        """
        if not self.hasMap or not self._key():
            return
        self._buildView()
        # 页面加载完成后 _onLoadFinished 里会 force push，这里不用重复推

    def _showFallback(self, text: str):
        if self._view is not None:
            self._view.hide()
        self._fallback.setText(text)
        self._fallback.show()

    def _html(self) -> str:
        cfg = self.config
        from urllib.parse import quote
        try:
            import theme as TH
            colors = TH.mapColors()
        except Exception:
            colors = {'up': '#4C8DFF', 'down': '#F0604F', 'unknown': '#E0A400'}
        return (_HTML_TEMPLATE
                .replace('__MAPCOLORS__', json.dumps(colors, ensure_ascii=False))
                .replace('__KEY__', quote(self._key(), safe=''))
                .replace('__SECURITY__', json.dumps(
                    str(getattr(cfg, 'amapSecurity', '') or '')))
                .replace('__ZOOM__', str(int(getattr(cfg, 'mapZoom', 12) or 12)))
                .replace('__FOLLOW__', 'true' if getattr(cfg, 'mapFollow', True) else 'false')
                .replace('__TRAIL__', 'true' if getattr(cfg, 'mapShowTrail', True) else 'false')
                .replace('__NIGHT__', 'true' if getattr(cfg, 'mapNight', True) else 'false')
                .replace('__CENTER_ADDR__', json.dumps(
                    str(getattr(cfg, 'mapCenterAddress', '') or ''), ensure_ascii=False))
                .replace('__CENTER_LNG__', repr(float(getattr(cfg, 'mapCenterLng', 0) or 0)))
                .replace('__CENTER_LAT__', repr(float(getattr(cfg, 'mapCenterLat', 0) or 0))))

    def _onLoadFinished(self, ok: bool):
        if not ok:
            self._showFallback('地图页面加载失败，请检查网络。')
            return
        self._page_ready = True
        self._push(force=True)

    def setConfig(self, config):
        """配置更新后重建页面。"""
        old_key = getattr(self.config, 'amapKey', '')
        old_night = bool(getattr(self.config, 'mapNight', True))
        old_addr = str(getattr(self.config, 'mapCenterAddress', '') or '').strip()
        self.config = config
        self.followBtn.setChecked(bool(getattr(config, 'mapFollow', True)))
        self._syncNightBtn()
        if bool(getattr(config, 'mapNight', True)) != old_night:
            self.setNightMode(bool(getattr(config, 'mapNight', True)))
        if str(getattr(config, 'amapKey', '') or '') != str(old_key or ''):
            self._trains.clear()
            self._buildView()
        else:
            # 默认中心改了 → 立刻把视图挪过去（不重建页面，标记点不丢）
            new_addr = str(getattr(config, 'mapCenterAddress', '') or '').strip()
            if new_addr != old_addr:
                self.centerToDefault()
            self._push(force=True)

    # ------------------------------------------------------------------
    # 数据更新
    # ------------------------------------------------------------------
    def updateTrain(self, d: dict):
        lat = d.get('latitude')
        lon = d.get('longitude')
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            return
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return
        train = str(d.get('train') or d.get('baseTrain') or '----')
        # 用纯数字车次作为稳定 id：基础帧先到、长报文后补前缀时不会出现两个标记
        tid = str(d.get('baseTrain') or train)
        ts = float(d.get('timestamp') or 0.0)
        item = self._trains.get(tid)
        if item is None:
            item = {'id': tid, 'trail': []}
            self._trains[tid] = item
        glat, glon = wgs84_to_gcj02(float(lat), float(lon))
        item.update({
            'train': train,
            'lat': round(glat, 6),
            'lon': round(glon, 6),
            'wgsLat': round(float(lat), 6),
            'wgsLon': round(float(lon), 6),
            'time': d.get('timeStr', ''),
            'speed': d.get('speed', '---'),
            'km': d.get('position', '---.-'),
            'route': d.get('route', '----'),
            'loco': d.get('loco', '----'),
            'direction': d.get('direction', '未知'),
            'category': d.get('category', '----'),
            'ts': ts,
        })
        # 轨迹：保留更多点（默认 240），按“距离 > 6m 或 时间 > 3s”抽稀，
        # 这样多帧详细报文能连成一条真实走行轨迹，又不会堆出上千个点。
        trail = item.setdefault('trail', [])
        now = ts or datetime.now().timestamp()
        keep = True
        if trail:
            d_lat = abs(trail[-1][1] - item['lat'])
            d_lon = abs(trail[-1][0] - item['lon'])
            moved = (d_lat + d_lon) > 6e-5          # 约 6 m
            elapsed = now - float(item.get('trailTs', 0) or 0)
            keep = moved or elapsed > 3.0
        if keep:
            trail.append([item['lon'], item['lat']])
            item['trailTs'] = now
            del trail[:-240]
        # 清理 15 分钟未更新的列车
        cutoff = ts - 900
        for k in [k for k, v in self._trains.items() if v.get('ts', 0) < cutoff]:
            self._trains.pop(k, None)
        self.coordLabel.setText(f'{train}  {lat:.5f}, {lon:.5f}')
        self._push()

    def _payload(self, focus: Optional[str] = None) -> dict:
        trains = sorted(self._trains.values(), key=lambda x: x.get('ts', 0), reverse=True)
        for t in trains:
            trail = t.get('trail') or []
            if len(trail) >= 2:
                # 用首尾点粗算轨迹长度（度差 → km，纬度 1°≈111km）
                import math as _m
                dist = 0.0
                for i in range(1, len(trail)):
                    dx = (trail[i][0] - trail[i - 1][0]) * 111.0 * \
                        _m.cos(_m.radians(trail[i][1]))
                    dy = (trail[i][1] - trail[i - 1][1]) * 111.0
                    dist += _m.hypot(dx, dy)
                t['trailSpan'] = ('%.1f km' % dist) if dist >= 0.1 else \
                    ('%.0f m' % (dist * 1000))
        return {
            'trains': trains,
            'follow': bool(getattr(self.config, 'mapFollow', True)),
            'showTrail': bool(getattr(self.config, 'mapShowTrail', True)),
            'night': bool(getattr(self.config, 'mapNight', True)),
            # 只有显式定位（focusCurrent）才传 focus；否则每次推送都会被
            # 强制 setZoomAndCenter，“跟随”开关就失效了
            'focus': focus,
        }

    def _push(self, force: bool = False):
        if not self._page_ready or self._view is None:
            return
        now = datetime.now().timestamp()
        if not force and now - self._last_push < 0.25:
            return
        self._last_push = now
        payload = json.dumps(self._payload(), ensure_ascii=False)
        self._view.page().runJavaScript(f'window.LBJ && window.LBJ.update({payload});')

    def focusCurrent(self):
        if not self._trains:
            return
        tid = max(self._trains.values(), key=lambda x: x.get('ts', 0))['id']
        if self._page_ready and self._view is not None:
            js = f'window.LBJ && window.LBJ.focus({json.dumps(tid)});'
            self._view.page().runJavaScript(js)

    def clear(self):
        self._trains.clear()
        self.coordLabel.setText('等待经纬度报文')
        if self._page_ready and self._view is not None:
            self._view.page().runJavaScript('window.LBJ && window.LBJ.clear();')

    def _onFollow(self, checked: bool):
        self.config.mapFollow = bool(checked)
        if self._page_ready and self._view is not None:
            # 钩子：重新打开跟随时清掉“用户已手动移动”的锁，并立刻回位一次
            self._view.page().runJavaScript(
                'window.LBJ && window.LBJ.setFollow(%s);'
                % ('true' if checked else 'false'))
            if checked:
                self.focusCurrent()
        self._push(force=True)
        self.followChanged.emit(bool(checked))

    def centerToDefault(self):
        """把地图挪回配置里的默认中心（地名交给高德地理编码，不加标记）。"""
        addr = str(getattr(self.config, 'mapCenterAddress', '') or '').strip()
        # 用户主动看固定中心，就先把「跟随」让开：否则下一帧列车位置一变，
        # 视野又被拉走，点「中心」看起来就像没生效。
        if self.followBtn.isChecked():
            self.followBtn.setChecked(False)
            self.config.mapFollow = False
            if self._page_ready and self._view is not None:
                self._view.page().runJavaScript(
                    'window.LBJ && window.LBJ.setFollow(false);')
        if not self._page_ready or self._view is None:
            return
        self._view.page().runJavaScript(
            'window.LBJ && window.LBJ.centerTo(%s);' % json.dumps(addr, ensure_ascii=False))
        self.coordLabel.setText('中心：%s' % (addr or '（未设置）'))

    def _pollView(self):
        """每秒问一次页面：用户是不是手动拖过地图了？

        是的话把「跟随」按钮取消勾选并存进配置——这样按钮状态和实际行为一致，
        用户也不会再遇到“拖动后又被拉回去”。
        """
        if not self._page_ready or self._view is None:
            return
        self._view.page().runJavaScript(
            'window.LBJ ? window.LBJ.locked() : false;', self._onLockPoll)

    def _onLockPoll(self, locked):
        if locked and self.followBtn.isChecked():
            # 用户手动拖过地图 → 取消勾选「跟随」，让按钮状态和实际行为一致
            self.followBtn.setChecked(False)
            self.config.mapFollow = False
            self.followChanged.emit(False)
        # 顺便把当前视图中心缓存下来，断网时下次启动就有中心可用
        self._view.page().runJavaScript(
            'window.LBJ ? window.LBJ.center() : null;', self._onCenterPoll)

    def _onCenterPoll(self, center):
        try:
            if isinstance(center, list) and len(center) == 2 and center[0]:
                lng, lat = float(center[0]), float(center[1])
                # 只有明显变化才写，避免每次刷新都落盘
                if (abs(lng - float(getattr(self.config, 'mapCenterLng', 0) or 0)) > 1e-4
                        or abs(lat - float(getattr(self.config, 'mapCenterLat', 0) or 0)) > 1e-4):
                    self.config.mapCenterLng = lng
                    self.config.mapCenterLat = lat
        except Exception:
            pass

    def _syncNightBtn(self):
        on = bool(getattr(self.config, 'mapNight', True))
        self.nightBtn.setText('夜间' if on else '日间')
        self.nightBtn.setChecked(on)
        self.nightBtn.setToolTip('当前：%s（点击切换）' % ('夜间' if on else '日间'))

    def setNightMode(self, on: bool):
        """切换夜间/日间配色（按钮与视图菜单共用）。"""
        self.config.mapNight = bool(on)
        self._syncNightBtn()
        if self._page_ready and self._view is not None:
            js = 'window.LBJ && window.LBJ.setNight(%s);' % (
                'true' if self.config.mapNight else 'false')
            self._view.page().runJavaScript(js)

    def _onNight(self, checked: bool):
        self.setNightMode(checked)
        self._push(force=True)

    def _openInBrowser(self):
        if not self._trains:
            QDesktopServices.openUrl(QUrl('https://www.amap.com/'))
            return
        t = max(self._trains.values(), key=lambda x: x.get('ts', 0))
        name = f"{t.get('train', '列车')} {t.get('time', '')}".strip()
        url = ('https://uri.amap.com/marker?position={lon:.6f},{lat:.6f}'
               '&name={name}&src=crlbj&coordinate=gaode&callnative=1'
               ).format(lon=t['lon'], lat=t['lat'],
                        name=QUrl.toPercentEncoding(name).data().decode())
        QDesktopServices.openUrl(QUrl(url))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._page_ready and self._view is not None:
            self._view.page().runJavaScript('window.LBJ && window.LBJ.resize();')
