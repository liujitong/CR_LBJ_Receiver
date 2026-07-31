# -*- coding: utf-8 -*-
"""
loco_info.py — 中国铁路机车车辆信息映射表。

用于根据 LBJ 报文中解析出的"机车代号"或"机车号"前缀，查询机车的简要信息。
可继续扩展补充更多车型。
"""

from typing import Optional, Dict, Any


# 机车代号 / 型号前缀 映射表
LOCO_INFO: Dict[str, Dict[str, Any]] = {
    "HXD1": {
        "name": "和谐电1型 (HXD1)",
        "type": "电力机车",
        "maker": "中车株洲/西门子",
        "axle": "Co'Co'",
        "power": "9600 kW",
        "speed": "120 km/h",
        "brief": "八轴大功率交流传动电力机车，主要用于重载货运。",
    },
    "HXD1B": {
        "name": "和谐电1B型 (HXD1B)",
        "type": "电力机车",
        "maker": "中车株洲",
        "axle": "Co'Co'",
        "power": "9600 kW",
        "speed": "120 km/h",
        "brief": "六轴大功率交流传动电力机车，适用于重载货运干线。",
    },
    "HXD1C": {
        "name": "和谐电1C型 (HXD1C)",
        "type": "电力机车",
        "maker": "中车株洲",
        "axle": "Co'Co'",
        "power": "7200 kW",
        "speed": "120 km/h",
        "brief": "六轴交流传动电力机车，客货通用，运用广泛。",
    },
    "HXD1D": {
        "name": "和谐电1D型 (HXD1D)",
        "type": "电力机车",
        "maker": "中车株洲",
        "axle": "Co'Co'",
        "power": "7200 kW",
        "speed": "160 km/h",
        "brief": "准高速客运电力机车，常用于直特、特快列车牵引。",
    },
    "HXD2": {
        "name": "和谐电2型 (HXD2)",
        "type": "电力机车",
        "maker": "中车大同/阿尔斯通",
        "axle": "Co'Co'",
        "power": "10000 kW",
        "speed": "120 km/h",
        "brief": "八轴大功率交流传动电力机车，主要用于重载货运。",
    },
    "HXD2B": {
        "name": "和谐电2B型 (HXD2B)",
        "type": "电力机车",
        "maker": "中车大同",
        "axle": "Co'Co'",
        "power": "9600 kW",
        "speed": "120 km/h",
        "brief": "六轴大功率交流传动电力机车，适用于重载货运。",
    },
    "HXD2C": {
        "name": "和谐电2C型 (HXD2C)",
        "type": "电力机车",
        "maker": "中车大同",
        "axle": "Co'Co'",
        "power": "7200 kW",
        "speed": "120 km/h",
        "brief": "六轴交流传动电力机车，客货通用。",
    },
    "HXD3": {
        "name": "和谐电3型 (HXD3)",
        "type": "电力机车",
        "maker": "中车大连/东芝",
        "axle": "Co'Co'",
        "power": "7200 kW",
        "speed": "120 km/h",
        "brief": "六轴交流传动电力机车，主要用于货运。",
    },
    "HXD3B": {
        "name": "和谐电3B型 (HXD3B)",
        "type": "电力机车",
        "maker": "中车大连",
        "axle": "Co'Co'",
        "power": "9600 kW",
        "speed": "120 km/h",
        "brief": "六轴大功率交流传动电力机车，重载货运主力。",
    },
    "HXD3C": {
        "name": "和谐电3C型 (HXD3C)",
        "type": "电力机车",
        "maker": "中车大连",
        "axle": "Co'Co'",
        "power": "7200 kW",
        "speed": "120 km/h",
        "brief": "六轴交流传动电力机车，客货通用，运用非常广泛。",
    },
    "HXD3D": {
        "name": "和谐电3D型 (HXD3D)",
        "type": "电力机车",
        "maker": "中车大连",
        "axle": "Co'Co'",
        "power": "7200 kW",
        "speed": "160 km/h",
        "brief": "准高速客运电力机车，俗称'红枣'，广泛用于直达、特快列车。",
    },
    "SS4": {
        "name": "韶山4型 (SS4)",
        "type": "电力机车",
        "maker": "中车株洲",
        "axle": "2(Bo-Bo)",
        "power": "6400 kW",
        "speed": "100 km/h",
        "brief": "交—直流电传动重载货运电力机车，曾是中国铁路货运主力。",
    },
    "SS4G": {
        "name": "韶山4改型 (SS4G)",
        "type": "电力机车",
        "maker": "中车株洲",
        "axle": "2(Bo-Bo)",
        "power": "6400 kW",
        "speed": "100 km/h",
        "brief": "SS4 改进型电力机车，货运干线常见车型。",
    },
    "SS7": {
        "name": "韶山7型 (SS7)",
        "type": "电力机车",
        "maker": "中车大同",
        "axle": "Bo-Bo-Bo",
        "power": "4800 kW",
        "speed": "100 km/h",
        "brief": "交—直流电传动电力机车，主要用于山区铁路。",
    },
    "SS7C": {
        "name": "韶山7C型 (SS7C)",
        "type": "电力机车",
        "maker": "中车大同",
        "axle": "Bo-Bo-Bo",
        "power": "4800 kW",
        "speed": "120 km/h",
        "brief": "客运电力机车，曾在西南、西北地区广泛运用。",
    },
    "SS7D": {
        "name": "韶山7D型 (SS7D)",
        "type": "电力机车",
        "maker": "中车大同",
        "axle": "Bo-Bo-Bo",
        "power": "4800 kW",
        "speed": "170 km/h",
        "brief": "准高速客运电力机车，曾用于宝成线等山区干线。",
    },
    "SS7E": {
        "name": "韶山7E型 (SS7E)",
        "type": "电力机车",
        "maker": "中车大同",
        "axle": "Co-Co",
        "power": "4800 kW",
        "speed": "170 km/h",
        "brief": "准高速客运电力机车，曾牵引特快列车。",
    },
    "SS8": {
        "name": "韶山8型 (SS8)",
        "type": "电力机车",
        "maker": "中车株洲",
        "axle": "Bo-Bo",
        "power": "3600 kW",
        "speed": "170 km/h",
        "brief": "准高速客运电力机车，中国铁路提速第一代主力客运机车。",
    },
    "SS9": {
        "name": "韶山9型 (SS9)",
        "type": "电力机车",
        "maker": "中车株洲",
        "axle": "Co-Co",
        "power": "4800 kW",
        "speed": "170 km/h",
        "brief": "准高速客运电力机车，曾广泛用于京沪、京广等干线特快列车。",
    },
    "SS9G": {
        "name": "韶山9改型 (SS9G)",
        "type": "电力机车",
        "maker": "中车株洲",
        "axle": "Co-Co",
        "power": "4800 kW",
        "speed": "170 km/h",
        "brief": "SS9 改进型客运电力机车，准高速干线常见。",
    },
    "DF4": {
        "name": "东风4型 (DF4)",
        "type": "内燃机车",
        "maker": "中车大连",
        "axle": "Co-Co",
        "power": "2430 kW",
        "speed": "100/120/145 km/h",
        "brief": "交—直流电传动内燃机车，中国铁路历史上产量最大、运用最广的内燃机车。",
    },
    "DF4B": {
        "name": "东风4B型 (DF4B)",
        "type": "内燃机车",
        "maker": "中车大连/资阳/大同",
        "axle": "Co-Co",
        "power": "1985 kW",
        "speed": "100 km/h",
        "brief": "客货运通用内燃机车，俗称'西瓜'，运用极其广泛。",
    },
    "DF4C": {
        "name": "东风4C型 (DF4C)",
        "type": "内燃机车",
        "maker": "中车大连",
        "axle": "Co-Co",
        "power": "2165 kW",
        "speed": "100 km/h",
        "brief": "货运内燃机车，DF4 系列改进型。",
    },
    "DF4D": {
        "name": "东风4D型 (DF4D)",
        "type": "内燃机车",
        "maker": "中车大连",
        "axle": "Co-Co",
        "power": "2425 kW",
        "speed": "145 km/h",
        "brief": "客货运通用内燃机车，准高速版曾用于快速列车。",
    },
    "东风4D": {
        "name": "东风4D型 (DF4D)",
        "type": "内燃机车",
        "maker": "中车大连",
        "axle": "Co-Co",
        "power": "2425 kW",
        "speed": "145 km/h",
        "brief": "客货运通用内燃机车，准高速版曾用于快速列车。",
    },
    "DF5": {
        "name": "东风5型 (DF5)",
        "type": "内燃机车",
        "maker": "中车唐山/大连",
        "axle": "Co-Co",
        "power": "920 kW",
        "speed": "80 km/h",
        "brief": "调车内燃机车，广泛用于车站调车作业。",
    },
    "东风5":{
        "name": "东风5型 (DF5)",
        "type": "内燃机车",
        "maker": "中车唐山/大连",
        "axle": "Co-Co",
        "power": "920 kW",
        "speed": "80 km/h",
        "brief": "调车内燃机车，广泛用于车站调车作业。",
    },
    "DF7": {
        "name": "东风7型 (DF7)",
        "type": "内燃机车",
        "maker": "中车北京二七",
        "axle": "Co-Co",
        "power": "1470 kW",
        "speed": "100 km/h",
        "brief": "调车及小运转内燃机车。",
    },
    "DF8B": {
        "name": "东风8B型 (DF8B)",
        "type": "内燃机车",
        "maker": "中车戚墅堰",
        "axle": "Co-Co",
        "power": "3680 kW",
        "speed": "100 km/h",
        "brief": "大功率货运内燃机车，主要用于干线重载货运。",
    },
    "DF11": {
        "name": "东风11型 (DF11)",
        "type": "内燃机车",
        "maker": "中车戚墅堰",
        "axle": "Co-Co",
        "power": "3040 kW",
        "speed": "170 km/h",
        "brief": "准高速客运内燃机车，曾用于京沪、京广等干线提速列车。",
    },
    "DF11G": {
        "name": "东风11G型 (DF11G)",
        "type": "内燃机车",
        "maker": "中车戚墅堰",
        "axle": "2(Co-Co)",
        "power": "6080 kW",
        "speed": "170 km/h",
        "brief": "双机重联准高速客运内燃机车，曾牵引直达特快列车。",
    },
    "HXN3": {
        "name": "和谐内3型 (HXN3)",
        "type": "内燃机车",
        "maker": "中车大连/EMD",
        "axle": "Co-Co",
        "power": "3300 kW",
        "speed": "120 km/h",
        "brief": "大功率交流传动内燃机车，主要用于重载货运。",
    },
    "HXN5": {
        "name": "和谐内5型 (HXN5)",
        "type": "内燃机车",
        "maker": "中车戚墅堰/GE",
        "axle": "Co-Co",
        "power": "3300 kW",
        "speed": "120 km/h",
        "brief": "大功率交流传动内燃机车，货运干线运用广泛。",
    },
    "FXD1": {
        "name": "复兴电1型 (FXD1)",
        "type": "电力机车",
        "maker": "中车株洲/大同",
        "axle": "Bo-Bo",
        "power": "2×5600 kW",
        "speed": "160 km/h",
        "brief": "动力集中动车组动力车，用于复兴号动力集中动车组。",
    },
    "FXD3": {
        "name": "复兴电3型 (FXD3)",
        "type": "电力机车",
        "maker": "中车大连",
        "axle": "Bo-Bo",
        "power": "2×5600 kW",
        "speed": "160 km/h",
        "brief": "动力集中动车组动力车，用于复兴号动力集中动车组。",
    },
    "CRH1": {
        "name": "和谐号 CRH1",
        "type": "高速动车组",
        "maker": "BST(四方-庞巴迪)",
        "axle": "动力分散",
        "power": "—",
        "speed": "200/250 km/h",
        "brief": "和谐号电力动车组，广泛用于城际铁路及干线高铁。",
    },
    "CRH2": {
        "name": "和谐号 CRH2",
        "type": "高速动车组",
        "maker": "中车青岛四方",
        "axle": "动力分散",
        "power": "—",
        "speed": "200/250/300 km/h",
        "brief": "和谐号电力动车组，基于日本新干线 E2 技术引进消化吸收。",
    },
    "CRH3": {
        "name": "和谐号 CRH3",
        "type": "高速动车组",
        "maker": "中车唐山/长客",
        "axle": "动力分散",
        "power": "—",
        "speed": "300/350 km/h",
        "brief": "和谐号电力动车组，基于西门子 Velaro 平台。",
    },
    "CRH5": {
        "name": "和谐号 CRH5",
        "type": "高速动车组",
        "maker": "中车长春轨道客车",
        "axle": "动力分散",
        "power": "—",
        "speed": "200/250 km/h",
        "brief": "和谐号电力动车组，广泛用于东北、西北及兰新高铁。",
    },
    "CRH380": {
        "name": "和谐号 CRH380 系列",
        "type": "高速动车组",
        "maker": "中车四方/长客/唐山",
        "axle": "动力分散",
        "power": "—",
        "speed": "350/380 km/h",
        "brief": "和谐号高速动车组，中国自主研发设计，最高运营时速 380 km/h。",
    },
    "CR400": {
        "name": "复兴号 CR400 系列",
        "type": "高速动车组",
        "maker": "中车四方/长客",
        "axle": "动力分散",
        "power": "—",
        "speed": "350 km/h",
        "brief": "复兴号中国标准动车组，运营时速 350 km/h，代表车型 CR400AF/BF。",
    },
}


