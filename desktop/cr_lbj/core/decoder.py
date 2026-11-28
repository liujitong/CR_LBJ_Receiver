#!/usr/bin/env python3
"""
RTL_LBJ_core.py — 基于 RTL-SDR 的中国铁路 LBJ 列车预警器核心库

作者: BG2GBQ
License: GPL v3

本文件从提取纯核心 DSP 与解码逻辑，
便于任何上层应用（GUI、Web、CLI、自动化脚本）直接调用。

核心能力:
  1. 连接 rtl_tcp 服务（支持直连 RTL-SDR Blog v4 或 OWRX 转发流）
  2. 完整接收前端流水线: IQ 校正 → DDC → 半带抽取 → 信道 FIR → FM 鉴频 → AFC
  3. LBJ 报文实时解码: DPLL 比特恢复 → 帧同步 → BCH(31,21) 译码 → BCD 提取 → 报文解析
  4. 车次 / 机车 / 线路 / 公里标 / 方向 / 速度 全字段解析
  5. ETA 到达估算（需设置本站公里标）
  6. 输出原始数据（含 BCD 字符串、地址码、功能码、码字列表）

典型用法:
    from cr_lbj.core.decoder import LbjCore

    core = LbjCore(host='owrx.example.com', port=5678,
                   sampleRate=960000, freqMhz=821.2375)
    core.start()                         # 启动后台 DSP 线程
    record = core.waitForDecode(timeout=30)  # 阻塞等待一次解码
    if record:
        print(record.train, record.direction, record.rawBcd)
"""

from __future__ import annotations
import os
import re
import time
import socket
import struct
import shutil
import subprocess
import threading
import queue
import unicodedata
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field

import numpy as np
from scipy.signal import firwin, lfilter, lfilter_zi
import scipy.signal as ssig

# 同层基础模块：路径查找、块级统计、USB 直连数据源
from cr_lbj.core.rtl_paths import runtime_dirs as _runtime_dirs, find_rtl_tool
from cr_lbj.core.source_stats import buildDiagnostics, recordBlock
from cr_lbj.core.usb_direct import RtlSdrDirectSource, RtlSdrError


# ===========================================================================
# 全局常量
# ===========================================================================
BASEBAND_RATE = 48000          # 基带音频采样率 (Hz)
BAUD_RATE = 1200               # LBJ 波特率 (bps)
HW_GAIN_DB = 15.7              # 默认硬件增益 (dB)
PPM = 1                        # 默认频率校准 (ppm)
TCP_HOST = '127.0.0.1'         # 默认 rtl_tcp 主机
TCP_PORT = 1234                # 默认 rtl_tcp 端口
RTL_SAMPLE_RATE = 960000       # 默认 RTL-SDR 采样率 (Hz)
HALFBAND_STAGES = 2            # 默认半带抽取级数
MID_RATE = 240000              # 半带输出后中间速率 (Hz)
BLOCK_SIZE = 65536             # 每次读取的 IQ 样本数
DEFAULT_DC_OFFSET_HZ = 50000.0 # 默认 DDC 偏移 (Hz)，用于避开 DC 零频
DEFAULT_BW_KHZ = 35.0          # 默认信道带宽 (kHz)
DEFAULT_AFC_MAX_HZ = 8000.0    # AFC 最大修正范围 (Hz)
DEFAULT_RSSI_THRESHOLD_DB = -55.0  # RSSI 开启门限 (dB)
DEFAULT_RSSI_HYST_DB = 4.0     # RSSI 释放迟滞 (dB)
DEFAULT_RSSI_HOLD_MS = 700.0   # RSSI 保持时间 (ms)
DEFAULT_ETA_MAX_SECONDS = 6 * 3600  # ETA 最大估算秒数 (6 小时)

# R820T 可选增益列表 (dB)，用于将期望增益映射到硬件支持的最接近值
R820T_GAINS = [0.0, 0.9, 1.4, 2.7, 3.7, 7.7, 8.7, 12.5, 14.4, 15.7, 16.6,
               19.7, 20.7, 22.9, 25.4, 28.0, 29.7, 32.8, 33.8, 36.4, 37.2,
               38.6, 40.2, 42.1, 43.4, 43.9, 44.5, 48.0, 49.6]

# rtl_tcp 协议命令 ID
CMD_SET_FREQ = 1               # 设置中心频率
CMD_SET_SAMPLERATE = 2         # 设置采样率
CMD_SET_GAINMODE = 3           # 设置增益模式 (0=auto, 1=manual)
CMD_SET_GAIN = 4               # 设置增益 (1/10 dB)
CMD_SET_FREQCORR = 5           # 设置频率校正 (ppm)
CMD_SET_AGC = 8                # 设置 AGC (0=off, 1=on)

# 数据源类型 → 日志/状态栏显示名（界面下拉的完整文案见 SOURCE_TYPE_LABELS）
SOURCE_TYPE_NAMES = {
    'rtl_usb': '本机 USB 直连',
    'rtl_usb_tcp': '本机 USB (RTL-TCP 中转)',
    'rtl_tcp': 'RTL-TCP',
    'owrx': 'OWRX',
}
_SOURCE_TYPES = tuple(SOURCE_TYPE_NAMES)


# ===========================================================================
# 解码结果数据类
# ===========================================================================
@dataclass
class DecodeResult:
    """一次完整解码的结果。包含解析后的字段与原始数据。"""

    # --- 解析后字段 ---
    timestamp: float = 0.0              # 解码时间戳 (Unix epoch)
    timeStr: str = ''                   # 解码时间字符串 'YYYY-MM-DD HH:MM:SS'
    train: str = '----'                 # 完整车次号 (含前缀字母，如 T398)
    baseTrain: str = '----'             # 纯数字车次号 (如 398)
    prefix: str = ''                    # 车次号前缀字母 (如 T)
    direction: str = '未知'             # 方向: 上行/下行/未知
    speed: str = '---'                  # 速度 (km/h)
    position: str = '---.-'            # 公里标 (如 0123.4)
    loco: str = '----'                  # 机车号 (如 韶山4-0123)
    locoCode: str = '---'               # 机车代号 (如 207)
    route: str = '----'                 # 线路名 (如 京沪线)
    category: str = '未知类别'          # 列车类别
    latitude: Optional[float] = None    # 纬度 (WGS-84 十进制度)
    longitude: Optional[float] = None   # 经度 (WGS-84 十进制度)
    isDetailed: bool = False            # 是否为详细报文 (含机车/线路)
    routeValid: bool = False            # 线路名是否通过校验
    msgTypeError: bool = False          # 是否存在 BCH 不可纠错
    hasInterference: bool = False       # 信号受干扰 (BCH 错包率高)

    # --- 原始数据 ---
    rawBcd: str = ''                    # BCD 原始字符串 (含特殊字符 * U 空格 - ) ( )
    rawAddr: int = 0                    # 报文地址码 (18 位)
    rawFunc: int = 0                    # 功能码 (2 位: 1=下行, 3=上行)
    rawCodewords: List[int] = field(default_factory=list)  # 纠错后的码字列表
    rawIsShort: bool = False            # 报文类型: 短报文
    rawIsMerged: bool = False           # 报文类型: 合并报文
    rawIsStandalone: bool = False       # 报文类型: 独立长报文

    # --- 记录标识（v2.1 去重用） ---
    uid: str = ''                       # 同一次发射的唯一标识；窗口内更优记录沿用同一 uid

    # --- 信号质量 ---
    rssi: float = -140.0               # 接收信号强度 (dB)
    afcHz: float = 0.0                 # AFC 补偿频率 (Hz)
    afcErrHz: float = 0.0              # AFC 频偏估计 (Hz)
    afcScore: float = 0.0              # AFC 信号评分 (0~1)

    # --- ETA 估算 ---
    etaSeconds: Optional[float] = None  # 预计到达秒数
    etaTime: str = '--:--:--'          # 预计到达时间 HH:MM:SS
    etaDistanceKm: Optional[float] = None  # 距离 (km)
    etaStatus: str = '等待信号'         # ETA 状态描述

    def toDict(self) -> Dict[str, Any]:
        """转换为字典 (便于 JSON 序列化)。"""
        return {
            'timestamp': self.timestamp, 'timeStr': self.timeStr,
            'train': self.train, 'baseTrain': self.baseTrain, 'prefix': self.prefix,
            'direction': self.direction, 'speed': self.speed, 'position': self.position,
            'loco': self.loco, 'locoCode': self.locoCode, 'route': self.route,
            'category': self.category, 'isDetailed': self.isDetailed,
            'latitude': self.latitude, 'longitude': self.longitude,
            'routeValid': self.routeValid, 'msgTypeError': self.msgTypeError,
            'hasInterference': self.hasInterference,
            'rawBcd': self.rawBcd, 'rawAddr': self.rawAddr, 'rawFunc': self.rawFunc,
            'rawCodewords': self.rawCodewords, 'rawIsShort': self.rawIsShort,
            'rawIsMerged': self.rawIsMerged, 'rawIsStandalone': self.rawIsStandalone,
            'rssi': self.rssi, 'afcHz': self.afcHz, 'afcErrHz': self.afcErrHz,
            'afcScore': self.afcScore, 'etaSeconds': self.etaSeconds,
            'etaTime': self.etaTime, 'etaDistanceKm': self.etaDistanceKm,
            'etaStatus': self.etaStatus, 'uid': self.uid,
        }


# ===========================================================================
# 核心配置类（供 GUI / CLI / Web 集中管理与持久化）
# ===========================================================================
@dataclass
class CoreConfig:
    """核心库运行配置。

    所有字段均可通过 GUI/CLI 修改；支持 toDict/fromDict 与 save/load
    以便序列化为 JSON 文件持久化。

    热更新（无需重启 DSP）:
        rssiThresholdDb, rssiHystDb, rssiHoldMs, userKm, routeKm, keepAfcAfterPacket
    需重启 DSP（涉及链路重建）:
        host, port, sampleRate, freqMhz, gainDb, ppm, bwKhz, blockSize,
        dcOffsetHz, owrxMode, afcEnable, afcMaxHz, afcGain, etaMaxMin
    """

    # --- 连接 ---
    host: str = TCP_HOST
    port: int = TCP_PORT

    # --- 射频参数 ---
    sampleRate: int = RTL_SAMPLE_RATE      # RTL-SDR 采样率 (Hz)
    freqMhz: float = 821.2375              # 中心频率 (MHz)
    gainDb: float = HW_GAIN_DB             # 硬件增益 (dB)
    ppm: float = PPM                       # 频率校正 (ppm)

    # --- 信号处理 ---
    bwKhz: float = DEFAULT_BW_KHZ          # 信道带宽 (kHz)
    blockSize: int = BLOCK_SIZE            # 每次读取 IQ 样本数
    dcOffsetHz: float = DEFAULT_DC_OFFSET_HZ  # DDC 偏移 (Hz)，传统模式默认 50000
    owrxMode: bool = False                  # 是否为 OWRX 模式 (默认传统 RTL-TCP)
    # 数据源: 'rtl_usb' 本机 USB 直连 librtlsdr (推荐, 无 TCP) |
    #         'rtl_usb_tcp' 本机 USB 经 rtl_tcp 子进程中转 (兼容模式) |
    #         'rtl_tcp' 远程/本地 rtl_tcp | 'owrx' OpenWebRX 兼容
    sourceType: str = 'rtl_tcp'
    sources: List[Dict[str, Any]] = field(default_factory=list)  # 数据源配置列表
    activeSource: int = 0                   # 当前数据源索引
    rtlTcpPath: str = ''                    # rtl_tcp.exe 路径，留空自动查找
    rtlDeviceIndex: int = 0                 # 本机 USB 设备序号 (多棒时使用)

    # --- RSSI 门控 ---
    rssiThresholdDb: float = DEFAULT_RSSI_THRESHOLD_DB  # 开启门限 (dB)
    rssiHystDb: float = DEFAULT_RSSI_HYST_DB            # 释放迟滞 (dB)
    rssiHoldMs: float = DEFAULT_RSSI_HOLD_MS            # 保持时间 (ms)

    # --- AFC ---
    afcEnable: bool = True                 # 是否启用 AFC
    afcMaxHz: float = DEFAULT_AFC_MAX_HZ   # AFC 最大修正范围 (Hz)
    afcGain: float = 0.45                  # AFC 环路增益
    keepAfcAfterPacket: bool = False       # 信号释放后是否保留 AFC

    # --- ETA 估算 ---
    userKm: Optional[float] = None         # 本站公里标 (km)
    routeKm: List[str] = field(default_factory=list)  # 线路公里标配置
    etaMaxMin: float = DEFAULT_ETA_MAX_SECONDS / 60.0  # ETA 最大估算分钟数

    # --- UI 偏好 (不影响 DSP，热更新) ---
    spectrumMode: str = 'graph'            # 频谱显示模式: 'graph'(pyqtgraph曲线) 或 'terminal'(终端块字符)
    dedupeWindow: float = 2.5              # 同车次重复报文合并窗口(秒)，0 表示关闭去重
    uiScale: float = 0.0                   # 界面缩放倍率，0 表示按屏幕自动
    theme: str = 'dark'                    # 外观主题: dark(夜间) / light(日间) / auto(跟随系统)

    # --- 地图显示 (仅 GUI 使用，不参与 DSP) ---
    # v3.0 起地图改用 shared/web/railmap.html（Leaflet + OpenRailwayMap），
    # 底图全部免 Key；旧版高德 JS API 的 amapKey/amapSecurity 已彻底移除
    # （老配置文件里残留的这两个键在 fromDict 时因 hasattr 为假而被忽略）。
    mapZoom: int = 12                      # 默认缩放级别
    mapFollow: bool = True                 # 是否自动跟随最新列车
    mapShowTrail: bool = True              # 是否显示最近列车轨迹点
    mapNight: bool = True                  # 地图夜间模式 (深色底图)
    # 默认中心：v3.2.8 起**只保留经纬度**（与安卓一致，不再存城市名字段）；
    # 离线也能定位，不再依赖地名解析。
    mapCenterLng: float = 0.0              # 中心经度 (WGS-84)
    mapCenterLat: float = 0.0              # 中心纬度 (WGS-84)
    # --- 地图图源 (v3.0) ---
    # 底图 id 与铁路图层 id 的取值见 shared/web/railmap.html 的
    # BASE_SOURCES / RAIL_SOURCES；界面侧清单在 cr_lbj/ui/config_ext.py。
    mapBase: str = 'amap'                  # 底图: amap*/baidu*/osm/tdt_*（见 railmap.html BASE_SOURCES）
    mapRail: str = 'orm_standard'          # 铁路图层: orm_standard/maxspeed/signals/electrified/gauge/off
    mapRailOpacity: float = 0.85           # 铁路图层不透明度 0.2~1.0
    tdtKey: str = ''                       # 天地图「浏览器端」tk（选 tdt_* 底图时需要）
    # --- 查询与数据更新 (v3.0) ---
    trainQuerySource: str = 'auto'         # 车次查询数据源: auto/railgo/12306
    dataAutoUpdate: bool = True            # 是否自动检查第三方数据（配属号段表）更新
    dataUpdateIntervalDays: int = 7         # 自动检查间隔（天）

    def toDict(self) -> Dict[str, Any]:
        """转换为字典 (便于 JSON 序列化)。"""
        d = {}
        for k, v in self.__dict__.items():
            if k == 'routeKm':
                d[k] = list(v) if v else []
            elif k == 'sources':
                d[k] = [dict(x) for x in v] if v else []
            else:
                d[k] = v
        return d

    @classmethod
    def fromDict(cls, d: Dict[str, Any]) -> 'CoreConfig':
        """从字典构造配置（忽略未知字段）。"""
        c = cls()
        if d:
            for k, v in d.items():
                if hasattr(c, k):
                    if k == 'routeKm' and isinstance(v, str):
                        v = [v]
                    setattr(c, k, v)
        # 兼容旧配置: 只有 host/port/owrxMode 时生成一个数据源条目
        if d and 'sourceType' not in d and d.get('owrxMode'):
            c.sourceType = 'owrx'
        if not c.sources:
            c.sources = [{
                'name': 'OWRX 数据源' if c.sourceType == 'owrx' else 'RTL-TCP 数据源',
                'type': c.sourceType if c.sourceType in _SOURCE_TYPES else 'rtl_tcp',
                'host': c.host, 'port': c.port, 'sampleRate': c.sampleRate,
                'gainDb': c.gainDb, 'ppm': c.ppm, 'dcOffsetHz': c.dcOffsetHz,
            }]
        if not (0 <= int(c.activeSource) < len(c.sources)):
            c.activeSource = 0
        return c

    def save(self, path: str) -> bool:
        """保存配置到 JSON 文件。"""
        import json
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.toDict(), f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    @classmethod
    def load(cls, path: str) -> 'CoreConfig':
        """从 JSON 文件加载配置；文件不存在则返回默认配置。"""
        import json
        try:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    return cls.fromDict(json.load(f))
        except Exception:
            pass
        return cls()


