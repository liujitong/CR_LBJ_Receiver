# -*- coding: utf-8 -*-
"""
loco_info.py — 中国铁路机车车辆信息映射表。

用于根据 LBJ 报文中解析出的"机车代号"或"机车号"前缀，查询机车的简要信息。
可继续扩展补充更多车型。

资料修订 2026-11-25（v2.5）：
  * 联网核对了中国中车官网产品技术参数、维基百科、百度百科等公开资料，
    重点修正了轴式、功率口径与制造厂商的错漏：
      - HXD1 / HXD2 是八轴双节固定重联，轴式为 2(Bo-Bo)，原表误写 Co'Co'；
      - HXN3 / HXN5 额定功率为 4400 kW 等级，原表误写 3300 kW；
      - FXD1 / FXD3 是单节动力车 5600 kW，原表按长编 2 动写成 2×5600 kW；
      - DF11G 功率口径细化为 2×3040 kW（标称）；
      - DF4B / DF4C / DF4D / DF11 区分「标称功率」与「柴油机装车/运用功率」；
      - 补齐 CRH / CR400 等动车组的牵引功率（原表为「—」）。
  * 旧 LOCO_IMAGES 使用 aka.doubaocdn.com 短链，2026-11 实测已全部返回 403，
    改为 Trainfanz.com 页面内 alt 明确标注、实测可访问的真实图片地址；
    页面其余图片为无 alt 的懒加载图且无法可靠对应车型，故不再保留，
    查不到图片时界面会显示「暂无该机型图片」。

字段口径约定：
  * power  优先用「机车标称/额定（轮周牵引）功率」；内燃机车口径差异大时
           并列标注，例如「1985 kW（标称）/ 2430 kW（柴油机装车）」。
  * speed  最高运用/构造速度；客货或多种版本用「/」并列。
  * axle   UIC 轴式，2(Bo-Bo) 表示八轴双节固定重联，2(Co-Co) 表示双机重联。
"""

from typing import Optional, Dict, Any, List, Tuple


# 资料修订版本与来源清单（详情窗口可选用；界面目前只展示 source/sourceUrl）
LOCO_DATA_REVISION = "2026-11-25"
LOCO_DATA_SOURCES: List[Tuple[str, str]] = [
    ("中国中车官网·产品技术参数（DF4B / DF11 / HXD2 等）", "https://www.crrcgc.cc/"),
    ("维基百科·和谐电力机车 / 中国电力机车列表 / 东风11型 / CR200J",
     "https://zh.wikipedia.org/"),
    ("百度百科·和谐系列货运电力机车 / 复兴号动车组", "https://baike.baidu.com/"),
    ("互动百科·和谐号电力动车组（CRH 牵引功率）", "https://www.baike.com/"),
    ("Trainfanz.com（我们的火车站）· 车型图片", "https://www.trainfanz.com/"),
]