# 机车图片 URL 映射表 — 图片来源: Trainfanz.com (我们的火车站)
# 电力机车列表页: https://www.trainfanz.com/h-col-229.html
# 内燃机车列表页: https://www.trainfanz.com/h-col-141.html
LOCO_IMAGES: Dict[str, str] = {
    # --- 韶山系列 (电力) ---
    "SS4":  "https://aka.doubaocdn.com/s/2Vk3f1Vaqx",
    "SS4B": "https://aka.doubaocdn.com/s/Rd6NQTUjdN",
    "SS4G": "https://aka.doubaocdn.com/s/D34fLYUow3",
    "SS7":  "https://aka.doubaocdn.com/s/4m0twUde4X",
    "SS7C": "https://aka.doubaocdn.com/s/SJcRTaUEu2",
    "SS7D": "https://aka.doubaocdn.com/s/Awu4YMPtkP",
    "SS7E": "https://aka.doubaocdn.com/s/mNonVs4i3J",
    "SS8":  "https://aka.doubaocdn.com/s/vYOxljKRZo",
    "SS9":  "https://aka.doubaocdn.com/s/q1f42zGjo2",
    "SS9G": "https://aka.doubaocdn.com/s/K6iUKUAfeS",
    # --- 和谐电系列 (电力) ---
    "HXD1":  "https://aka.doubaocdn.com/s/67vUCc55v6",
    "HXD1B": "https://aka.doubaocdn.com/s/KOiVDGVH7h",
    "HXD1C": "https://aka.doubaocdn.com/s/ziQzJCuspy",
    "HXD1D": "https://aka.doubaocdn.com/s/0XPfN2V72a",
    "HXD2":  "https://aka.doubaocdn.com/s/443TDfouEV",
    "HXD2B": "https://aka.doubaocdn.com/s/qEY5r6HYGq",
    "HXD2C": "https://aka.doubaocdn.com/s/n3Cz2nVrq7",
    "HXD3":  "https://aka.doubaocdn.com/s/oafZnEb8Pr",
    "HXD3B": "https://aka.doubaocdn.com/s/8CicuzIThG",
    "HXD3C": "https://aka.doubaocdn.com/s/huWgs7NAK1",
    "HXD3D": "https://aka.doubaocdn.com/s/ngWhBaVEVp",
    # --- 东风系列 (内燃) ---
    "DF4":   "https://aka.doubaocdn.com/s/ahcJ5eKOaf",
    "DF4B":  "https://aka.doubaocdn.com/s/Y1v5RYPa8t",
    "DF5":   "https://aka.doubaocdn.com/s/0Li8i2QF6z",
    "DF7":   "https://aka.doubaocdn.com/s/HKlBkI72Zu",
    "DF8B":  "https://aka.doubaocdn.com/s/znAddHi1dq",
    "DF11":  "https://aka.doubaocdn.com/s/ahcJ5eKOaf",
    "DF11G": "https://aka.doubaocdn.com/s/ahcJ5eKOaf",
}