# ===========================================================================
# 工具函数
# ===========================================================================
def parseDmCoordinate(degText: str, minText: str,
                      isLatitude: bool = False) -> Optional[float]:
    """解析 LBJ 长报文中的“度分”坐标 (DDD + MM.MMMM)。

    LBJ 扩展报文用 3 位度 + 6 位分表示经度、2 位度 + 6 位分表示纬度，
    分值为整数形式，需除以 10000 得到实际分值。返回 WGS-84 十进制度。
    """
    try:
        deg = int(str(degText))
        minute = int(str(minText)) / 10000.0
    except (TypeError, ValueError):
        return None
    if minute >= 60.0:
        return None
    value = deg + minute / 60.0
    if isLatitude:
        if not (0.0 < value <= 60.0):
            return None
    else:
        if not (70.0 <= value <= 140.0):
            return None
    return round(value, 6)


def _speedValue(speed: Any) -> Optional[float]:
    """把速度字段转成数值；无效返回 None。"""
    try:
        v = float(str(speed).replace('km/h', '').strip())
    except (TypeError, ValueError):
        return None
    return v if 0 <= v <= 500 else None


# 新车次编排方案全量启用日期（本地时间语义）：此日 00:00 起所有车次一律按新版分类
TRAIN_NEW_SCHEME_DATE = datetime(2027, 1, 1)


def _category2026(prefix: str, numText: str) -> Optional[str]:
    """按 2026 版《列车车次编排规定》分类。"""
    try:
        n = int(numText) if numText else -1
    except ValueError:
        n = -1
    if prefix == 'X':
        return '新时速动车组 (350km/h+)'
    if prefix == 'G':
        return '高速动车组 (350km/h)'
    if prefix == 'T':
        return '特快动车组 (300km/h)'
    if prefix == 'K':
        return '快速动车组 (200~250km/h)'
    if prefix == 'D':
        return '动力集中动车组 (≤200km/h)'
    if prefix == 'C':
        return '城际动车组 (≤200km/h)'
    if prefix == 'S':
        return '市郊(域)列车 (≤160km/h)'
    if prefix == 'Z':
        return '快速旅客列车 (160km/h)'
    if prefix == 'N':
        return '快速旅客列车 (140km/h)'
    if prefix == 'V':
        if 6001 <= n <= 6998:
            return '普通旅客快车 (120km/h)'
        if 7001 <= n <= 7998:
            return '普通旅客慢车 (120km/h)'
        return '快速旅客列车 (120km/h)'
    if prefix == 'Y':
        return '普速旅游专线列车' if n <= 998 else '普速旅游专列'
    if prefix == 'B':
        if 1 <= n <= 198:
            return '特快城际班列 (160km/h)'
        if 201 <= n <= 998:
            return '快速多式联运班列 (120km/h)'
        if 1001 <= n <= 1998:
            return '快速城际班列 (120km/h)'
        if 2001 <= n <= 2998:
            return '快速中欧班列 (120km/h)'
        if 3001 <= n <= 3998:
            return '快速中亚班列 (120km/h)'
        if 4001 <= n <= 5998:
            return '普快多式联运班列 (90km/h)'
        if 6001 <= n <= 7998:
            return '普快城际班列 (90km/h)'
        if 8001 <= n <= 8998:
            return '普快中欧班列 (90km/h)'
        if 9001 <= n <= 9998:
            return '普快中亚班列 (90km/h)'
        return '货运班列'
    if prefix == 'DH':
        return '动车组快运 (250km/h+)' if n <= 998 else '动车组快运 (≤250km/h)'
    if prefix == 'DJ':
        return '动车组检测/确认列车'
    return None


def _categoryLegacy(prefix: str, numText: str, isDetailed: bool) -> str:
    """按 2014 版旧规则分类（兼容仍在过渡期的车次）。"""
    legacyLetters = {
        'K': '快速旅客列车', 'Z': '直达特快列车', 'T': '特快旅客列车',
        'G': '高速动车组', 'D': '动车组列车', 'C': '城际动车组',
        'X': '行包货物列车', 'Y': '旅游旅客列车',
    }
    if prefix in legacyLetters:
        return legacyLetters[prefix]
    return ''


def classifyTrainCategory(trainNo: str, isDetailed: bool,
                          speed: Any = None,
                          now: Optional[datetime] = None) -> str:
    """根据车次号判断列车类别（纯自动、纯日期驱动，无手动方案）。

    now >= TRAIN_NEW_SCHEME_DATE (2027-01-01)：所有车次（高铁+普速）一律
    按新版编排分类，不再看速度；
    now <  TRAIN_NEW_SCHEME_DATE：过渡期——含义稳定的前缀已按新版，
    T/K/X 新旧含义冲突按速度判定（>=200 km/h 视为新版动车组），
    速度缺失/无效时一律按旧版兜底（日期界限即 2027-01-01）。

    参数:
        trainNo: 车次号 (如 T398, G1234, V6001, 50001)。
        isDetailed: 是否已收到详细报文。
        speed: 当前速度 (km/h)，仅过渡期用于区分新旧 T/K/X 含义。
        now: 当前时间（本地时间语义），None 取 datetime.now()；可注入便于测试。
    返回:
        类别中文名称。
    """
    if not trainNo or trainNo in ('等待信号...', '----'):
        return '等待信号...'
    tn = str(trainNo).replace(' ', '').strip().upper()
    m = re.match(r'^([A-Z]+)(\d*)', tn)
    prefix = m.group(1) if m else ''
    numText = m.group(2) if m else ''
    # 车次前缀可能带 0/无数字；纯数字车次 prefix 为空
    if prefix and not numText and tn.isalpha():
        numText = ''
    if now is None:
        now = datetime.now()

    # ---------- 2027-01-01 起：全量新版（高铁+普速，不看速度） ----------
    if now >= TRAIN_NEW_SCHEME_DATE:
        cat = _category2026(prefix, numText)
        if cat:
            return cat
        return _categoryNumeric(numText, tn, isDetailed)

    # ---------- 过渡期（2027-01-01 前） ----------
    # Z/N/V/B/DH/DJ/Y 以及 G/D/C/S 含义稳定，直接按新版
    if prefix in ('Z', 'N', 'V', 'B', 'DH', 'DJ', 'Y', 'G', 'D', 'C', 'S'):
        cat = _category2026(prefix, numText)
        if cat:
            return cat
    # T/K/X 新旧含义冲突：用速度判定（新 T=300、K=200~250、X=350+）
    if prefix in ('T', 'K', 'X'):
        spd = _speedValue(speed)
        if spd is not None:
            if spd >= 200:
                return _category2026(prefix, numText) or '未知类别'
            return _categoryLegacy(prefix, numText, isDetailed) or '未知类别'
        # 速度缺失/无效：过渡期内一律按旧版兜底（此分支 now < 2027-01-01 恒成立）
        return _categoryLegacy(prefix, numText, isDetailed) or '未知类别'
    return _categoryNumeric(numText, tn, isDetailed)


def _categoryNumeric(numText: str, tn: str, isDetailed: bool) -> str:
    """纯数字车次（货物/路用/回送等）分类，按新版区段表。"""
    # 00 开头 -> 回送列车（新旧规则一致）
    if tn.startswith('00'):
        d = ''.join(filter(str.isdigit, tn))
        if d:
            n = int(d)
            if 1 <= n <= 100:
                return '动车组有火回送'
            if 101 <= n <= 198:
                return '动车组无火跨局回送'
            if 201 <= n <= 298:
                return '动车组无火管内回送'
            if 301 <= n <= 398:
                return '跨局回送客车'
            if 401 <= n <= 498:
                return '管内回送客车'
    d = ''.join(filter(str.isdigit, numText or tn))
    if not d:
        return '未知类别'
    n = int(d)
    ranges = [(10001, 19998, '技术直达货运列车'), (20001, 29998, '直通货运列车'),
              (30001, 39998, '区段货运列车'), (40001, 44998, '摘挂列车'),
              (45001, 49998, '小运转列车'), (50001, 50998, '客车单机'),
              (51001, 51998, '货车单机'), (52001, 52998, '小运转单机'),
              (53001, 54998, '补机'), (55001, 55998, '试运行列车'),
              (56001, 56998, '轨道车、小型工程车'), (57001, 57998, '路用列车'),
              (58101, 58998, '救援列车'), (60001, 69998, '工厂自备车'),
              (70001, 70998, '超限货运列车'), (71001, 77998, '重载货物列车'),
              (80001, 81748, '直达货运/五定班列'), (81751, 81998, '快运货运列车'),
              (82001, 84998, '煤炭直达列车'), (85001, 85998, '石油直达列车'),
              (86001, 86998, '始发直达列车'), (87001, 87998, '空车直达列车'),
              (88001, 88998, '汽运专列'), (90001, 91998, '军用列车(满载)'),
              (93001, 94998, '军用列车(空车)')]
    for lo, hi, cat in ranges:
        if lo <= n <= hi:
            return cat
    if 1 <= n <= 9998 and not tn.startswith('00'):
        return '普通旅客列车' if isDetailed else '等待详细报文确认...'
    return '未知类别'


class RecordDeduplicator:
    """同一车次短窗口内的重复解码合并 (v2.1)。

    POCSAG 同一次发射常被连续解出 2~4 次（重发、码字重排、误码差异），
    表现为“同一车次同一秒出现多行、字段略有不同”。这里按 (车次, 方向)
    做窗口合并：

    * 窗口内第一条立即放行，并分配 uid；
    * 后续记录质量更高时，沿用同一 uid 放行 —— 上层据此替换已有记录；
    * 质量不更高则丢弃。

    既去掉重复，又保证留下的是“最好的那一条”。
    """

    def __init__(self, window: float = 2.5, maxSlots: int = 256):
        self.window = float(window)
        self.maxSlots = int(maxSlots)
        self._slots: Dict[str, Dict[str, Any]] = {}
        self.dropped = 0        # 被合并丢弃的重复记录数
        self.upgraded = 0       # 窗口内被更优记录替换的次数

    @staticmethod
    def keyOf(d: DecodeResult) -> str:
        base = str(d.baseTrain or d.train or '').strip()
        if base in ('', '----', '未知'):
            return ''
        return '%s|%s' % (base, d.direction)

    @staticmethod
    def quality(d: DecodeResult) -> float:
        """记录质量分，越大越好。详细报文、有坐标、无 BCH 错优先。"""
        score = 0.0
        if d.isDetailed:
            score += 100.0
        if d.latitude is not None and d.longitude is not None:
            score += 40.0
        if not d.msgTypeError:
            score += 20.0
        if d.routeValid:
            score += 10.0
        if d.loco and d.loco not in ('----', ''):
            score += 15.0
        if d.route and d.route not in ('----', ''):
            score += 10.0
        if d.speed not in ('---', '', None):
            score += 5.0
        if d.position not in ('---.-', '', None):
            score += 5.0
        try:  # RSSI 只作为同分时的微弱权重 (0~1)
            score += max(0.0, min(60.0, float(d.rssi) + 140.0)) / 60.0
        except (TypeError, ValueError):
            pass
        return score

    def apply(self, d: DecodeResult) -> Optional[DecodeResult]:
        """返回要放行的记录（可能沿用窗口内 uid），None 表示丢弃。"""
        key = self.keyOf(d)
        if not key:
            return d
        now = float(d.timestamp or time.time())
        if self.window <= 0:      # 关闭去重：仍分配 uid，便于 GUI/DB 唯一标识
            d.uid = '%s-%.3f' % (key.replace('|', '-'), now)
            return d
        slot = self._slots.get(key)
        if slot is not None and now - slot['ts'] > self.window:
            slot = None
        if slot is None:
            d.uid = '%s-%.3f' % (key.replace('|', '-'), now)
            self._slots[key] = {'uid': d.uid, 'ts': now,
                                'score': self.quality(d)}
            self._prune(now)
            return d
        score = self.quality(d)
        # 只有明显更优才替换（避免 RSSI 抖动导致反复刷新）
        if score > slot['score'] + 3.0:
            slot['score'] = score
            d.uid = slot['uid']
            self.upgraded += 1
            return d
        self.dropped += 1
        return None

    def _prune(self, now: float) -> None:
        if len(self._slots) <= self.maxSlots:
            return
        expire = now - self.window * 4
        for k in [k for k, v in self._slots.items() if v['ts'] < expire]:
            self._slots.pop(k, None)

    def reset(self) -> None:
        self._slots.clear()