# 机车代号 / 型号前缀 映射表
LOCO_INFO: Dict[str, Dict[str, Any]] = {
    # ---------------- 和谐电系列（交流传动电力机车） ----------------
    "HXD1": {
        "name": "和谐电1型 (HXD1)",
        "type": "电力机车",
        "maker": "中车株洲/西门子",
        "axle": "2(Bo-Bo)",
        "power": "9600 kW",
        "speed": "120 km/h",
        "brief": "八轴大功率交流传动货运机车，两节四轴车固定重联、单轴 1200 kW；基于西门子 EuroSprinter 平台，大秦线 2 万吨重载列车主力。",
    },
    "HXD1B": {
        "name": "和谐电1B型 (HXD1B)",
        "type": "电力机车",
        "maker": "中车株洲/西门子",
        "axle": "Co-Co",
        "power": "9600 kW",
        "speed": "120 km/h",
        "brief": "六轴大功率交流传动货运机车，单轴 1600 kW，以 HXD1 平台为基础研制，可牵引 6000 吨级货物列车。",
    },
    "HXD1C": {
        "name": "和谐电1C型 (HXD1C)",
        "type": "电力机车",
        "maker": "中车株洲",
        "axle": "Co-Co",
        "power": "7200 kW",
        "speed": "120 km/h",
        "brief": "六轴交流传动干线货运机车，国产化率超 90%，累计生产逾 1200 台，配属全国多个铁路局。",
    },
    "HXD1D": {
        "name": "和谐电1D型 (HXD1D)",
        "type": "电力机车",
        "maker": "中车株洲",
        "axle": "Co-Co",
        "power": "7200 kW",
        "speed": "160 km/h",
        "brief": "准高速客运电力机车，Co-Co 轴式、7200 kW，常用于直特、特快列车牵引。",
    },
    "HXD2": {
        "name": "和谐电2型 (HXD2)",
        "type": "电力机车",
        "maker": "中车大同/阿尔斯通",
        "axle": "2(Bo-Bo)",
        "power": "10000 kW",
        "speed": "120 km/h",
        "brief": "八轴大功率交流传动货运机车，基于阿尔斯通 PRIMA 平台、单轴 1250 kW；深度国产化的「新八轴」为 9600 kW，具备多机无线重联。",
    },
    "HXD2B": {
        "name": "和谐电2B型 (HXD2B)",
        "type": "电力机车",
        "maker": "中车大同/阿尔斯通",
        "axle": "Co-Co",
        "power": "9600 kW",
        "speed": "120 km/h",
        "brief": "六轴大功率货运机车，单轴 1600 kW，以 PRIMA 6000 为原型，主要服务西部、西北、华北干线。",
    },
    "HXD2C": {
        "name": "和谐电2C型 (HXD2C)",
        "type": "电力机车",
        "maker": "中车大同/东芝·庞巴迪",
        "axle": "Co-Co",
        "power": "7200 kW",
        "speed": "120 km/h",
        "brief": "六轴交流传动电力机车，客货通用。",
    },
    "HXD3": {
        "name": "和谐电3型 (HXD3)",
        "type": "电力机车",
        "maker": "中车大连/东芝",
        "axle": "Co-Co",
        "power": "7200 kW",
        "speed": "120 km/h",
        "brief": "六轴交流传动货运机车，以 JR 货物 EH500 型为原型，曾大批量配属干线货运。",
    },
    "HXD3B": {
        "name": "和谐电3B型 (HXD3B)",
        "type": "电力机车",
        "maker": "中车大连/庞巴迪",
        "axle": "Co-Co",
        "power": "9600 kW",
        "speed": "120 km/h",
        "brief": "六轴大功率货运机车，单轴 1600 kW，以庞巴迪 IORE Kiruna 机车为基础研制，重载货运主力。",
    },
    "HXD3C": {
        "name": "和谐电3C型 (HXD3C)",
        "type": "电力机车",
        "maker": "中车大连/北京二七",
        "axle": "Co-Co",
        "power": "7200 kW",
        "speed": "120 km/h",
        "brief": "六轴交流传动客货通用机车，带列车供电 2×400 kW，可牵引客运列车，运用非常广泛。",
    },
    "HXD3D": {
        "name": "和谐电3D型 (HXD3D)",
        "type": "电力机车",
        "maker": "中车大连",
        "axle": "Co-Co",
        "power": "7200 kW",
        "speed": "160 km/h",
        "brief": "准高速客运电力机车，俗称'红枣'，广泛用于直达、特快列车。",
    },

    # ---------------- 韶山系列（交—直流电传动电力机车） ----------------
    "SS4": {
        "name": "韶山4型 (SS4)",
        "type": "电力机车",
        "maker": "中车株洲",
        "axle": "2(Bo-Bo)",
        "power": "6400 kW (2×3200)",
        "speed": "100 km/h",
        "brief": "交—直流电传动八轴重载货运机车，两节四轴车固定重联，曾是中国铁路货运主力。",
    },
    "SS4G": {
        "name": "韶山4改型 (SS4G)",
        "type": "电力机车",
        "maker": "中车株洲/资阳/大同",
        "axle": "2(Bo-Bo)",
        "power": "6400 kW (2×3200)",
        "speed": "100 km/h",
        "brief": "SS4 改进型，产量逾 1400 台，货运干线常见车型。",
    },
    "SS4B": {
        "name": "韶山4B型 (SS4B)",
        "type": "电力机车",
        "maker": "中车株洲",
        "axle": "2(Bo-Bo)",
        "power": "6400 kW (2×3200)",
        "speed": "100 km/h",
        "brief": "SS4 系列改进型双节重联重载货运机车。",
    },
    "SS7": {
        "name": "韶山7型 (SS7)",
        "type": "电力机车",
        "maker": "中车大同",
        "axle": "Bo-Bo-Bo",
        "power": "4800 kW",
        "speed": "100 km/h",
        "brief": "交—直流电传动六轴机车，三台二轴转向架，适应山区铁路小半径曲线。",
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
        "maker": "中车大同/大连",
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

    # ---------------- 东风系列（内燃机车） ----------------
    "DF4": {
        "name": "东风4型 (DF4)",
        "type": "内燃机车",
        "maker": "中车大连",
        "axle": "Co-Co",
        "power": "2430 kW（柴油机装车）",
        "speed": "100 km/h（货运）/ 120 km/h（客运）",
        "brief": "交—直流电传动内燃机车，装 16V240ZJ 系列柴油机，中国铁路历史上产量最大、运用最广的内燃机车系列。",
    },
    "DF4B": {
        "name": "东风4B型 (DF4B)",
        "type": "内燃机车",
        "maker": "中车大连/资阳/大同",
        "axle": "Co-Co",
        "power": "1985 kW（标称）/ 2430 kW（柴油机装车）",
        "speed": "100 km/h（货运）/ 120 km/h（客运）",
        "brief": "客货运通用内燃机车，俗称'西瓜'，产量逾 4500 台；按国家铁路局办法 2035 年底前逐步淘汰。",
    },
    "DF4C": {
        "name": "东风4C型 (DF4C)",
        "type": "内燃机车",
        "maker": "中车大连",
        "axle": "Co-Co",
        "power": "2165 kW（标称）/ 2430 kW（柴油机装车）",
        "speed": "100 km/h",
        "brief": "货运内燃机车，DF4 系列改进型。",
    },
    "DF4D": {
        "name": "东风4D型 (DF4D)",
        "type": "内燃机车",
        "maker": "中车大连",
        "axle": "Co-Co",
        "power": "2425 kW（标称）/ 2940 kW（柴油机装车）",
        "speed": "145 km/h（客运）/ 100 km/h（货运）/ 170 km/h（准高速）",
        "brief": "客货运通用内燃机车，分客运型、货运型与准高速型，曾广泛用于快速列车牵引。",
    },
    "东风4D": {
        "name": "东风4D型 (DF4D)",
        "type": "内燃机车",
        "maker": "中车大连",
        "axle": "Co-Co",
        "power": "2425 kW（标称）/ 2940 kW（柴油机装车）",
        "speed": "145 km/h（客运）/ 100 km/h（货运）/ 170 km/h（准高速）",
        "brief": "客货运通用内燃机车，分客运型、货运型与准高速型，曾广泛用于快速列车牵引。",
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
    "东风5": {
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
        "power": "3680 kW（5000 马力）",
        "speed": "100 km/h",
        "brief": "大功率货运内燃机车，主要用于干线重载货运。",
    },
    "DF11": {
        "name": "东风11型 (DF11)",
        "type": "内燃机车",
        "maker": "中车戚墅堰",
        "axle": "Co-Co",
        "power": "3040 kW（标称）/ 3610 kW（运用）/ 3860 kW（标定）",
        "speed": "170 km/h",
        "brief": "准高速客运内燃机车，装 16V280ZJA 柴油机，中国铁路前四次大提速主力，俗称'狮子'。",
    },
    "DF11G": {
        "name": "东风11G型 (DF11G)",
        "type": "内燃机车",
        "maker": "中车戚墅堰",
        "axle": "2(Co-Co)",
        "power": "2×3040 kW（标称）",
        "speed": "170 km/h",
        "brief": "双机重联准高速客运内燃机车，柴油机运用功率 2×3610 kW，带列车供电，曾牵引直达特快列车。",
    },
    "HXN3": {
        "name": "和谐内3型 (HXN3)",
        "type": "内燃机车",
        "maker": "中车大连/EMD",
        "axle": "Co-Co",
        "power": "4400 kW（6000 马力，额定）",
        "speed": "120 km/h",
        "brief": "大功率交流传动内燃机车，基于 EMD SD90MAC 平台，主要用于重载货运。",
    },
    "HXN5": {
        "name": "和谐内5型 (HXN5)",
        "type": "内燃机车",
        "maker": "中车戚墅堰/GE",
        "axle": "Co-Co",
        "power": "4400 kW（额定）/ 4660 kW（装车）",
        "speed": "120 km/h",
        "brief": "大功率交流传动内燃机车，装 GEVO16 柴油机，基于 GE AC6000CW 平台，货运干线运用广泛。",
    },

    # ---------------- 复兴号动力集中动车组动力车 ----------------
    "FXD1": {
        "name": "复兴电1型 (FXD1)",
        "type": "电力机车（动力车）",
        "maker": "中车株洲",
        "axle": "Bo-Bo",
        "power": "5600 kW（单节动力车，短时 6400 kW）",
        "speed": "160 km/h（运营）/ 210 km/h（动力车构造）",
        "brief": "复兴号 CR200J 动力集中动车组动力车；短编 1 动合计 5600 kW，长编双动合计 11200 kW，采用永磁同步牵引电机。",
    },
    "FXD3": {
        "name": "复兴电3型 (FXD3)",
        "type": "电力机车（动力车）",
        "maker": "中车大连",
        "axle": "Bo-Bo",
        "power": "5600 kW（单节动力车，短时 6400 kW）",
        "speed": "160 km/h（运营）/ 210 km/h（动力车构造）",
        "brief": "复兴号 CR200J 动力车（东芝/中车永济牵引系统）；短编 5600 kW，长编双动 11200 kW。",
    },
    "CR200J": {
        "name": "复兴号 CR200J",
        "type": "动力集中动车组",
        "maker": "中车株机/大连等六家",
        "axle": "1L8T（短编）/ 2L16T（长编）",
        "power": "5600 kW（短编）/ 11200 kW（长编）",
        "speed": "160 km/h",
        "brief": "时速 160 km 动力集中动车组，俗称'绿巨人'，动力车为 FXD1/FXD3，2019 年 1 月投入运营。",
    },

    # ---------------- 和谐号 / 复兴号动力分散动车组 ----------------
    "CRH1": {
        "name": "和谐号 CRH1",
        "type": "高速动车组",
        "maker": "BST(四方-庞巴迪)",
        "axle": "动力分散 5M3T",
        "power": "5500 kW（8 辆编组）",
        "speed": "200/250 km/h",
        "brief": "和谐号电力动车组，广泛用于城际铁路及干线高铁。",
    },
    "CRH2": {
        "name": "和谐号 CRH2",
        "type": "高速动车组",
        "maker": "中车青岛四方",
        "axle": "动力分散 4M4T",
        "power": "4800 kW（CRH2A，8 辆编组）",
        "speed": "200/250/300 km/h",
        "brief": "和谐号电力动车组，基于日本新干线 E2 技术引进消化吸收，衍生 CRH2C/CRH380A 等。",
    },
    "CRH3": {
        "name": "和谐号 CRH3",
        "type": "高速动车组",
        "maker": "中车唐山/长客",
        "axle": "动力分散 4M4T",
        "power": "8800 kW（CRH3C，8 辆编组）",
        "speed": "300/350 km/h",
        "brief": "和谐号电力动车组，基于西门子 Velaro 平台。",
    },
    "CRH5": {
        "name": "和谐号 CRH5",
        "type": "高速动车组",
        "maker": "中车长春轨道客车",
        "axle": "动力分散 5M3T",
        "power": "6770 kW（8 辆编组）",
        "speed": "200/250 km/h",
        "brief": "和谐号电力动车组，耐寒性好，广泛用于东北、西北及兰新高铁。",
    },
    "CRH380": {
        "name": "和谐号 CRH380 系列",
        "type": "高速动车组",
        "maker": "中车四方/长客/唐山",
        "axle": "动力分散（视子型）",
        "power": "约 9600 kW（8 辆编组）",
        "speed": "350/380 km/h",
        "brief": "和谐号高速动车组，中国自主研发设计，最高运营时速 380 km/h。",
    },
    "CR300": {
        "name": "复兴号 CR300 系列",
        "type": "高速动车组",
        "maker": "中车四方/长客",
        "axle": "动力分散 4M4T",
        "power": "5460 kW（8 辆编组）",
        "speed": "250 km/h",
        "brief": "复兴号时速 250 km 级别动车组，代表车型 CR300AF/BF，2020 年 12 月投入运用。",
    },
    "CR400": {
        "name": "复兴号 CR400 系列",
        "type": "高速动车组",
        "maker": "中车四方/长客",
        "axle": "动力分散 4M4T（8 辆）",
        "power": "9750 kW（AF）/ 10140 kW（BF），8 辆编组",
        "speed": "350 km/h",
        "brief": "复兴号中国标准动车组，运营时速 350 km/h，代表车型 CR400AF/BF；长编（16/17 辆）约 19500~20280 kW。",
    },
    "CR450": {
        "name": "复兴号 CR450 系列",
        "type": "高速动车组",
        "maker": "中车四方/长客",
        "axle": "动力分散 4M4T",
        "power": "—（官方尚未公布）",
        "speed": "400 km/h（设计运营）",
        "brief": "复兴号下一代高速动车组，CR450AF/BF 于 2024 年 12 月发布，试验速度达 450 km/h 级。",
    },
}


# 机车图片 URL 映射表
# 2026-11-25 重新抓取：原 aka.doubaocdn.com 短链已全部 403 失效。
# 现使用 Trainfanz.com 页面内 alt 明确标注车型、且实测可访问的真实图片地址；
# 未被 alt 覆盖的车型无法可靠对应，故不保留（界面显示「暂无该机型图片」）。
_IMG_BASE = "https://26561303.s21i.faiusr.com/"
LOCO_IMAGES: Dict[str, str] = {
    # --- 和谐电系列 ---
    "HXD1":   _IMG_BASE + "2/1/ABUIABACGAAg5eD9pgYolK-BGDDUAjjUAg.jpg",
    "HXD1B":  _IMG_BASE + "2/1/ABUIABACGAAg5eD9pgYopc-v-QUw1AI41AI.jpg",
    "HXD1C":  _IMG_BASE + "2/1/ABUIABACGAAg5eD9pgYo1IfxlgYw1AI41AI.jpg",
    "HXD1D":  _IMG_BASE + "2/1/ABUIABACGAAg5eD9pgYo4dm19AUw1AI41AI.jpg",
    "HXD2":   _IMG_BASE + "2/1/ABUIABACGAAg5eD9pgYolti0sAcw1AI41AI.jpg",
    "HXD3C":  _IMG_BASE + "2/1/ABUIABACGAAgx6bCqQYo2tG1gwEw1AI41AI.jpg",
    # --- 东风 / 和谐内系列 ---
    "DF7":    _IMG_BASE + "2/1/ABUIABACGAAg18XKqAYotNKdxwcw1AI41AI.jpg",
    "DF8B":   _IMG_BASE + "2/1/ABUIABACGAAg-ZLQqAYouqqoqAYw1AI41AI.jpg",
    "DF11":   _IMG_BASE + "2/1/ABUIABACGAAg2MXKqAYokIyBUzDUAjjUAg.jpg",
    "DF11G":  _IMG_BASE + "2/1/ABUIABACGAAg2MXKqAYo8q7sGzDUAjjUAg.jpg",
}

# 机车来源标注（图片来源页；参数来源见 LOCO_DATA_SOURCES）
LOCO_SOURCE = "Trainfanz.com · 参数经公开资料核对"
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
        '和谐电1': 'HXD1', '和谐电1B': 'HXD1B', '和谐电1C': 'HXD1C',
        '和谐电1D': 'HXD1D', '和谐电2': 'HXD2', '和谐电2B': 'HXD2B',
        '和谐电2C': 'HXD2C', '和谐电3': 'HXD3', '和谐电3B': 'HXD3B',
        '和谐电3C': 'HXD3C', '和谐电3D': 'HXD3D',
        '和谐内3': 'HXN3', '和谐内5': 'HXN5',
    }

    # 优先按机车号前缀匹配（长 key 优先，避免 HXD1 抢走 HXD1D）
    if loco_number:
        upper = loco_number.upper().replace(' ', '')
        for key in sorted(LOCO_INFO.keys(), key=lambda k: -len(k)):
            if upper.startswith(key.upper()):
                return _enrich_loco_info(key)
        # 再尝试中文名别名匹配（长名优先，避免「东风4」抢走「东风4B」）
        for cn, en in sorted(CN_TO_EN.items(), key=lambda kv: -len(kv[0])):
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
    # 附加图片 URL（无可靠图片时为空串，界面显示「暂无该机型图片」）
    info['imageUrl'] = LOCO_IMAGES.get(key, '')
    # 附加来源
    info['source'] = LOCO_SOURCE
    loco_type = info.get('type', '')
    if '内燃' in loco_type:
        info['sourceUrl'] = LOCO_SOURCE_URL_DIESEL
    else:
        info['sourceUrl'] = LOCO_SOURCE_URL_ELECTRIC
    # 资料核对信息（供详情窗口/导出使用，界面当前不遍历字典故不影响显示）
    info['dataSources'] = LOCO_DATA_SOURCES
    info['dataRevision'] = LOCO_DATA_REVISION
    return info


def format_loco_brief(info: Dict[str, Any]) -> str:
    """把机车信息格式化为单行简介。"""
    return (
        f"{info.get('name', '')}  "
        f"{info.get('type', '')}  "
        f"{info.get('power', '')}  "
        f"{info.get('speed', '')}"
    )