# 机车来源标注
LOCO_SOURCE = "Trainfanz.com (我们的火车站)"
LOCO_SOURCE_URL_ELECTRIC = "https://www.trainfanz.com/h-col-229.html"
LOCO_SOURCE_URL_DIESEL = "https://www.trainfanz.com/h-col-141.html"


def lookup_loco(loco_code: Optional[str] = None, loco_number: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    根据机车代号或机车号查询机车信息。

    参数:
        loco_code:  机车代号，例如 "240" 这种通常需要额外映射。
        loco_number: 机车号，例如 "HXD1D-00182" 或 "东风5-1234"。

    返回:
        找到返回字典，未找到返回 None。
    """
    if not loco_code and not loco_number:
        return None

    # 中文名 → 英文缩写别名映射 (LOCO_TABLE 输出中文名，LOCO_INFO key 为英文)
    CN_TO_EN = {
        '东风4': 'DF4', '东风4B': 'DF4B', '东风4C': 'DF4C', '东风4D': 'DF4D',
        '东风4客': 'DF4', '东风4E': 'DF4', '东风4DJ': 'DF4D',
        '东风5': 'DF5', '东风5宽': 'DF5', '东风5S': 'DF5',
        '东风7': 'DF7', '东风7B': 'DF7', '东风7C': 'DF7', '东风7D': 'DF7',
        '东风7E': 'DF7', '东风7G': 'DF7', '东风7S': 'DF7',
        '东风8': 'DF8B', '东风8B': 'DF8B',
        '东风9': 'DF11', '东风10': 'DF11', '东风10F': 'DF11',
        '东风11': 'DF11', '东风11G': 'DF11G',
        '东风12': 'DF8B',
        '东方红1': 'DF5', '东方红2': 'DF5', '东方红3': 'DF5',
        '东方红5': 'DF5', '东方红21': 'DF5',
        '韶山1': 'SS4', '韶山3': 'SS4', '韶山3B': 'SS4', '韶山3C': 'SS4',
        '韶山4': 'SS4', '韶山4G': 'SS4G',
        '韶山5': 'SS4', '韶山6': 'SS4', '韶山6B': 'SS4',
        '韶山7': 'SS7', '韶山7B': 'SS7', '韶山7C': 'SS7C',
        '韶山7D': 'SS7D', '韶山7E': 'SS7E',
        '韶山8': 'SS8', '韶山9': 'SS9',
    }

    # 优先按机车号前缀匹配
    if loco_number:
        upper = loco_number.upper().replace(' ', '')
        # 先尝试直接前缀匹配 (HXD1D-00182 → HXD1D)
        for key in sorted(LOCO_INFO.keys(), key=lambda k: -len(k)):
            if upper.startswith(key.upper()):
                return _enrich_loco_info(key)
        # 再尝试中文名别名匹配 (东风5-1234 → DF5)
        for cn, en in CN_TO_EN.items():
            if loco_number.startswith(cn):
                if en in LOCO_INFO:
                    return _enrich_loco_info(en)

    # 再按机车代号匹配（如果 LOCO_INFO 中有以数字代号作为 key 的条目）
    if loco_code:
        code_str = str(loco_code).strip()
        if code_str in LOCO_INFO:
            return _enrich_loco_info(code_str)

    return None


def _enrich_loco_info(key: str) -> Optional[Dict[str, Any]]:
    """构建机车信息字典，并附加图片URL和来源标注。"""
    info = dict(LOCO_INFO[key])
    info['matchedBy'] = 'lookup'
    info['matchedKey'] = key
    # 附加图片 URL
    info['imageUrl'] = LOCO_IMAGES.get(key, '')
    # 附加来源
    info['source'] = LOCO_SOURCE
    loco_type = info.get('type', '')
    if '内燃' in loco_type:
        info['sourceUrl'] = LOCO_SOURCE_URL_DIESEL
    else:
        info['sourceUrl'] = LOCO_SOURCE_URL_ELECTRIC
    return info


def format_loco_brief(info: Dict[str, Any]) -> str:
    """把机车信息格式化为单行简介。"""
    return (
        f"{info.get('name', '')}  "
        f"{info.get('type', '')}  "
        f"{info.get('power', '')}  "
        f"{info.get('speed', '')}"
    )