def sanitizeRouteName(route: Optional[str]) -> str:
    """清洗线路名：去除控制字符与空白，返回规范字符串；无效返回空串。"""
    if route is None:
        return ''
    r = str(route).replace('\x00', '').strip()
    if not r or r in ('----', '---', '未知', '等待信号...'):
        return ''
    return r


def isValidRouteName(route: str) -> bool:
    """校验线路名是否合法：长度 ≤24，仅含中文/字母/数字/横线/空格。"""
    route = sanitizeRouteName(route)
    if not route:
        return False
    if len(route) > 24:
        return False
    if re.search(r'[\*U\(\)<>[\]{}\\/|;:,.，。！？?！@#$%^&_=+`~]', route):
        return False
    if not re.search(r'[\u4e00-\u9fa5A-Za-z0-9]', route):
        return False
    return bool(re.match(r'^[\u4e00-\u9fa5A-Za-z0-9\-\s]+$', route))


def parseKmValue(v: Any) -> Optional[float]:
    """从字符串/数字解析公里标 (km)，无效返回 None。"""
    if v is None:
        return None
    s = str(v).upper().replace('KM', '').strip()
    if not s or s in ('---', '---.-', '----'):
        return None
    try:
        km = float(s)
    except Exception:
        return None
    if km < 0 or km > 9999.9:
        return None
    return round(km, 1)


def parseRouteKmMap(items: Any) -> Dict[str, float]:
    """解析 '线路名=公里标' 列表为字典。"""
    result: Dict[str, float] = {}
    if not items:
        return result
    if isinstance(items, str):
        items = [items]
    for item in items:
        for part in str(item).split(','):
            part = part.strip()
            if not part or '=' not in part:
                continue
            route, val = part.split('=', 1)
            route = sanitizeRouteName(route)
            km = parseKmValue(val)
            if route and km is not None:
                result[route] = km
    return result


# ===========================================================================
# BCH 译码辅助函数
# ===========================================================================
def popcount32(x: int) -> int:
    """计算 32 位整数的二进制中 1 的个数 (population count)。"""
    x = x - ((x >> 1) & 0x55555555)
    x = (x & 0x33333333) + ((x >> 2) & 0x33333333)
    x = (x + (x >> 4)) & 0x0F0F0F0F
    return ((x * 0x01010101) & 0xFFFFFFFF) >> 24


def calcSyndrome(d31: int) -> int:
    """计算 BCH(31,21) 的 10 位伴随式。

    使用 LFSR (线性反馈移位寄存器) 模拟生成多项式 g(x) = x^10+x^9+x^8+x^6+x^5+x^3+1，
    对输入 31 位数据进行除法，余数即为伴随式。
    """
    syn = 0
    for i in range(31):
        bit = (d31 >> (30 - i)) & 1
        if syn & (1 << 9):
            # BCH(31,21) 生成多项式 g(x)=x^10+x^9+x^8+x^6+x^5+x^3+1
            # LFSR 反馈取低 10 位: 0x369 = 873
            syn = ((syn << 1) ^ bit ^ 873) & 0x3FF
        else:
            syn = ((syn << 1) ^ bit) & 0x3FF
    return syn


def buildSyndromeLut() -> Dict[int, int]:
    """构建 BCH 单比特错误伴随式反查表。

    返回: {伴随式: 错误比特位置} 字典，用于快速定位单比特错误。
    """
    lut: Dict[int, int] = {}
    for i in range(31):
        syn = calcSyndrome(1 << i)
        if syn not in lut:
            lut[syn] = i
    return lut


# ===========================================================================
# DPLL 比特恢复
# ===========================================================================
def dpllBitRecovery(bb, n, ncoPhase, ncoStep, pllIntegrator,
                    peakMax, peakMin, lastHardBit, lastBitClk, hyst=0.03):
    """DPLL (数字锁相环) 比特同步与恢复。

    使用早/迟门鉴相器跟踪比特时钟，自适应门限判决比特值，
    比例+积分修正 NCO 相位。

    参数:
        bb: 高斯平滑后的 PCM 样本数组。
        n: 样本数。
        ncoPhase: NCO 当前相位 [0, 1)。
        ncoStep: NCO 步进 (每个样本的相位增量 = baudRate/fs)。
        pllIntegrator: PLL 频率积分项。
        peakMax, peakMin: 自适应判决门限的峰/谷值。
        lastHardBit, lastBitClk: 上一个硬判决比特与时钟状态。
        hyst: 判决迟滞量。
    返回:
        tuple (bits, ncoPhase, pllIntegrator, peakMax, peakMin, lastHardBit, lastBitClk)
    """
    bits = []
    step = ncoStep
    _ph, _int, _mx, _mn, _lh, _lc = ncoPhase, pllIntegrator, peakMax, peakMin, lastHardBit, lastBitClk
    MD = ncoStep * 0.02  # 积分项上限：约为步进的 2%，限制频率修正速率
    for i in range(n):
        v = bb[i]
        # 自适应峰值/谷值跟踪：立即捕获极值，缓慢向中心衰减
        ha = max(1e-06, (_mx - _mn) * 0.5)
        if v > _mx:
            _mx = v
        else:
            _mx -= ha * 0.0005
        if v < _mn:
            _mn = v
        else:
            _mn += ha * 0.0005
        # 自适应门限 + 迟滞判决（迟滞有下限，弱信号下也保持稳定）
        mid = (_mx + _mn) * 0.5
        amp = max(1e-06, _mx - _mn)
        h = max(0.006, min(hyst, 0.15 * amp))
        if v > mid + h:
            hb = 1
        elif v < mid - h:
            hb = 0
        else:
            hb = _lh  # 迟滞区间内保持上一比特
        # 早/迟门鉴相
        if hb != _lh:
            err = _ph
            if err > 0.5:
                err -= 1.0  # 归一化到 [-0.5, 0.5]
            _int += 0.005 * err  # 积分项
            if _int > MD:
                _int = MD
            elif _int < -MD:
                _int = -MD
            _ph -= 0.1 * err + _int  # 比例 + 积分修正
        _lh = hb
        _ph += step
        # 相位过 0.5（比特中点）时若未采样则输出一个比特；采样后锁定 _lc=1
        # 直到相位回落到 <=0.5 才解锁，避免一个比特周期内重复输出
        if _ph > 0.5:
            if _lc == 0:
                bits.append(1 - hb)  # LBJ 反逻辑: 高电平 -> 0
            _lc = 1
        else:
            _lc = 0
        if _ph >= 1.0:
            _ph -= 1.0  # 进入下一比特周期
    return (bits, _ph, _int, _mx, _mn, _lh, _lc)


# ===========================================================================
# ETA 到达估算器
# ===========================================================================
class ArrivalEstimator:
    """列车到达估算器。

    根据本站公里标、列车位置、方向与速度估算 ETA (预计到达时间)。
    支持为不同线路设置不同的本站公里标。
    """

    def __init__(self, userKm: Optional[float] = None,
                 maxSeconds: float = DEFAULT_ETA_MAX_SECONDS,
                 routeKmMap: Optional[Dict[str, float]] = None):
        """初始化估算器。

        参数:
            userKm: 默认本站公里标 (km)。
            maxSeconds: ETA 最大估算秒数 (超出则不显示)。
            routeKmMap: 线路名 -> 本站公里标的映射。
        """
        self.defaultKm = None if userKm is None else float(userKm)
        self.downIncreases = True  # 约定下行公里标递增
        self.maxSeconds = float(maxSeconds)
        self.routeKmMap: Dict[str, float] = {}
        self.knownRoutes: List[str] = []
        if routeKmMap:
            for route, km in routeKmMap.items():
                self.addRouteKm(route, km)

    def getRouteKm(self, route: str) -> Optional[float]:
        """获取指定线路的本站公里标；未设置则返回默认值。"""
        route = sanitizeRouteName(route)
        if route and route in self.routeKmMap:
            return self.routeKmMap[route]
        return self.defaultKm

    def addRouteKm(self, route: str, km: Any) -> bool:
        """添加/更新一条线路的本站公里标。"""
        route = sanitizeRouteName(route)
        kmVal = parseKmValue(km)
        if not route or kmVal is None:
            return False
        self.routeKmMap[route] = kmVal
        if route not in self.knownRoutes:
            self.knownRoutes.append(route)
            self.knownRoutes = self.knownRoutes[-20:]
        return True

    def removeRouteKm(self, route: str) -> None:
        """删除指定线路的本站公里标设置。"""
        route = sanitizeRouteName(route)
        if route and route in self.routeKmMap:
            del self.routeKmMap[route]

    def setUserKm(self, userKm: Any) -> None:
        """设置默认本站公里标。"""
        self.defaultKm = parseKmValue(userKm)

    def estimateEta(self, train: str, direction: str, speed: Any,
                    position: Any, route: str, goodData: bool = True,
                    now: Optional[float] = None) -> Dict[str, Any]:
        """估算列车到达时间。

        参数:
            train: 车次号。
            direction: 方向 ('上行'/'下行')。
            speed: 速度 (km/h 字符串或数字)。
            position: 公里标 (字符串或数字)。
            route: 线路名。
            goodData: 数据是否可靠 (BCH 校验通过)。
            now: 当前时间戳，None 则取 time.time()。
        返回:
            包含 etaSeconds/etaTime/etaDistanceKm/etaStatus 的字典。
        """
        result = {'etaSeconds': None, 'etaTime': '--:--:--',
                  'etaDistanceKm': None, 'etaStatus': '等待信号',
                  'etaTrain': train, 'etaRoute': route}
        if not goodData:
            result['etaStatus'] = '错包忽略'
            return result
        route = sanitizeRouteName(route)
        if not route:
            result['etaStatus'] = '线路未知'
            return result
        if not isValidRouteName(route):
            result['etaStatus'] = '线路名无效'
            return result
        userKm = self.getRouteKm(route)
        if userKm is None:
            result['etaStatus'] = '未设置线路位置'
            return result
        if not train or train == '----':
            result['etaStatus'] = '等待车次'
            return result
        if direction not in ('上行', '下行'):
            result['etaStatus'] = '方向未知'
            return result
        spd = parseKmValue(speed)
        if spd is None or spd <= 0:
            result['etaStatus'] = '速度无效'
            return result
        trainKm = parseKmValue(position)
        if trainKm is None:
            result['etaStatus'] = '公里标无效'
            return result
        # 距离计算
        if self.downIncreases:
            dist = userKm - trainKm if direction == '下行' else trainKm - userKm
        else:
            dist = trainKm - userKm if direction == '下行' else userKm - trainKm
        if dist < -0.02:
            result.update({'etaStatus': '远离/已过'})
            return result
        dist = max(0.0, dist)
        etaSec = dist / spd * 3600.0
        if etaSec > self.maxSeconds:
            result.update({'etaDistanceKm': dist, 'etaStatus': 'ETA过大'})
            return result
        if now is None:
            now = time.time()
        etaTime = time.strftime('%H:%M:%S', time.localtime(now + etaSec))
        result.update({'etaSeconds': etaSec, 'etaTime': etaTime,
                       'etaDistanceKm': dist,
                       'etaStatus': '即将到达' if etaSec <= 10 else '接近'})
        return result


# ===========================================================================
# DSP 信号处理模块
# ===========================================================================
class IqCorrector:
    """IQ 直流校正与 I/Q 增益平衡处理器。

    通过极低通滤波估计 I、Q 两路的直流偏置并扣除；同时估计 Q/I 功率比
    平方根作为增益修正系数 (限制在 [0.9, 1.1])，修正 I/Q 通路增益失衡。
    """

    def __init__(self):
        self.dcI = 0.0  # I 路直流估计
        self.dcQ = 0.0  # Q 路直流估计
        self.gainRatio = 1.0  # Q 路相对增益修正系数

    def process(self, iq: np.ndarray) -> np.ndarray:
        """处理 IQ 复数采样，返回直流与增益修正后的复数数组。"""
        i = iq.real.astype(np.float64)
        q = iq.imag.astype(np.float64)
        # 一阶 IIR 直流估计 (时间常数约 1000 样本)
        self.dcI += 0.001 * (np.mean(i) - self.dcI)
        self.dcQ += 0.001 * (np.mean(q) - self.dcQ)
        i -= self.dcI
        q -= self.dcQ
        # Q 路增益修正
        pi, pq = float(np.mean(i * i)), float(np.mean(q * q))
        if pi > 1e-20:
            self.gainRatio += 0.0001 * (np.sqrt(pq / pi) - self.gainRatio)
            self.gainRatio = max(0.9, min(1.1, self.gainRatio))
            q *= self.gainRatio
        return (i + 1j * q).astype(np.complex64)


class DigitalDownConverter:
    """数字下变频 (DDC) / 数控本振 (NCO)。

    通过复数乘法将指定频率偏移处的信号搬移到零频 (基带)。
    偏移由 setOffset 控制，可用于硬避让 DC 或 AFC 动态补偿。
    """

    def __init__(self, sampleRate: float, offsetHz: float = 0.0):
        self.sampleRate = float(sampleRate)
        self.offsetHz = float(offsetHz)
        self.phase = 0.0  # 当前 NCO 相位累积
        self._updateIncrement()

    def _updateIncrement(self):
        """根据当前偏移与采样率计算每样本相位增量。"""
        self.increment = -2.0 * np.pi * self.offsetHz / self.sampleRate

    def setOffset(self, offsetHz: float):
        """设置新的频率偏移 (Hz)。"""
        self.offsetHz = float(offsetHz)
        self._updateIncrement()

    def addOffset(self, deltaHz: float):
        """在当前偏移上叠加增量 (Hz)。"""
        self.setOffset(self.offsetHz + float(deltaHz))

    def process(self, iq: np.ndarray) -> np.ndarray:
        """将 IQ 与本地复指数相乘完成下变频。"""
        if abs(self.offsetHz) < 0.1:
            return iq
        n = len(iq)
        ph = self.phase + self.increment * np.arange(n, dtype=np.float64)
        self.phase = (ph[-1] + self.increment) % (2.0 * np.pi)
        lo = np.exp(1j * ph).astype(np.complex64)
        return iq * lo


class ChannelFilter:
    """信道带通 FIR 滤波器。

    在指定采样率下设计通带带宽的低通型 FIR (经 DDC 后等效带通)，
    使用 Blackman-Harris 窗获得高阻带衰减；保留状态支持流式处理。
    """

    def __init__(self, sampleRate: float, bwHz: float = 15000.0):
        cut = min(bwHz / 2.0, sampleRate * 0.45)
        tw = max(bwHz * 0.1, 1000)
        nt = max(31, min(int(4 * sampleRate / tw), 511)) | 1
        self.taps = firwin(nt, cut, fs=sampleRate, window='blackmanharris').astype(np.float32)
        self.state = np.zeros(nt - 1, dtype=np.complex64)

    def process(self, iq: np.ndarray) -> np.ndarray:
        out, self.state = lfilter(self.taps, 1.0, iq, zi=self.state)
        return out


class HalfbandDecimator:
    """半带抽取器 (Half-band Decimator)。

    使用归一化截止 0.25 (fs/4) 的对称 FIR，抽取因子固定为 2。
    半带滤波器计算量约为普通 FIR 的一半。
    """

    def __init__(self, nt: int = 63):
        self.taps = firwin(nt, 0.25, window='blackmanharris').astype(np.float32)
        self.state = np.zeros(nt - 1, dtype=np.complex64)

    def process(self, iq: np.ndarray) -> np.ndarray:
        out, self.state = lfilter(self.taps, 1.0, iq, zi=self.state)
        return out[::2]


class FirDecimator:
    """通用整数抽取 FIR 滤波器。

    在 sr_in -> sr_out 之间完成低通滤波 + 整数抽取。
    """

    def __init__(self, srIn: float, srOut: float, dec: Optional[int] = None):
        self.dec = dec if dec is not None else int(srIn // srOut)
        cut = srOut / 2 * 0.9
        tw = srOut * 0.1
        nt = max(31, min(int(4 * srIn / tw), 255)) | 1
        self.taps = firwin(nt, cut, fs=srIn, window='blackmanharris').astype(np.float32)
        self.state = np.zeros(nt - 1, dtype=np.complex64)

    def process(self, iq: np.ndarray) -> np.ndarray:
        out, self.state = lfilter(self.taps, 1.0, iq, zi=self.state)
        return out[::self.dec]


class FmDiscriminator:
    """FM 鉴频器 (差分相位法)。

    对复数基带信号求相邻样本共轭乘积的相位，归一化到 [-1, 1]，
    得到对应瞬时频偏的浮点序列。
    """

    def __init__(self):
        self.prev = np.complex64(0)

    def process(self, iq: np.ndarray) -> np.ndarray:
        buf = np.empty(len(iq) + 1, dtype=np.complex64)
        buf[0] = self.prev
        buf[1:] = iq
        self.prev = iq[-1]
        return (np.angle(buf[1:] * np.conj(buf[:-1])) * (1.0 / np.pi)).astype(np.float32)


class RssiGate:
    """RSSI 载波感知门控。

    基于 RSSI (dB) 与开启/释放门限 (带迟滞) 和保持时间控制是否启用解码。
    状态机: OFF -> ARM -> ON -> HOLD -> OFF。
    """

    def __init__(self, onDb: float = DEFAULT_RSSI_THRESHOLD_DB,
                 hysteresisDb: float = DEFAULT_RSSI_HYST_DB,
                 holdMs: float = DEFAULT_RSSI_HOLD_MS,
                 confirmBlocks: int = 1, enabled: bool = True):
        self.onDb = float(onDb)
        self.hysteresisDb = float(hysteresisDb)
        self.offDb = self.onDb - self.hysteresisDb
        self.holdMs = float(holdMs)
        self.confirmBlocks = max(1, int(confirmBlocks))
        self.enabled = bool(enabled)
        self.active = False
        self.holdLeftMs = 0.0
        self.onCount = 0
        self.justActivated = False
        self.justDeactivated = False
        self.state = 'BYPASS' if not self.enabled else 'OFF'

    def updateThreshold(self, onDb: float):
        """运行时修改开启门限。"""
        self.onDb = float(onDb)
        self.offDb = self.onDb - self.hysteresisDb

    def reset(self):
        """复位状态机。"""
        self.active = False
        self.holdLeftMs = 0.0
        self.onCount = 0
        self.justActivated = False
        self.justDeactivated = False
        self.state = 'BYPASS' if not self.enabled else 'OFF'

    def update(self, rssiDb: float, audioLen: int, fsAudio: float = BASEBAND_RATE) -> bool:
        """输入当前块 RSSI，更新门控状态。

        返回: True 表示当前块处于激活状态。
        """
        self.justActivated = False
        self.justDeactivated = False
        if not self.enabled:
            self.active = True
            self.holdLeftMs = self.holdMs
            self.state = 'BYPASS'
            return True
        blockMs = 1000.0 * max(0, int(audioLen)) / float(fsAudio)
        wasActive = self.active
        if not self.active:
            if rssiDb >= self.onDb:
                self.onCount += 1
                if self.onCount >= self.confirmBlocks:
                    self.active = True
                    self.holdLeftMs = self.holdMs
            else:
                self.onCount = 0
        elif rssiDb >= self.offDb:
            self.holdLeftMs = self.holdMs
            self.onCount = self.confirmBlocks
        else:
            self.holdLeftMs -= blockMs
            if self.holdLeftMs <= 0.0:
                self.active = False
                self.holdLeftMs = 0.0
                self.onCount = 0
        self.justActivated = not wasActive and self.active
        self.justDeactivated = wasActive and (not self.active)
        if self.active:
            self.state = 'ON' if rssiDb >= self.offDb else 'HOLD'
        else:
            self.state = 'ARM' if self.onCount > 0 else 'OFF'
        return self.active


class AfcLoop:
    """自动频率控制 (AFC) 闭环。

    利用鉴频输出直流分量估计载波频偏，通过调整 DDC offset 实现闭环跟踪。
    使用信号自相关评分判断信号是否存在，仅在评分超过门限时更新 AFC。
    """

    def __init__(self, fs: float, baseDdcHz: float, maxAfcHz: float = 1500.0,
                 loopGain: float = 0.45, maxStepHz: float = 350.0,
                 minAltScore: float = 0.25):
        self.fs = float(fs)
        self.baseDdcHz = float(baseDdcHz)
        self.maxAfcHz = float(maxAfcHz)
        self.loopGain = float(loopGain)
        self.maxStepHz = float(maxStepHz)
        self.minAltScore = float(minAltScore)
        self.afcHz = 0.0       # 当前 AFC 累积补偿 (Hz)
        self.dcNorm = 0.0      # 鉴频直流平滑估计 (归一化)
        self.lastErrHz = 0.0   # 最近频偏估计 (Hz)
        self.lastScore = 0.0   # 最近信号评分
        self.updated = False   # 本次是否更新了 DDC
        self.enabled = True

    @staticmethod
    def trimmedMean(x, trim: float = 0.1) -> float:
        """截尾均值: 去掉两端 trim 比例后取均值。"""
        if len(x) == 0:
            return 0.0
        xs = np.sort(np.asarray(x, dtype=np.float32))
        k = int(len(xs) * trim)
        if k > 0 and len(xs) > 2 * k:
            xs = xs[k:-k]
        return float(np.mean(xs)) if len(xs) else 0.0

    def process(self, y, ddc: DigitalDownConverter, updateAllowed: bool = True) -> np.ndarray:
        """执行 DC 估计与 AFC 更新。

        参数:
            y: 鉴频输出 float 数组 (归一化到 [-1, 1])。
            ddc: 关联的 DDC 实例。
            updateAllowed: 是否允许更新 AFC。
        返回:
            扣除直流后的鉴频样本。
        """
        self.updated = False
        yy = np.asarray(y, dtype=np.float32)
        if not self.enabled:
            return yy.astype(np.float32, copy=False)
        if len(yy) < 160:
            return (yy - self.dcNorm).astype(np.float32)
        if not updateAllowed:
            self.lastScore = 0.0
            self.lastErrHz = self.dcNorm * self.fs * 0.5
            return (yy - self.dcNorm).astype(np.float32)
        finite = yy[np.isfinite(yy)]
        finite = finite[np.abs(finite) < 0.95]
        if len(finite) < 160:
            return (yy - self.dcNorm).astype(np.float32)
        dcNow = self.trimmedMean(finite, trim=0.1)
        maxNorm = 2.0 * self.maxAfcHz / self.fs
        dcNow = float(np.clip(dcNow, -maxNorm, maxNorm))
        yc = yy - dcNow
        # 替代性评分: -1 倍 spb 滞后自相关
        spb = max(1, int(round(self.fs / BAUD_RATE)))
        if len(yc) > spb:
            pwr = float(np.mean(yc * yc)) + 1e-12
            score = -float(np.mean(yc[:-spb] * yc[spb:])) / pwr
        else:
            score = 0.0
        self.lastScore = score
        alphaDc = 1.0 if score >= self.minAltScore else 0.01
        self.dcNorm += alphaDc * (dcNow - self.dcNorm)
        self.dcNorm = float(np.clip(self.dcNorm, -maxNorm, maxNorm))
        if score >= self.minAltScore:
            fErrHz = dcNow * self.fs * 0.5
            fErrHz = float(np.clip(fErrHz, -self.maxAfcHz, self.maxAfcHz))
            self.lastErrHz = fErrHz
            step = self.loopGain * fErrHz
            step = float(np.clip(step, -self.maxStepHz, self.maxStepHz))
            oldAfc = self.afcHz
            self.afcHz = float(np.clip(self.afcHz + step, -self.maxAfcHz, self.maxAfcHz))
            if abs(self.afcHz - oldAfc) >= 5.0:
                ddc.setOffset(self.baseDdcHz + self.afcHz)
                self.updated = True
        else:
            self.lastErrHz = self.dcNorm * self.fs * 0.5
        return (yy - self.dcNorm).astype(np.float32)


class FrontendChain:
    """RTL-SDR 接收前端信号处理流水线。

    串联: IQ 校正 → DDC → 半带抽取 → 信道 FIR → 整数抽取 → FM 鉴频 → AFC + RSSI。
    构造时根据输入采样率自动选择半带级数与抽取因子。
    """

    @staticmethod
    def computeChain(srIn: float, targetOut: float = BASEBAND_RATE,
                     targetMid: float = 240000):
        """自动计算半带级数与抽取因子。

        返回: (halfbandN, midRate, firDec, actualOut)
        """
        bestHb, bestRate, bestScore = 0, srIn, abs(srIn - targetMid)
        for hb in range(1, 8):
            rate = srIn // (2 ** hb)
            if rate < targetOut:
                break
            score = abs(rate - targetMid)
            if score <= bestScore:
                bestHb, bestRate, bestScore = hb, rate, score
        firDec = max(1, bestRate // targetOut)
        actualOut = bestRate // firDec
        return bestHb, bestRate, firDec, actualOut

    def __init__(self, sampleRate: float = RTL_SAMPLE_RATE,
                 halfbandN: Optional[int] = None, midRate: Optional[float] = None,
                 dcOffsetHz: float = DEFAULT_DC_OFFSET_HZ, userOffsetHz: float = 0.0,
                 bwHz: float = DEFAULT_BW_KHZ * 1000.0, rssiOffsetDb: float = 0.0,
                 afcEnable: bool = True, afcMaxHz: float = DEFAULT_AFC_MAX_HZ,
                 afcGain: float = 0.45):
        """构造前端流水线。

        参数:
            sampleRate: 输入采样率 (Hz)。
            halfbandN: 半带级数 (None 自动计算)。
            midRate: 中间速率 (None 自动计算)。
            dcOffsetHz: DDC 基础偏移 (Hz)。
            userOffsetHz: 用户额外偏移 (Hz)。
            bwHz: 信道带宽 (Hz)。
            rssiOffsetDb: RSSI 显示偏移 (dB)。
            afcEnable: 是否启用 AFC。
            afcMaxHz: AFC 最大修正范围 (Hz)。
            afcGain: AFC 环路增益。
        """
        self.rssiOffsetDb = rssiOffsetDb
        self.baseDdc = float(dcOffsetHz + userOffsetHz)
        self.inputSr = sampleRate
        if halfbandN is None or midRate is None:
            self.hbN, self.midRate, self.firDec, self.actualOut = self.computeChain(sampleRate)
        else:
            self.hbN = halfbandN
            self.midRate = midRate
            self.firDec = max(1, midRate // BASEBAND_RATE)
            self.actualOut = midRate // self.firDec
        # 实例化 DSP 模块
        self.iqCorrector = IqCorrector()
        self.ddc = DigitalDownConverter(sampleRate, self.baseDdc)
        self.halfbands = [HalfbandDecimator(63) for _ in range(self.hbN)]
        self.channelFilter = ChannelFilter(self.midRate, bwHz)
        self.firDecimator = FirDecimator(self.midRate, self.actualOut, dec=self.firDec)
        self.fmDiscriminator = FmDiscriminator()
        self.afc = AfcLoop(self.actualOut, self.baseDdc, maxAfcHz=afcMaxHz, loopGain=afcGain)
        self.afc.enabled = bool(afcEnable)
        # 链路描述
        ch = f'{sampleRate / 1000.0:.0f}k→DDC({self.baseDdc / 1000.0:+.0f}k+AFC)'
        if self.hbN > 0:
            ch += f'→HB×{self.hbN}→{self.midRate / 1000.0:.0f}k'
        ch += f'→CH({bwHz / 1000.0:.1f}k)→FIR÷{self.firDec}→{self.actualOut / 1000.0:.0f}k→FM→AFC'
        self.chainDesc = ch

    def process(self, iq: np.ndarray, rssiGate: Optional[RssiGate] = None):
        """处理一段 IQ 采样。

        返回: (pcmFloat, rssiDb, rxActive)
        """
        x = self.iqCorrector.process(iq)
        x = self.ddc.process(x)
        for hb in self.halfbands:
            x = hb.process(x)
        x = self.channelFilter.process(x)
        x = self.firDecimator.process(x)
        rssi = float(10.0 * np.log10(np.vdot(x, x).real / max(1, len(x)) + 1e-12) + self.rssiOffsetDb)
        y = self.fmDiscriminator.process(x)
        rxActive = True
        if rssiGate is not None:
            rxActive = rssiGate.update(rssi, len(y), self.actualOut)
        y = self.afc.process(y, self.ddc, updateAllowed=rxActive)
        return (y, rssi, rxActive)

    def resetAfc(self):
        """清零 AFC 状态并把 DDC 偏移恢复到 baseDdc。"""
        self.afc.afcHz = 0.0
        self.afc.dcNorm = 0.0
        self.afc.lastErrHz = 0.0
        self.afc.lastScore = 0.0
        self.afc.updated = False
        self.ddc.setOffset(self.baseDdc)

    def consumeAfcUpdated(self) -> bool:
        """查询 AFC 是否在本帧更新过 (查询后自动清标志)。"""
        u = self.afc.updated
        self.afc.updated = False
        return u


# ===========================================================================
# RTL-TCP 数据源
# ===========================================================================
class RtlTcpSource:
    """rtl_tcp 协议数据源。

    连接 rtl_tcp 服务 (RTL-SDR Blog v4 或 OWRX 转发)，完成协议握手后
    持续读取 IQ 数据流。支持 OWRX 模式 (dcOffset=0, 不启动 Android 驱动)。
    断线自动重连 (1 秒间隔)。
    """

    def __init__(self, host: str, port: int, freqHz: float, sampleRate: int,
                 blockSize: int, dcOffsetHz: float = 0.0, owrxMode: bool = False,
                 gainDb: float = HW_GAIN_DB, ppm: float = PPM):
        self.host = host
        self.port = port
        self.targetFreqHz = float(freqHz)    # 用户目标接收频率
        self.freqHz = float(freqHz)          # 当前下发给硬件的实际调谐频率
        self.dcOffsetHz = dcOffsetHz
        self.sampleRate = sampleRate
        self.blockSize = blockSize
        self.owrxMode = owrxMode
        self.gainDb = gainDb
        self.ppm = ppm
        self.queue: queue.Queue = queue.Queue(maxsize=60)
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.sock: Optional[socket.socket] = None
        self.lastError: Optional[str] = None
        # 网络诊断统计
        self.blockCount = 0
        self.bytesRecv = 0
        self.reconnectCount = 0
        self.droppedBlocks = 0                  # 因队列满丢弃的块数
        self.lastBlockTime = 0.0
        self.blockIntervals: List[float] = []  # 最近 30 个块间隔 (秒)
        self.blockSizes: List[int] = []        # 最近 30 个块大小 (字节)
        self.connectTime = 0.0                  # 当前连接建立时间
        self.lastRtt = 0.0                      # 最近一次 RTT (秒)
        self._blockTimeouts = 0                 # 块读取超时次数

    def _setFrequency(self, targetFreq: Optional[float] = None):
        """设置中心频率 (考虑 DC 偏移)。

        默认使用用户目标频率 targetFreqHz，计算硬件实际调谐频率后下发。
        """
        tgt = self.targetFreqHz if targetFreq is None else float(targetFreq)
        hwFreq = tgt - self.dcOffsetHz
        self.freqHz = hwFreq
        self._sendCommand(CMD_SET_FREQ, int(hwFreq))

    def _setGain(self, gainDb: float):
        """设置硬件增益 (映射到最接近的 R820T 增益)。"""
        nearest = min(R820T_GAINS, key=lambda x: abs(x - gainDb))
        self._sendCommand(CMD_SET_GAINMODE, 1)
        self._sendCommand(CMD_SET_GAIN, int(nearest * 10))
        return nearest

    def _setPpm(self, ppm: float):
        """设置频率校正 (ppm)。"""
        self._sendCommand(CMD_SET_FREQCORR, int(ppm))

    def _startAndroidDriver(self):
        """启动 Android RTL-SDR 驱动 (仅 Android 且非 OWRX 模式)。"""
        if self.owrxMode:
            return
        if os.name == 'nt' or shutil.which('am') is None:
            return
        uri = f'iqsrc://-a 127.0.0.1 -p {self.port} -s {int(self.sampleRate)} -f {int(self.targetFreqHz)} -T 0'
        try:
            subprocess.run(['am', 'start', '-a', 'android.intent.action.VIEW', '-d', uri],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
            time.sleep(3.0)
        except Exception:
            pass

    def _readerTask(self):
        """后台读取线程: 连接 → 握手 → 持续读取 IQ。

        同时维护网络诊断统计: 块计数、字节接收量、块间隔、块大小、重连次数。
        """
        chunkBytes = self.blockSize * 2
        while self.running:
            try:
                self.lastError = None
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(5.0)
                self.sock.connect((self.host, self.port))
                self.connectTime = time.time()
                self.lastBlockTime = 0.0  # 重置块间隔基准
                # 读取 12 字节握手头
                hdr = b''
                while len(hdr) < 12:
                    buf = self.sock.recv(12 - len(hdr))
                    if not buf:
                        raise ConnectionError('握手阶段连接断开')
                    hdr += buf
                self.sock.settimeout(None)
                # 发送配置命令 (频率需扣除 DC 偏移，保证 DDC 后落在目标频点)
                self._setFrequency()
                self._sendCommand(CMD_SET_SAMPLERATE, self.sampleRate)
                self._sendCommand(CMD_SET_GAINMODE, 1)
                self._sendCommand(CMD_SET_GAIN, int(self.gainDb * 10))
                self._sendCommand(CMD_SET_FREQCORR, int(self.ppm))
                self._sendCommand(CMD_SET_AGC, 0)
                stream = self.sock.makefile('rb')
                while self.running:
                    data = stream.read(chunkBytes)
                    if not data:
                        if self.running:
                            raise ConnectionError('rtl_tcp 服务端断开连接')
                        break
                    if len(data) < chunkBytes:
                        continue
                    # uint8 → complex64
                    raw = np.frombuffer(data, dtype=np.uint8).astype(np.float32)
                    iq = (raw[0::2] - 127.5) / 128.0 + 1j * (raw[1::2] - 127.5) / 128.0
                    # ---- 块级统计（与 USB 直连源共用同一口径）----
                    recordBlock(self, len(iq), len(data))
                    try:
                        self.queue.put_nowait(iq.astype(np.complex64))
                    except queue.Full:
                        self.droppedBlocks += 1  # 队列满则丢弃，reader 线程不减速
            except ConnectionRefusedError:
                if self.running:
                    if self.connectTime > 0:
                        self.reconnectCount += 1
                    self.lastError = '连接被拒，1秒后重连...'
                    time.sleep(1.0)
            except (ConnectionError, socket.error, OSError) as e:
                if self.running:
                    if self.connectTime > 0:
                        self.reconnectCount += 1
                    self.lastError = f'断开: {e}，1秒后重连...'
                    time.sleep(1.0)
            except Exception as e:
                if self.running:
                    if self.connectTime > 0:
                        self.reconnectCount += 1
                    self.lastError = f'异常: {e}，1秒后重连...'
                    time.sleep(1.0)
            finally:
                if self.sock:
                    try:
                        self.sock.close()
                    except Exception:
                        pass
                    self.sock = None

    def _sendCommand(self, cmdId: int, param: int):
        """发送 rtl_tcp 协议命令 (5 字节: 1 字节命令 + 4 字节参数)。"""
        if self.sock:
            try:
                self.sock.sendall(struct.pack('>BI', cmdId, param & 0xFFFFFFFF))
            except Exception:
                pass

    def open(self):
        """启动读取线程。"""
        self.running = True
        self._startAndroidDriver()
        self.thread = threading.Thread(target=self._readerTask, daemon=True)
        self.thread.start()

    def read(self, timeout: float = 30.0) -> np.ndarray:
        """读取一块 IQ 数据。超时抛出 RuntimeError。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                return self.queue.get(timeout=0.5)
            except queue.Empty:
                if self.lastError:
                    raise RuntimeError(self.lastError)
                if not self.running:
                    raise RuntimeError('程序退出')
        raise RuntimeError('读取超时')

    def close(self):
        """停止读取并关闭连接。"""
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass

    def getDiagnostics(self) -> Dict[str, Any]:
        """获取网络诊断数据快照。

        返回字典包含:
            blocksPerSec: 块率 (块/秒)
            avgIntervalMs: 平均块间隔 (毫秒)
            avgBlockSize: 平均块大小 (样本数)
            dataRateMbps: 等效数据速率 (Mbps, 按 complex64 吞吐计算)
            queueSize: 当前队列积压
            queueMax: 队列容量
            totalBlocks: 累计块数
            reconnectCount: 重连次数
            jitterCv: 块间隔变异系数 (std/mean)
            issues: 已识别的问题列表

        具体计算见 cr_lbj/core/source_stats.py，USB 直连源用同一套口径。
        """
        return buildDiagnostics(self, 'net')


# ===========================================================================
# 本机 RTL-SDR: 设备检测与 rtl_tcp 兜底方案
# ===========================================================================
def detect_rtl_devices(timeout: float = 10.0) -> (bool, str):
    """调用 rtl_test -t 检测本机 RTL-SDR 设备。

    返回 (是否找到设备, 原始输出/错误说明)。
    """
    exe = find_rtl_tool('rtl_test')
    if not exe:
        return False, ('未找到 rtl_test.exe。\n'
                       '请把 RTL-SDR 官方工具包（含 rtl_tcp.exe / rtl_test.exe）'
                       '放到程序目录或 RTL_TCP_Server 子目录。')
    flags = 0
    if os.name == 'nt':
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    try:
        r = subprocess.run([exe, '-t'], capture_output=True, text=True,
                           errors='replace', timeout=timeout, creationflags=flags)
        out = (r.stdout or '') + (r.stderr or '')
        low = out.lower()
        ok = bool(re.search(r'found\s+\d+\s+device', low)) or 'sn:' in low
        if 'no supported devices' in low or 'no devices found' in low:
            ok = False
        return ok, out.strip() or f'退出码 {r.returncode}'
    except subprocess.TimeoutExpired:
        return False, 'rtl_test 超时（设备可能被其他程序占用）'
    except Exception as e:
        return False, f'检测失败: {e}'


def _port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _free_port(start: int = 1234) -> int:
    """从 start 开始找一个空闲 TCP 端口。"""
    for p in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', p))
                return p
            except OSError:
                continue
    return start


class RtlUsbSource(RtlTcpSource):
    """本机 USB RTL-SDR 数据源（经 rtl_tcp 中转，兼容模式）。

    v2.5 起「本机 USB」默认走 librtlsdr 直连（见 usb_direct.RtlSdrDirectSource），
    本类保留为兜底：直连不可用时由 RtlUsbAutoSource 自动启用，也允许用户在
    数据源类型里显式选择。行为与旧版一致——若目标端口已有 rtl_tcp 在跑就直接
    复用，否则用 rtl_tcp.exe 在空闲端口启动，并在 close() 时结束进程。
    """

    def __init__(self, host: str, port: int, freqHz: float, sampleRate: int,
                 blockSize: int, dcOffsetHz: float = 0.0,
                 gainDb: float = HW_GAIN_DB, ppm: float = PPM,
                 rtlTcpPath: str = '', deviceIndex: int = 0):
        super().__init__(host, port, freqHz, sampleRate, blockSize,
                         dcOffsetHz=dcOffsetHz, owrxMode=False,
                         gainDb=gainDb, ppm=ppm)
        self.rtlTcpPath = rtlTcpPath or find_rtl_tool('rtl_tcp')
        self.deviceIndex = int(deviceIndex or 0)
        self._proc: Optional[subprocess.Popen] = None
        self._spawned = False

    def open(self):
        if not self.rtlTcpPath or not os.path.isfile(self.rtlTcpPath):
            raise RuntimeError(
                '未找到 rtl_tcp.exe。请把 RTL-SDR 工具包放到程序目录，'
                '或在配置中指定 rtl_tcp.exe 路径。')
        if not _port_open(self.host, self.port):
            self.port = _free_port(self.port)
            self._spawn(self.port)
        super().open()

    def _spawn(self, port: int):
        hwFreq = int(self.targetFreqHz - self.dcOffsetHz)
        args = [self.rtlTcpPath,
                '-a', '127.0.0.1', '-p', str(port),
                '-f', str(hwFreq), '-s', str(int(self.sampleRate)),
                '-g', str(self.gainDb)]
        if self.ppm:
            args += ['-P', str(int(self.ppm))]
        if self.deviceIndex > 0:
            args += ['-d', str(self.deviceIndex)]
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0
        self._proc = subprocess.Popen(args, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, text=True,
                                      errors='replace', creationflags=flags)
        self._spawned = True
        deadline = time.time() + 8.0
        while time.time() < deadline:
            if self._proc.poll() is not None:
                out = ''
                try:
                    out = (self._proc.stdout.read() or '').strip()
                except Exception:
                    pass
                raise RuntimeError(f'RTL-TCP 启动失败（退出码 {self._proc.returncode}）: {out}')
            if _port_open('127.0.0.1', port, 0.3):
                return
            time.sleep(0.2)
        raise RuntimeError('RTL-TCP 启动超时（8 秒内端口未就绪）')

    def close(self):
        super().close()
        if self._spawned and self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
        self._proc = None
        self._spawned = False


class RtlUsbAutoSource:
    """本机 USB 数据源：优先 librtlsdr 直连，失败时回退 rtl_tcp 中转。

    界面上的「本机 USB」只给用户一个选项，走哪条路由这里决定：直连可用就
    省掉子进程和本地 TCP；直连不可用（dll 缺失、位数不符、设备被占用）时
    自动退回旧方案，行为与 v2.5 之前一致，用户无感。

    只做转发，不复制统计逻辑：所有属性访问都落到当前激活的那个数据源上。
    """

    _fallback = None      # 类级默认值，避免 __getattr__ 递归

    def __init__(self, direct, fallbackFactory: Optional[Callable[[], Any]] = None,
                 log: Optional[Callable[[str], None]] = None):
        self._direct = direct
        self._fallbackFactory = fallbackFactory
        self._log = log
        self.mode = 'direct'

    @property
    def active(self):
        """当前真正在用的数据源对象。"""
        return self._fallback or self._direct

    def open(self):
        try:
            self._direct.open()
            self.mode = 'direct'
        except Exception as e:
            fb = self._fallbackFactory() if self._fallbackFactory else None
            if fb is None:
                raise
            if self._log:
                self._log(f'[数据源] USB 直连不可用（{e}），改用 RTL-TCP 中转')
            self._fallback = fb
            self.mode = 'tcp'
            fb.open()

    def __getattr__(self, name):
        # 除上面显式定义的成员外，一律透传给激活的数据源
        return getattr(self.active, name)


# ===========================================================================
# LBJ 解码器
# ===========================================================================
class LbjDecoder:
    """LBJ 列车预警报文实时解码器。

    流程: 高斯 FIR 平滑 → DPLL 比特恢复 → 帧同步 → BCH(31,21) 译码 →
    BCD 提取 → 报文解析 (短报文/合并报文/独立长报文) → 车次/机车/线路/公里标解析。
    """

    # 机车代号 -> 中文名称映射表
    LOCO_TABLE = {1: '解放', 3: '前进', 5: '建设', 6: 'KD7', 55: '蓝箭控车',
                  81: '东风21', 101: '东风', 102: '东风2', 103: '东风3', 104: '东风4',
                  105: '东风4客', 106: '东风4C', 107: '东风5', 108: '东风5宽', 109: '东风6',
                  110: '东风7', 111: '东风8', 112: '东风9', 113: '东风10', 114: '东方红1',
                  115: '东方红2', 116: '东方红3', 117: '东方红5', 118: '北京', 119: '北京宽',
                  120: 'ND2', 121: 'ND3', 122: 'ND4', 123: 'ND5', 124: 'NY5', 125: 'NY6',
                  126: 'NY7', 127: '轻油', 128: '东方红21', 129: '东风7B', 130: '东风5S',
                  131: '东风7C', 132: '东风7S', 133: '工矿1', 134: '工矿1F', 135: '东风4E',
                  136: '东风7D', 137: '工矿1A', 138: '东风11', 139: '天安', 140: '东风10F',
                  141: '东风4D', 142: '东风8B', 143: '东风12', 144: '东风7E', 145: 'NYJ1',
                  146: 'NZJ1', 147: 'NZJ2', 148: '东风4DJ', 149: '新曙光', 150: '神州',
                  151: 'NJ2', 152: '东风7G', 153: 'NDJ3', 157: 'FXN3D', 158: '东风11G',
                  160: 'HXN3', 161: 'HXN5', 162: 'HXN3B', 163: 'HXN5B', 167: 'FXN3B',
                  170: 'FXN5C', 171: 'FXN3-J', 201: '8G', 202: '8K', 203: '6G', 204: '6K',
                  205: '韶山1', 206: '韶山3', 207: '韶山4', 208: '韶山5', 209: '韶山6',
                  210: '韶山3B', 211: '韶山7', 212: '韶山8', 213: '韶山7B', 214: '韶山7C',
                  215: '韶山6B', 216: '韶山9', 217: '韶山7D', 218: 'DJ熊猫', 219: 'DJ1',
                  220: 'DJ2', 221: 'DJF', 222: '蓝箭动车', 223: '先锋号', 224: '韶山7E',
                  225: '韶山4G', 226: '韶山3C', 228: '天梭', 229: 'DJ4和谐', 230: 'KTT',
                  231: 'HXD1', 232: 'HXD2', 233: 'HXD3', 234: 'HXD1B', 235: 'HXD2B',
                  236: 'HXD3B', 237: 'HXD1C', 238: 'HXD2C', 239: 'HXD3C', 240: 'HXD1D',
                  241: 'HXD2D', 242: 'HXD3D', 243: 'FXD1B', 244: 'FXD2B', 245: 'FXD1',
                  246: 'FXD3', 247: 'FXD1-J', 248: 'FXD3-J', 249: 'KZ25TA', 251: 'KZ25TB',
                  252: 'HXD1D-J', 254: 'FXD1H', 299: '雪域神州', 300: 'CRH1', 301: 'CRH2',
                  302: 'CRH3', 304: 'CRH5', 305: 'CRH380A', 306: 'CRH380B', 307: 'CRH380C',
                  308: 'CRH380D', 309: 'CRH6A', 310: 'CR400AF', 311: 'CR400BF',
                  312: 'CR300AF', 313: 'CR300BF', 314: 'CRH2E', 315: 'CRH6F', 329: 'CJ1',
                  330: 'CJ2', 331: 'CJ3', 332: 'CJ4', 333: 'CJ5', 334: 'CJ6'}

    def __init__(self, fs: float = 48000, baudRate: int = 1200,
                 arrivalEstimator: Optional[ArrivalEstimator] = None):
        """初始化解码器。

        参数:
            fs: 输入 PCM 采样率 (Hz)。
            baudRate: LBJ 波特率 (bps)。
            arrivalEstimator: 关联的到达估算器实例。
        """
        self.arrivalEstimator = arrivalEstimator
        self.syndromeLut = buildSyndromeLut()  # BCH 伴随式反查表
        # 高斯 FIR 平滑滤波器 (截止 1200 Hz)
        taps = ssig.firwin(numtaps=31, cutoff=1200, fs=fs, window=('gaussian', 7.0))
        self.bSmooth = taps / np.sum(taps)
        self.ziSmooth = ssig.lfilter_zi(self.bSmooth, 1.0) * 0.0
        self.ncoPhase = 0.0
        self.ncoStep = baudRate / fs
        self.pllIntegrator = 0.0
        self.peakMax = 0.0
        self.peakMin = 0.0
        self.lastHardBit = 0
        self.lastBitClk = 0
        # 帧同步常量
        self.SYNC_STD = 2094142936   # 标准同步字
        self.SYNC_INV = 2200824359   # 反相同步字
        self.IDLE_WORD = 2055848343  # 空闲字
        # 状态机
        self.state = 0               # 0=搜同步, 1=收码字
        self.shiftReg = 0
        self.cwBitCount = 0
        self.polarity = 1            # 1=正常, -1=反相
        self.wordCount = 0
        self.framePos = 0
        self.inMessage = False
        self.currentAddr = 0
        self.currentFunc = 0
        self.currentCodewords: List[int] = []
        self.huntTimeout = 0
        self.sessions: Dict[str, dict] = {}
        self.lastTrain: Optional[str] = None
        self.currentMsgHasError = False
        self.lastWarnTime = 0.0  # 上次干扰告警时间
        # v3.2.9：车次解析不出（----）的上/下行干扰计数（诊断用，不入库）
        self.interferenceUp = 0
        self.interferenceDown = 0
        self.interferenceUnknown = 0
        # 回调
        self.onDecode: Optional[Callable[[DecodeResult], None]] = None
        self.onInterference: Optional[Callable[[str, str], None]] = None  # (方向, 告警文本)

    def resetDpllSoft(self):
        """软复位 DPLL (AFC 更新后调用)，保留帧同步状态。"""
        self.ncoPhase = 0.0
        self.pllIntegrator = 0.0
        self.peakMax = 0.0
        self.peakMin = 0.0
        self.lastHardBit = 0
        self.lastBitClk = 0

    def resetReceiverState(self):
        """完全复位接收机状态 (信号释放后调用)：DPLL + 滤波器 + 帧同步。"""
        self.resetDpllSoft()
        self.ziSmooth = ssig.lfilter_zi(self.bSmooth, 1.0) * 0.0
        self.state = 0
        self.shiftReg = 0
        self.cwBitCount = 0
        self.wordCount = 0
        self.framePos = 0
        self.inMessage = False
        self.huntTimeout = 0

    def _noteInterference(self, func: int, reason: str = '车次无法解析'):
        """记一次「解析不出车次」的干扰（v3.2.9）。

        * 按功能码判上/下行并累加计数（状态栏/诊断可见）；
        * 限速 1 秒输出一条日志提示（避免刷屏）；
        * **不产出 DecodeResult**，所以这类帧不会进数据库。
        """
        if func == 1:
            self.interferenceDown += 1
            d = '下行'
        elif func == 3:
            self.interferenceUp += 1
            d = '上行'
        else:
            self.interferenceUnknown += 1
            d = '未知'
        now = time.time()
        if now - self.lastWarnTime >= 1.0:
            self.lastWarnTime = now
            warnText = '⚠ 探测到%s信号 干扰严重（%s，已计为干扰、不入库）' % (d, reason)
            if self.onInterference:
                self.onInterference(d, warnText)

    @staticmethod
    def bcdToHexChar(c: str) -> str:
        """BCD 特殊字符 → hex 字母映射。"""
        return {'*': 'A', 'U': 'B', ' ': 'C', '-': 'D', ')': 'E', '(': 'F'}.get(c, c)

    def extractBcd(self, cwList: List[int]) -> str:
        """从码字列表提取 BCD 字符串。

        每个码字 32 位: 最高位标志，次 11 位控制，低 20 位为 5 个 BCD。
        BCD 传输前经过 4 位倒序，此处还原后查表得到字符。

        返回: BCD 字符串 (含数字与特殊字符 * U 空格 - ) ( )。
        """
        chars = []
        for cw in cwList:
            data20 = (cw >> 11) & 0xFFFFF  # 取低 20 位 BCD 数据
            for n in range(5):
                val = (data20 >> (16 - n * 4)) & 0xF
                # 4 位倒序还原
                rev = ((val & 1) << 3 | (val & 2) << 1 |
                       (val & 4) >> 1 | (val & 8) >> 3)
                chars.append('0123456789*U -)('[rev])
        return ''.join(chars)

    def bchDecodeFast(self, cwVal: int):
        """BCH(31,21) 译码 + 单比特纠错。

        返回: (correctedCw, isValid)
        """
        data31 = (cwVal >> 1) & 0x7FFFFFFF
        syn = calcSyndrome(data31)
        if syn == 0:
            return (cwVal, True)
        fp = self.syndromeLut.get(syn)
        if fp is not None:
            return (((data31 ^ (1 << fp)) << 1) | (cwVal & 1), True)
        return (cwVal, False)

    def processChunk(self, audioChunk: np.ndarray):
        """处理一段 PCM 音频: 高斯平滑 + DPLL 比特恢复 + 帧同步。"""
        bb, self.ziSmooth = ssig.lfilter(self.bSmooth, [1.0], audioChunk, zi=self.ziSmooth)
        res = dpllBitRecovery(bb, len(bb), self.ncoPhase, self.ncoStep,
                              self.pllIntegrator, self.peakMax, self.peakMin,
                              self.lastHardBit, self.lastBitClk)
        (bits, self.ncoPhase, self.pllIntegrator, self.peakMax, self.peakMin,
         self.lastHardBit, self.lastBitClk) = res
        for bit in bits:
            self.processBitStreaming(bit)

    def processBitStreaming(self, bit: int):
        """逐比特更新帧同步状态机。

        状态 0: 在 32 位移位寄存器中搜索同步字 (Hamming 距离 ≤2)。
        状态 1: 每 32 位为一个码字，BCH 译码后按类型分发。
        """
        self.shiftReg = ((self.shiftReg << 1) | bit) & 0xFFFFFFFF
        if self.state == 0:
            if popcount32(self.shiftReg ^ self.SYNC_STD) <= 2:
                self.polarity, self.state = (1, 1)
                self.wordCount = self.framePos = self.cwBitCount = self.huntTimeout = 0
            elif popcount32(self.shiftReg ^ self.SYNC_INV) <= 2:
                self.polarity, self.state = (-1, 1)
                self.wordCount = self.framePos = self.cwBitCount = self.huntTimeout = 0
            if self.inMessage:
                self.huntTimeout += 1
                if self.huntTimeout > 64:
                    self.triggerParse()
        elif self.state == 1:
            self.cwBitCount += 1
            if self.cwBitCount == 32:
                self.cwBitCount = 0
                raw = self.shiftReg if self.polarity == 1 else (~self.shiftReg) & 0xFFFFFFFF
                corrected, isBchValid = self.bchDecodeFast(raw)
                self.framePos += 1
                self.wordCount += 1
                if popcount32(corrected ^ self.SYNC_STD) <= 2:
                    self.wordCount = self.framePos = 0
                elif popcount32(corrected ^ self.IDLE_WORD) <= 2:
                    if self.inMessage:
                        self.triggerParse()
                elif (corrected >> 31) == 0:
                    # 控制字: 报文起始
                    if self.inMessage:
                        self.triggerParse()
                    self.currentFunc = (corrected >> 11) & 3
                    self.currentAddr = ((corrected >> 13) & 0x3FFFF) * 8 + (self.framePos - 1) // 2
                    self.currentCodewords = []
                    self.inMessage = True
                    self.currentMsgHasError = not isBchValid
                elif (corrected >> 31) == 1:
                    # 数据字: 追加到当前报文
                    if self.inMessage:
                        self.currentCodewords.append(corrected)
                        if not isBchValid:
                            self.currentMsgHasError = True
                if self.wordCount >= 16:
                    self.state = 0

    def triggerParse(self):
        """结束当前报文收集，执行 BCD 提取与解析。

        若报文含 BCH 不可纠错，触发干扰告警回调。
        """
        self.inMessage = False
        if self.currentCodewords:
            hasError = self.currentMsgHasError
            validForEta = not hasError
            bcd = self.extractBcd(self.currentCodewords)
            # BCH 错包: 触发干扰告警 (每秒最多一次)
            if hasError:
                now = time.time()
                if now - self.lastWarnTime >= 1.0:
                    self.lastWarnTime = now
                    d = '下行' if self.currentFunc == 1 else '上行' if self.currentFunc == 3 else '未知'
                    warnText = f'⚠ 探测到{d}信号 干扰严重'
                    if self.onInterference:
                        self.onInterference(d, warnText)
            self.decodeLbj(bcd, validForEta=validForEta, hasInterference=hasError)
            self.currentCodewords = []
            self.currentMsgHasError = False

    def decodeLbj(self, bcd: str, validForEta: bool = True, hasInterference: bool = False):
        """解析一帧 BCD 报文。

        报文类型判定:
          - 短报文: addr ∈ {1233999, 1234000} 且 BCD ≥ 15
          - 合并报文: addr ∈ {1233999, 1234000, 1234002} 且 BCD ≥ 65
          - 独立长报文: addr ∈ {1234001, 1234002} 且 BCD < 65
        """
        addr, func = (self.currentAddr, self.currentFunc)
        ct = time.time()
        # 过滤无效地址
        if addr == 1234008 or (addr in (1233999, 1234000) and func == 0
                               and len(bcd) == 5 and bcd[0] in ('-', '*') and bcd[4] != '-'):
            return
        isShort = addr in (1233999, 1234000) and len(bcd) >= 15
        isMerged = addr in (1233999, 1234000, 1234002) and len(bcd) >= 65
        isStandalone = addr in (1234001, 1234002) and len(bcd) < 65
        baseTrain = None

        # === 短报文: 解析车次/方向/速度/位置 ===
        if isShort:
            raw = bcd[0:6].strip()
            baseTrain = raw if re.match(r'^[A-Za-z0-9]+$', raw) else '----'
            # v3.2.9：车次解析不出来（BCD 前 6 位不是字母数字）→ 判为上/下行干扰，
            # 只统计 + 记日志，**绝不建会话、绝不产出 DecodeResult**（因此不入库）。
            # 旧实现会把 '----' 当车次建会话，最后存进数据库一堆「----」记录。
            if baseTrain == '----':
                self._noteInterference(func, '车次字段无法解析')
                return
            self.lastTrain = baseTrain
            direction = '下行' if func == 1 else '上行' if func == 3 else f'未知({func})'
            rs = bcd[6:9].replace(' ', '0').replace('U', '0').replace('*', '0')
            speed = str(int(rs)) if rs.isdigit() and 0 <= int(rs) <= 400 else '---'
            pr = bcd[10:15]
            if any(c in pr for c in ['*', '-', 'X', 'U']):
                position = '---.-'
            else:
                ps = pr.replace(' ', '0')
                position = f'{ps[0:4]}.{ps[4]}' if ps.isdigit() else '---.-'
            # 创建/更新会话
            if baseTrain not in self.sessions:
                self.sessions[baseTrain] = {
                    'baseTrain': baseTrain, 'prefix': '', 'direction': direction,
                    'speed': speed, 'position': position, 'loco': '----',
                    'locoCode': '---', 'route': '----', 'routeValid': False,
                    'latitude': None, 'longitude': None,
                    'isDetailed': False}
            else:
                s = self.sessions[baseTrain]
                if direction != '未知' and not direction.startswith('未知'):
                    s['direction'] = direction
                if speed != '---':
                    s['speed'] = speed
                if position != '---.-':
                    s['position'] = position
            self.sessions[baseTrain]['timestamp'] = ct

        # === 合并/独立长报文: 解析机车号、机车类型、线路名 ===
        if isMerged or isStandalone:
            tid = baseTrain if isMerged else self.lastTrain
            if not tid and isStandalone and self.sessions:
                recent = sorted(self.sessions.items(),
                                key=lambda x: x[1].get('timestamp', 0), reverse=True)
                if recent and ct - recent[0][1].get('timestamp', 0) < 10:
                    tid = recent[0][0]
            if tid and tid in self.sessions:
                if isStandalone and ct - self.sessions[tid]['timestamp'] > 8.0:
                    pass  # 独立报文间隔过久
                else:
                    buf = bcd[-50:]  # 后 50 个 BCD 含机车与线路
                    ih = ''.join(self.bcdToHexChar(c) for c in buf)
                    # 解析车次号前缀 (前 2 字节 ASCII)
                    lc = ''
                    if len(ih) >= 6:
                        try:
                            c1, c2 = int(ih[0:2], 16), int(ih[2:4], 16)
                            if c1 in range(48, 58) or c1 in range(65, 91):
                                lc += chr(c1)
                            if c2 in range(48, 58) or c2 in range(65, 91):
                                lc += chr(c2)
                        except Exception:
                            pass
                    lc = lc.replace(' ', '').strip()
                    # 解析机车代号与编号
                    lr = buf[4:12] if len(buf) >= 12 else ''
                    lm, lk = ('----', '---')
                    if len(lr) >= 3:
                        cp, np_ = lr[0:3], lr[3:].strip()
                        if cp.isdigit():
                            lk = cp
                            ti = int(cp)
                            ln = self.LOCO_TABLE.get(ti, '未知型号')
                            if not np_.isdigit():
                                np_ = '----'
                            lm = f'{ln}-{np_}'
                    # 解析线路名 (hex → GBK 解码)
                    ru = '----'
                    if len(ih) >= 30:
                        try:
                            rb = bytes.fromhex(ih[14:30])
                            dec = rb.decode('gbk', errors='ignore').replace('\x00', '').strip()
                            if dec and re.match(r'^[\u4e00-\u9fa5A-Za-z0-9\-\s]+$', dec):
                                ru = dec
                        except Exception:
                            pass
                    # 解析经纬度 (30..38 经度 DDD+MM.MMMM, 39..46 纬度 DD+MM.MMMM)
                    lat = lon = None
                    if len(ih) >= 47:
                        lon = parseDmCoordinate(ih[30:33], ih[33:39], False)
                        lat = parseDmCoordinate(ih[39:41], ih[41:47], True)
                    # 写回会话
                    if lc:
                        self.sessions[tid]['prefix'] = lc
                    if lm != '----':
                        self.sessions[tid]['loco'] = lm
                        self.sessions[tid]['locoCode'] = lk
                    if validForEta and ru != '----' and isValidRouteName(ru):
                        self.sessions[tid]['route'] = ru
                        self.sessions[tid]['routeValid'] = True
                    if lat is not None and lon is not None:
                        self.sessions[tid]['latitude'] = lat
                        self.sessions[tid]['longitude'] = lon
                    self.sessions[tid]['isDetailed'] = True
                    self.sessions[tid]['timestamp'] = ct

        # === 汇总会话并生成解码结果 ===
        aid = baseTrain if isShort else self.lastTrain
        # v3.2.9：最终车次仍为空/---- → 计干扰、只记日志，不产出结果（不入库）
        if not aid or str(aid).strip() in ('', '----', '未知'):
            self._noteInterference(func)
            return
        if aid and aid in self.sessions:
            s = self.sessions[aid]
            fullTrain = f"{s['prefix']}{s['baseTrain']}".replace(' ', '').strip()
            if not fullTrain or fullTrain in ('----', '未知'):
                self._noteInterference(func)
                return
            category = classifyTrainCategory(
                fullTrain, s['isDetailed'], speed=s.get('speed'))
            # ETA 估算
            etaInfo = {'etaSeconds': None, 'etaTime': '--:--:--',
                       'etaDistanceKm': None, 'etaStatus': '等待信号'}
            if self.arrivalEstimator:
                etaInfo = self.arrivalEstimator.estimateEta(
                    fullTrain, s['direction'], s['speed'], s['position'],
                    s['route'], goodData=validForEta, now=ct)
            # 构造解码结果
            result = DecodeResult(
                timestamp=ct,
                timeStr=datetime.fromtimestamp(ct).strftime('%Y-%m-%d %H:%M:%S'),
                train=fullTrain, baseTrain=s['baseTrain'], prefix=s.get('prefix', ''),
                direction=s['direction'], speed=s['speed'], position=s['position'],
                loco=s['loco'], locoCode=s['locoCode'], route=s['route'],
                category=category, isDetailed=s['isDetailed'],
                latitude=s.get('latitude'), longitude=s.get('longitude'),
                routeValid=bool(s.get('routeValid', False)),
                msgTypeError=self.currentMsgHasError,
                hasInterference=hasInterference,
                rawBcd=bcd, rawAddr=addr, rawFunc=func,
                rawCodewords=list(self.currentCodewords),
                rawIsShort=isShort, rawIsMerged=isMerged, rawIsStandalone=isStandalone,
                etaSeconds=etaInfo.get('etaSeconds'),
                etaTime=etaInfo.get('etaTime', '--:--:--'),
                etaDistanceKm=etaInfo.get('etaDistanceKm'),
                etaStatus=etaInfo.get('etaStatus', '等待信号'),
            )
            if self.onDecode:
                self.onDecode(result)

        # 清理 30 秒未更新的过期会话
        for k in [k for k, v in self.sessions.items() if ct - v['timestamp'] > 30]:
            del self.sessions[k]
            if self.lastTrain == k:
                self.lastTrain = None


# ===========================================================================
# LBJ 核心引擎
# ===========================================================================
class LbjCore:
    """LBJ 核心引擎: 封装数据源 + 前端流水线 + 解码器，提供简洁调用接口。

    典型用法:
        core = LbjCore(host='owrx.example.com', port=5678)
        core.onDecode = myCallback  # 设置解码回调
        core.start()                # 启动后台线程
        # ... 运行中 ...
        core.stop()                 # 停止

    也可用同步方式等待解码:
        result = core.waitForDecode(timeout=30)
    """

    def __init__(self, host: str = TCP_HOST, port: int = TCP_PORT,
                 sampleRate: int = RTL_SAMPLE_RATE, freqMhz: float = 821.2375,
                 gainDb: float = HW_GAIN_DB, ppm: float = PPM,
                 bwKhz: float = DEFAULT_BW_KHZ, blockSize: int = BLOCK_SIZE,
                 dcOffsetHz: float = 0.0, owrxMode: bool = True,
                 rssiThresholdDb: float = DEFAULT_RSSI_THRESHOLD_DB,
                 rssiHystDb: float = DEFAULT_RSSI_HYST_DB,
                 rssiHoldMs: float = DEFAULT_RSSI_HOLD_MS,
                 afcEnable: bool = True, afcMaxHz: float = DEFAULT_AFC_MAX_HZ,
                 afcGain: float = 0.45, keepAfcAfterPacket: bool = False,
                 userKm: Optional[float] = None,
                 routeKm: Optional[Any] = None,
                 etaMaxMin: float = DEFAULT_ETA_MAX_SECONDS / 60.0,
                 sourceType: str = '', rtlTcpPath: str = '',
                 rtlDeviceIndex: int = 0,
                 config: Optional[CoreConfig] = None):
        """初始化核心引擎。

        支持两种传参方式:
          1. 传入 CoreConfig 对象 (推荐，便于 GUI/CLI 管理):
                cfg = CoreConfig.load('lbj.json')
                core = LbjCore(config=cfg)
          2. 直接传入各项参数 (向后兼容):
                core = LbjCore(host='owrx.example.com', port=5678)

        参数:
            config: CoreConfig 配置对象；提供时覆盖其他参数。
            host/port: rtl_tcp 服务器地址。
            sampleRate: RTL-SDR 采样率 (Hz)。
            freqMhz: 中心频率 (MHz)。
            gainDb: 硬件增益 (dB)。
            ppm: 频率校正 (ppm)。
            bwKhz: 信道带宽 (kHz)。
            blockSize: 每次读取 IQ 样本数。
            dcOffsetHz: DDC 偏移 (Hz)，OWRX 模式应为 0。
            owrxMode: 是否为 OWRX 模式 (不启动 Android 驱动)。
            rssiThresholdDb: RSSI 开启门限 (dB)。
            rssiHystDb: RSSI 释放迟滞 (dB)。
            rssiHoldMs: RSSI 保持时间 (ms)。
            afcEnable: 是否启用 AFC。
            afcMaxHz: AFC 最大修正范围 (Hz)。
            afcGain: AFC 环路增益。
            keepAfcAfterPacket: 信号释放后是否保留 AFC。
            userKm: 本站公里标 (km)。
            routeKm: 线路公里标配置 (字符串列表或字典)。
            etaMaxMin: ETA 最大估算分钟数。
        """
        # 优先使用 config 对象
        if config is not None:
            host = config.host
            port = config.port
            sampleRate = config.sampleRate
            freqMhz = config.freqMhz
            gainDb = config.gainDb
            ppm = config.ppm
            bwKhz = config.bwKhz
            blockSize = config.blockSize
            dcOffsetHz = config.dcOffsetHz
            owrxMode = config.owrxMode
            rssiThresholdDb = config.rssiThresholdDb
            rssiHystDb = config.rssiHystDb
            rssiHoldMs = config.rssiHoldMs
            afcEnable = config.afcEnable
            afcMaxHz = config.afcMaxHz
            afcGain = config.afcGain
            keepAfcAfterPacket = config.keepAfcAfterPacket
            userKm = config.userKm
            routeKm = config.routeKm
            etaMaxMin = config.etaMaxMin
            sourceType = getattr(config, 'sourceType', 'owrx' if config.owrxMode else 'rtl_tcp')
            rtlTcpPath = getattr(config, 'rtlTcpPath', '')
            rtlDeviceIndex = getattr(config, 'rtlDeviceIndex', 0)
        self.host = host
        self.port = port
        self.sampleRate = sampleRate
        self.freqMhz = freqMhz
        self.gainDb = gainDb
        self.ppm = ppm
        self.bwKhz = bwKhz
        self.blockSize = blockSize
        self.dcOffsetHz = dcOffsetHz
        self.owrxMode = owrxMode
        self.sourceType = sourceType or ('owrx' if owrxMode else 'rtl_tcp')
        if self.sourceType == 'owrx':
            self.owrxMode = True
        self.rtlTcpPath = rtlTcpPath
        self.rtlDeviceIndex = int(rtlDeviceIndex or 0)
        # 去重窗口：同车次在此窗口内的重复报文只保留最优一条 (0=关闭)
        self.dedupeWindow = float(getattr(config, 'dedupeWindow', 2.5) or 0.0)
        self.rssiThresholdDb = rssiThresholdDb
        self.rssiHystDb = rssiHystDb
        self.rssiHoldMs = rssiHoldMs
        self.afcEnable = afcEnable
        self.afcMaxHz = afcMaxHz
        self.afcGain = afcGain
        self.keepAfcAfterPacket = keepAfcAfterPacket

        # 状态
        self.connected = False
        self.running = False
        self.rssi = -140.0
        self.rssiGateState = 'OFF'
        self.afcHz = 0.0
        self.afcErrHz = 0.0
        self.afcScore = 0.0
        # 频谱缓存 (32 个 bin，-120 dB 底噪)
        self._spectrumBins = 256
        self.spectrumSmoothed = np.full(256, -120.0, dtype=np.float64)
        # 统计
        self._bytesRecv = 0
        self._reconnectCount = 0

        # 回调
        self.onDecode: Optional[Callable[[DecodeResult], None]] = None
        self.onLog: Optional[Callable[[str], None]] = None
        self.onConnectionChange: Optional[Callable[[bool], None]] = None
        self.onInterference: Optional[Callable[[str, str], None]] = None  # (方向, 告警文本)

        # 解码结果队列 (用于 waitForDecode)
        self._decodeQueue: queue.Queue = queue.Queue(maxsize=100)

        # 线程
        self._thread: Optional[threading.Thread] = None
        self._buildChain(userKm, routeKm, etaMaxMin)

    def _usbTcpFallback(self, freqHz: float):
        """生成「回退到 rtl_tcp 中转」的工厂函数；没有 rtl_tcp.exe 则返回 None。"""
        path = self.rtlTcpPath or find_rtl_tool('rtl_tcp')
        if not path or not os.path.isfile(path):
            return None

        def make() -> RtlUsbSource:
            return RtlUsbSource(
                self.host, self.port, freqHz, self.sampleRate, self.blockSize,
                dcOffsetHz=self.dcOffsetHz, gainDb=self.gainDb, ppm=self.ppm,
                rtlTcpPath=path, deviceIndex=self.rtlDeviceIndex)
        return make

    def _buildChain(self, userKm, routeKm, etaMaxMin):
        """构造 DSP 链路。"""
        freqHz = self.freqMhz * 1e6
        routeKmMap = parseRouteKmMap(routeKm) if routeKm else {}
        self.arrivalEstimator = ArrivalEstimator(
            userKm=userKm, maxSeconds=max(1.0, etaMaxMin * 60.0),
            routeKmMap=routeKmMap)
        if self.sourceType == 'rtl_usb':
            # 直连优先，不经过 rtl_tcp 子进程；失败自动回退中转（见 RtlUsbAutoSource）
            self.source = RtlUsbAutoSource(
                RtlSdrDirectSource(
                    freqHz, self.sampleRate, self.blockSize,
                    dcOffsetHz=self.dcOffsetHz, gainDb=self.gainDb,
                    ppm=self.ppm, deviceIndex=self.rtlDeviceIndex),
                self._usbTcpFallback(freqHz),
                log=self._log)
        elif self.sourceType == 'rtl_usb_tcp':
            self.source = RtlUsbSource(
                self.host, self.port, freqHz, self.sampleRate, self.blockSize,
                dcOffsetHz=self.dcOffsetHz, gainDb=self.gainDb, ppm=self.ppm,
                rtlTcpPath=self.rtlTcpPath, deviceIndex=self.rtlDeviceIndex)
        else:
            self.source = RtlTcpSource(
                self.host, self.port, freqHz, self.sampleRate, self.blockSize,
                dcOffsetHz=self.dcOffsetHz, owrxMode=self.owrxMode,
                gainDb=self.gainDb, ppm=self.ppm)
        self.frontend = FrontendChain(
            self.sampleRate, dcOffsetHz=self.dcOffsetHz,
            bwHz=self.bwKhz * 1000.0, afcEnable=self.afcEnable,
            afcMaxHz=self.afcMaxHz, afcGain=self.afcGain)
        self.decoder = LbjDecoder(
            self.frontend.actualOut, BAUD_RATE,
            arrivalEstimator=self.arrivalEstimator)
        # 设置解码回调
        self.decoder.onDecode = self._onDecode
        self.decoder.onInterference = self._onInterference
        self._dedupe = RecordDeduplicator(self.dedupeWindow)

    def _onDecode(self, result: DecodeResult):
        """解码回调: 补信号质量 → 同车次去重 → 转发。

        v2.1 起改用 RecordDeduplicator：同一车次在 dedupeWindow 内
        只保留质量最高的一条；更优记录沿用同一 uid，供 UI/DB 就地替换。
        """
        result.rssi = self.rssi
        result.afcHz = self.afcHz
        result.afcErrHz = self.afcErrHz
        result.afcScore = self.afcScore
        kept = self._dedupe.apply(result)
        if kept is None:
            return
        result = kept
        # 放入队列
        try:
            self._decodeQueue.put_nowait(result)
        except queue.Full:
            pass
        # 转发回调
        if self.onDecode:
            self.onDecode(result)

    def _onInterference(self, direction: str, warnText: str):
        """干扰告警回调: 转发到上层。"""
        if self.onInterference:
            self.onInterference(direction, warnText)
        if self.onLog:
            self.onLog(f'[告警] {warnText}')

    def _log(self, msg: str):
        """输出日志 (通过回调或 print)。"""
        if self.onLog:
            self.onLog(msg)
        else:
            print(f'[{time.strftime("%H:%M:%S")}] {msg}')

    def start(self):
        """启动后台 DSP 线程。"""
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        srcName = SOURCE_TYPE_NAMES.get(self.sourceType, self.sourceType)
        # 直连 / OWRX 不走 TCP，端点信息没意义，只报射频参数
        endpoint = '' if self.sourceType in ('rtl_usb', 'owrx') else f' {self.host}:{self.port}'
        self._log(f'[启动] {srcName}{endpoint} '
                  f'采样率 {self.sampleRate // 1000}k 频率 {self.freqMhz:.4f} MHz')
        self._log(f'[链路] {self.frontend.chainDesc}')

    def stop(self):
        """停止 DSP 线程。"""
        self.running = False
        try:
            self.source.close()
        except Exception:
            pass
        if self._thread:
            self._thread.join(timeout=3)
        self._log('[停止] DSP 线程已退出')

    def _run(self):
        """DSP 主循环。"""
        try:
            self.source.open()
        except Exception as e:
            self._log(f'[错误] 无法打开数据源: {e}')
            self._setConnected(False)
            return

        while self.running:
            # 读取 IQ
            try:
                iq = self.source.read(timeout=30)
            except RuntimeError as e:
                msg = str(e)
                if '程序退出' in msg:
                    break
                if self.connected:
                    self._setConnected(False)
                self._reconnectCount += 1
                self._log(f'[断连] {msg}, 1秒后重连...')
                time.sleep(1.0)
                continue

            if not self.connected:
                self._setConnected(True)
                self._log('[连接] 数据流已连接')

            # 更新统计
            self._bytesRecv += len(iq) * 8  # complex64 = 8 bytes

            # 前端处理
            try:
                pcm, rssi, rxActive = self.frontend.process(iq, self._getRssiGate())
            except Exception as e:
                self._log(f'[DSP错误] {e}')
                continue

            # ---- FFT 频谱 (256 bin, v4.0) ----
            try:
                nfft = 1024
                seg = iq[:nfft] * np.hanning(nfft)
                spec = np.fft.fftshift(np.fft.fft(seg))
                mag = np.abs(spec) / (nfft * np.mean(np.hanning(nfft)))
                db = 20.0 * np.log10(np.maximum(mag, 1e-12))
                bins = self._spectrumBins
                chunk = nfft // bins
                pooled = np.array([np.max(db[i * chunk:(i + 1) * chunk])
                                   for i in range(bins)])
                self.spectrumSmoothed = 0.75 * self.spectrumSmoothed + 0.25 * pooled
            except Exception:
                pass

            self.rssi = rssi
            self.afcHz = self.frontend.afc.afcHz
            self.afcErrHz = self.frontend.afc.lastErrHz
            self.afcScore = self.frontend.afc.lastScore

            if self.frontend.consumeAfcUpdated():
                self.decoder.resetDpllSoft()

            # 解码
            rssiGate = self._getRssiGate()
            if rxActive:
                try:
                    self.decoder.processChunk(pcm)
                except Exception as e:
                    self._log(f'[解码错误] {e}')
            elif rssiGate.justDeactivated:
                # 信号刚释放（仅此一帧）: 复位接收状态与 AFC，避免噪声期间频繁复位丢失同步
                self.decoder.resetReceiverState()
                if not self.keepAfcAfterPacket and self.frontend.afc.enabled:
                    self.frontend.resetAfc()
                    self.afcHz = 0.0
                    self.afcErrHz = 0.0
                    self.afcScore = 0.0

    def _getRssiGate(self):
        """获取/创建 RSSI 门控实例。"""
        if not hasattr(self, '_rssiGate'):
            self._rssiGate = RssiGate(
                onDb=self.rssiThresholdDb, hysteresisDb=self.rssiHystDb,
                holdMs=self.rssiHoldMs, enabled=True)
        return self._rssiGate

    def _setConnected(self, val: bool):
        """更新连接状态并通知回调。"""
        self.connected = val
        if self.onConnectionChange:
            self.onConnectionChange(val)

    def waitForDecode(self, timeout: float = 30.0) -> Optional[DecodeResult]:
        """阻塞等待一次解码结果。

        参数:
            timeout: 超时秒数。
        返回:
            DecodeResult 或 None (超时)。
        """
        try:
            return self._decodeQueue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _sourceDisplayName(self) -> str:
        """数据源显示名；USB 直连失败回退中转时在名字上标出来。"""
        name = SOURCE_TYPE_NAMES.get(self.sourceType, self.sourceType)
        if self.sourceType == 'rtl_usb' and getattr(self.source, 'mode', '') == 'tcp':
            name += ' (已回退中转)'
        return name

    def getStatus(self) -> Dict[str, Any]:
        """获取当前状态快照。"""
        return {
            'connected': self.connected,
            'running': self.running,
            'rssi': self.rssi,
            'rssiThreshold': self.rssiThresholdDb,
            'rssiGate': self._rssiGate.state if hasattr(self, '_rssiGate') else 'OFF',
            'afcHz': self.afcHz,
            'afcErrHz': self.afcErrHz,
            'afcScore': self.afcScore,
            'sampleRate': self.sampleRate,
            'freqMhz': self.freqMhz,
            'chainDesc': self.frontend.chainDesc,
            'sourceType': self.sourceType,
            'sourceName': self._sourceDisplayName(),
            'dedupeWindow': self.dedupeWindow,
            'dupDropped': self._dedupe.dropped if hasattr(self, '_dedupe') else 0,
            'dupUpgraded': self._dedupe.upgraded if hasattr(self, '_dedupe') else 0,
            # v3.2.9：解析不出车次的干扰计数（上/下行分开；这些帧不入库）
            'interferenceUp': getattr(self.decoder, 'interferenceUp', 0),
            'interferenceDown': getattr(self.decoder, 'interferenceDown', 0),
            'interferenceUnknown': getattr(self.decoder, 'interferenceUnknown', 0),
        }

    def getNetworkDiagnostics(self) -> Dict[str, Any]:
        """获取链路层诊断数据（网络源与 USB 直连源同口径）。

        返回当前数据源 getDiagnostics() 的结果；若数据源尚未建立则返回空诊断。
        """
        if hasattr(self, 'source') and self.source:
            return self.source.getDiagnostics()
        return {
            'blocksPerSec': 0.0, 'avgIntervalMs': 0.0, 'avgBlockSize': 0.0,
            'dataRateMbps': 0.0, 'queueSize': 0, 'queueMax': 60,
            'droppedBlocks': 0, 'totalBlocks': 0, 'reconnectCount': 0, 'jitterCv': 0.0, 'issues': [],
        }

    def setRssiThreshold(self, thresholdDb: float):
        """运行时修改 RSSI 门限。"""
        self.rssiThresholdDb = thresholdDb
        if hasattr(self, '_rssiGate'):
            self._rssiGate.updateThreshold(thresholdDb)

    def setUserKm(self, userKm: float):
        """设置本站公里标。"""
        self.arrivalEstimator.setUserKm(userKm)

    def addRouteKm(self, route: str, km: float):
        """添加线路公里标。"""
        self.arrivalEstimator.addRouteKm(route, km)

    def removeRouteKm(self, route: str):
        """删除线路公里标。"""
        self.arrivalEstimator.removeRouteKm(route)

    def getConfig(self) -> CoreConfig:
        """获取当前运行配置的快照 (CoreConfig 对象)。"""
        return CoreConfig(
            host=self.host, port=self.port, sampleRate=self.sampleRate,
            freqMhz=self.freqMhz, gainDb=self.gainDb, ppm=self.ppm,
            bwKhz=self.bwKhz, blockSize=self.blockSize,
            dcOffsetHz=self.dcOffsetHz, owrxMode=self.owrxMode,
            rssiThresholdDb=self.rssiThresholdDb, rssiHystDb=self.rssiHystDb,
            rssiHoldMs=self.rssiHoldMs, afcEnable=self.afcEnable,
            afcMaxHz=self.afcMaxHz, afcGain=self.afcGain,
            keepAfcAfterPacket=self.keepAfcAfterPacket,
            userKm=self.arrivalEstimator.defaultKm,
            routeKm=[f'{r}={km}' for r, km in self.arrivalEstimator.routeKmMap.items()],
            etaMaxMin=self.arrivalEstimator.maxSeconds / 60.0,
            sourceType=self.sourceType, rtlTcpPath=self.rtlTcpPath,
            rtlDeviceIndex=self.rtlDeviceIndex,
            dedupeWindow=self.dedupeWindow,
        )

    def applyHotConfig(self, config: CoreConfig):
        """热更新配置 (无需重启 DSP)。

        仅更新以下字段:
            rssiThresholdDb, rssiHystDb, rssiHoldMs,
            userKm, routeKm, keepAfcAfterPacket
        其他字段变更需调用 restartWithConfig。
        """
        self.rssiThresholdDb = config.rssiThresholdDb
        self.rssiHystDb = config.rssiHystDb
        self.rssiHoldMs = config.rssiHoldMs
        self.keepAfcAfterPacket = config.keepAfcAfterPacket
        self.dedupeWindow = float(getattr(config, 'dedupeWindow',
                                          self.dedupeWindow) or 0.0)
        if hasattr(self, '_dedupe'):
            self._dedupe.window = self.dedupeWindow
        if hasattr(self, '_rssiGate'):
            self._rssiGate.updateThreshold(config.rssiThresholdDb)
            self._rssiGate.hysteresisDb = config.rssiHystDb
            self._rssiGate.offDb = config.rssiThresholdDb - config.rssiHystDb
            self._rssiGate.holdMs = config.rssiHoldMs
        if config.userKm is not None:
            self.arrivalEstimator.setUserKm(config.userKm)
        if config.routeKm:
            self.arrivalEstimator.routeKmMap.clear()
            for item in config.routeKm:
                for part in str(item).split(','):
                    part = part.strip()
                    if '=' in part:
                        r, v = part.split('=', 1)
                        self.arrivalEstimator.addRouteKm(r, v)

    def restartWithConfig(self, config: CoreConfig):
        """用新配置重启 DSP 线程 (涉及链路重建)。

        会先停止当前线程，再用新参数重建 DSP 链路并启动。
        """
        wasRunning = self.running
        if wasRunning:
            self.stop()
        # 用新配置覆盖实例属性
        self.host = config.host
        self.port = config.port
        self.sampleRate = config.sampleRate
        self.freqMhz = config.freqMhz
        self.gainDb = config.gainDb
        self.ppm = config.ppm
        self.bwKhz = config.bwKhz
        self.blockSize = config.blockSize
        self.dcOffsetHz = config.dcOffsetHz
        self.owrxMode = config.owrxMode
        self.sourceType = getattr(config, 'sourceType',
                                  'owrx' if config.owrxMode else 'rtl_tcp')
        self.rtlTcpPath = getattr(config, 'rtlTcpPath', '')
        self.rtlDeviceIndex = getattr(config, 'rtlDeviceIndex', 0)
        self.rssiThresholdDb = config.rssiThresholdDb
        self.rssiHystDb = config.rssiHystDb
        self.rssiHoldMs = config.rssiHoldMs
        self.afcEnable = config.afcEnable
        self.afcMaxHz = config.afcMaxHz
        self.afcGain = config.afcGain
        self.keepAfcAfterPacket = config.keepAfcAfterPacket
        # 重建链路
        if hasattr(self, '_rssiGate'):
            del self._rssiGate
        self._buildChain(config.userKm, config.routeKm, config.etaMaxMin)
        if wasRunning:
            self.start()


# ===========================================================================
# 模块测试
# ===========================================================================
if __name__ == '__main__':
    # 简单测试: 连接并等待解码
    print('RTL_LBJ_core.py — 核心库测试')
    print(f'作者: BG2GBQ')
    print(f'License: GPL v3')
    print()

    def onDecode(result: DecodeResult):
        print(f'[{result.timeStr}] 车次={result.train} 方向={result.direction} '
              f'速度={result.speed} 位置={result.position} 机车={result.loco} '
              f'线路={result.route} 类别={result.category}')
        print(f'  原始: BCD={result.rawBcd} ADDR={result.rawAddr} FUNC={result.rawFunc} '
              f'类型={"短" if result.rawIsShort else "合并" if result.rawIsMerged else "独立"}')
        print(f'  信号: RSSI={result.rssi:.1f}dB AFC={result.afcHz:+.0f}Hz '
              f'评分={result.afcScore:.2f} ETA={result.etaTime} ({result.etaStatus})')

    def onLog(msg: str):
        print(f'[LOG] {msg}')

    def onConn(connected: bool):
        print(f'[连接] {"已连接" if connected else "已断开"}')

    core = LbjCore(
        host='owrx.example.com', port=5678,
        sampleRate=960000, freqMhz=821.2375,
        owrxMode=True, dcOffsetHz=0.0,
        onDecode=None,  # 下面用赋值方式
    )
    core.onDecode = onDecode
    core.onLog = onLog
    core.onConnectionChange = onConn

    print(f'链路: {core.frontend.chainDesc}')
    print('启动 DSP... (Ctrl+C 退出)')
    core.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print('\n停止...')
        core.stop()
