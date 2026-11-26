#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""使用说明与关于对话框。

本模块由 GUI 组装层 cr_lbj/gui.py 导入；共享运行时（Qt 类别名、主题色、
缩放、控件工厂）统一来自 cr_lbj/runtime.py。
"""
from __future__ import annotations

from cr_lbj.runtime import *  # noqa: F401,F403

class ManualDialog(QDialog):
    """使用手册对话框：USB 直连 / rtl_tcp / OWRX 配置说明。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('使用手册')
        self.resize(spx(700), spx(640))
        layout = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        contentLayout = QVBoxLayout(content)

        # ---- 传统 RTL-TCP 模式 ----
        title1 = QLabel('一、本机 USB 直连（推荐）')
        title1.setStyleSheet(f'color: {CLR("accent")}; font-size: 15px; font-weight: bold;')
        contentLayout.addWidget(title1)

        text1 = QLabel(
            '<p>棒子插在本机时的默认方式：程序用 <b>librtlsdr</b>（内附 '
            '<code>rtlsdr.dll</code>）直接读取 RTL2832U，不经过 rtl_tcp、不走 TCP，'
            '少一个后台进程和一层本地转发。</p>'
            '<p><b>配置步骤：</b></p>'
            '<p>1. 安装驱动：用 <b>Zadig</b> 把 RTL2832U 的驱动替换为 '
            '<b>WinUSB</b>（勾选 "List All Devices"，选 Bulk-In Interface，'
            '点 Replace Driver）。装过一次即可。</p>'
            '<p>2. 数据源类型选「本机 USB (直连)」（默认就是它），点「检测设备」'
            '可确认设备与 tuner 型号，并一键应用推荐参数。</p>'
            '<p>3. 射频参数（推荐值，检测设备后可自动填入）：</p>'
            '<ul style="margin-left: 20px;">'
            '<li>采样率：960000 Hz（DSP 链路的甜点值）</li>'
            '<li>频率：821.2375 MHz</li>'
            '<li>增益：手动，R820T 19.7 dB / R828D 15.7 dB，按设备增益表就近取</li>'
            '<li>AGC：关闭（突发窄带信号不能被 AGC 拉平）</li>'
            '<li>DC 偏移：50000 Hz（避开零频 DC 干扰）</li>'
            '<li>PPM 校正：按晶振偏差调整（默认 1）</li>'
            '<li>信道带宽：35 kHz；AFC：建议开启</li>'
            '</ul>'
            '<p><b>说明：</b>直连打不开（dll 缺失、被占用等）会自动退回 rtl_tcp 中转，'
            '日志里会写明原因，不影响使用。</p>'
        )
        text1.setWordWrap(True)
        text1.setStyleSheet('font-size: 13px; line-height: 1.5;')
        contentLayout.addWidget(text1)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet(f'background-color: {CLR("border")};')
        contentLayout.addWidget(sep1)

        # ---- OWRX 模式 ----
        title2 = QLabel('二、OWRX 兼容模式')
        title2.setStyleSheet(f'color: {CLR("accent2")}; font-size: 15px; font-weight: bold;')
        contentLayout.addWidget(title2)

        text2 = QLabel(
            '<p>使用 OpenWebRX 服务器提供的 IQ 流进行解码，无需本地 SDR 硬件。</p>'
            '<p><b>配置步骤：</b></p>'
            '<p>1. 确保已部署 OpenWebRX 服务器，并启用了 rtl_tcp 兼容接口。</p>'
            '<p>2. 在本程序配置中设置：</p>'
            '<ul style="margin-left: 20px;">'
            '<li>模式：OWRX 兼容模式</li>'
            '<li>主机：OpenWebRX 服务器地址（如 127.0.0.1 或远程 IP）</li>'
            '<li>端口：OpenWebRX 的 rtl_tcp 端口（通常为 1234）</li>'
            '<li>DC 偏移：0 Hz（OWRX 提供零中频 IQ 流，无需 DC 避让）</li>'
            '<li>采样率：与 OpenWebRX 设置一致（通常 960000 Hz）</li>'
            '<li>频率：821.2375 MHz</li>'
            '<li>增益：由 OpenWebRX 服务端控制，本地设置可保持默认</li>'
            '<li>AFC：建议开启</li>'
            '</ul>'
            '<p><b>说明：</b>OWRX 模式下，OpenWebRX 服务端已经完成调谐和 IQ 采样，'
            '本程序直接接收零中频 IQ 流，因此 DC 偏移必须设为 0。'
            '增益等射频参数由服务端控制，本地设置不生效。</p>'
        )
        text2.setWordWrap(True)
        text2.setStyleSheet('font-size: 13px; line-height: 1.5;')
        contentLayout.addWidget(text2)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet(f'background-color: {CLR("border")};')
        contentLayout.addWidget(sep2)

        # ---- 通用说明 ----
        title3 = QLabel('三、通用说明')
        title3.setStyleSheet(f'color: {CLR("warn")}; font-size: 15px; font-weight: bold;')
        contentLayout.addWidget(title3)

        text3 = QLabel(
            '<p><b>RSSI 门控：</b>当信号强度超过阈值（默认 -55 dB）时开始解码，'
            '低于阈值后保持 700ms 再停止，避免信号波动导致频繁启停。</p>'
            '<p><b>AFC（自动频率控制）：</b>跟踪并修正接收信号的频偏，'
            '确保信号锁定在信道中心。建议始终开启。</p>'
            '<p><b>干扰告警：</b>当 BCH 译码检测到不可纠正的错误时，'
            '说明信号受到干扰，程序会在日志和状态栏显示告警。</p>'
            '<p><b>当前列表：</b>显示最近 10 分钟内的解码记录，'
            '无车次信息或受干扰的记录以红色标注，不存入历史数据库。</p>'
        )
        text3.setWordWrap(True)
        text3.setStyleSheet('font-size: 13px; line-height: 1.5;')
        contentLayout.addWidget(text3)

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.HLine)
        sep3.setStyleSheet(f'background-color: {CLR("border")};')
        contentLayout.addWidget(sep3)

        # ---- 多数据源 ----
        title4 = QLabel('四、多数据源与免命令行')
        title4.setStyleSheet(f'color: {CLR("accent")}; font-size: 15px; font-weight: bold;')
        contentLayout.addWidget(title4)
        text4 = QLabel(
            '<p>支持保存多套数据源，在“配置 → 数据源与射频”中切换（列表里带短标签：'
            '[USB] 直连、[USB*] 中转、[TCP] 网络、[OWRX]）：</p>'
            '<ul style="margin-left: 20px;">'
            '<li><b>本机 USB（直连，推荐）</b>：插上 RTL-SDR 即可。程序直接调用内附的'
            ' <code>rtlsdr.dll</code> 收数，不经过 rtl_tcp、不走 TCP；'
            '要求已用 Zadig 安装 WinUSB 驱动。直连打不开时会自动退回 rtl_tcp 中转。</li>'
            '<li><b>本机 USB（rtl_tcp 中转）</b>：兼容模式，程序自动拉起 '
            '<code>rtl_tcp.exe</code> 并连本地端口，退出时自动关闭。</li>'
            '<li><b>RTL-TCP</b>：连接局域网或本机已有的 rtl_tcp 服务（默认 1234 端口）。</li>'
            '<li><b>OWRX</b>：连接 OpenWebRX 的 rtl_tcp 兼容端口（DC 偏移设为 0）。</li>'
            '</ul>'
            '<p>发布包已内附 <code>rtl_tcp.exe</code>、<code>rtlsdr.dll</code> 等工具，'
            '装好驱动、插上棒子就能用，无需另外安装工具包。'
            '源码运行时把它们放在项目的 <code>tools/rtl/</code> 目录即可（也兼容'
            '<code>RTL_TCP_Server</code> 子目录与 PATH）。'
            '“检测设备”会读出 tuner 型号（R820T / R828D 等）并按型号推荐'
            '采样率与增益，点“应用推荐参数”一键填入。</p>'
        )
        text4.setWordWrap(True)
        text4.setStyleSheet('font-size: 13px; line-height: 1.5;')
        contentLayout.addWidget(text4)

        sep4 = QFrame()
        sep4.setFrameShape(QFrame.HLine)
        sep4.setStyleSheet(f'background-color: {CLR("border")};')
        contentLayout.addWidget(sep4)

        # ---- 地图（Leaflet + OpenRailwayMap） ----
        title5 = QLabel('五、地图：OpenRailwayMap 铁路图源与底图切换')
        title5.setStyleSheet(f'color: {CLR("accent2")}; font-size: 15px; font-weight: bold;')
        contentLayout.addWidget(title5)
        text5 = QLabel(
            '<p><b>先决条件：</b>只有扩展长报文（地址 1234002 / 1234001）携带经纬度；'
            '基础帧 1234000 只有车次/速度/公里标。因此地图上出现标记的前提是：'
            '<b>收到同一列车的基础帧 + 长报文</b>。</p>'
            '<p><b>地图引擎：</b>地图页由 <code>shared/web/railmap.html</code>'
            '（Leaflet，已本地化）提供，<b>桌面版与安卓版共用同一份页面</b>，'
            '铁路图源是 <b>OpenRailwayMap</b>（免 Key、WGS-84 栅格瓦片），'
            '还可选「本地铁路线」加载自建的 <code>rail_local.geojson</code>。</p>'
            '<p><b>怎么换底图：</b>地图卡片左上角的「底图」下拉，或'
            '「视图 → 底图」子菜单。可选 高德 街道/卫星、百度 街道/卫星（均免 Key）、天地图（矢量、影像）'
            '/ OSM 标准。'
            '也可以直接点地图右上角的「图层」面板改，三种入口互相同步。</p>'
            '<p><b>铁路图层：</b>地图卡片上的「铁路」勾选框（或「视图 → 铁路图层」）'
            '控制是否叠加 OpenRailwayMap；在「配置 → 地图与车次」里还能选'
            '<b>图层样式</b>（标准/限速/信号/电气化/轨距/本地铁路线）和'
            '<b>不透明度</b>（20%~100%）。</p>'
            '<p><b>坐标系：</b>OSM/天地图为 WGS-84 系（天地图 CGCS2000 工程上等同 '
            'WGS-84，零偏移）；高德为 GCJ-02、百度为 BD-09（百度另有自有投影），'
            '页面会自动纠偏标记，此时铁路图层（WGS-84）会自动关闭以避免错位。</p>'
            '<p><b>天地图 tk：</b>只有天地图底图需要。到 '
            '<a href="https://console.tianditu.gov.cn/">console.tianditu.gov.cn</a> '
            '免费申请，应用类型必须选「<b>浏览器端</b>」，把 tk 填到'
            '「配置 → 地图与车次 → 天地图 tk」；申请时登记的<b>白名单域名</b>填到'
            '「天地图 Referer 域名」——本地页面没有合法 Referer，程序会按该域名'
            '给天地图请求附加 Referer（留空则不附加）。详见 docs/地图与图源.md。</p>'
            '<p><b>底图打不开时：</b>地图工具栏的状态文字会变成红色的'
            '「底图不可达，换一张」——通常是当前网络连不上该瓦片服务（境外瓦片居多），'
            '换高德/百度（免 Key）或天地图（配 tk）即可；页面也会给一键切换按钮。</p>'
            '<p><b>默认中心：</b>「配置 → 地图与车次 → 默认中心」选预设城市会自动填好'
            '经纬度（也可以手改）；它只用于开机时把视野带到该地区，'
            '<b>不会在地图上加标记</b>。地图卡片上的「中心」按钮可随时回去。</p>'
            '<p><b>视野与跟随：</b>「跟随」只在当前列车真的移动约 30 米以上时才重新居中；'
            '<b>你一拖动地图或用滚轮缩放，跟随会自动暂停</b>（按钮同步取消勾选），'
            '点一下「跟随」即可恢复。</p>'
            '<p><b>轨迹：</b>同一列车收到多个详细报文时，页面按“移动超过约 6 米或间隔超过 '
            '3 秒”记录一个点，最多保留 240 点并画成折线；点标记可看轨迹点数与里程。</p>'
            '<p><b>完整文档：</b>程序目录 <code>docs/</code> 下有用户手册、技术参考与'
            '「地图与图源」文档；地图页面源码在 <code>shared/web/railmap.html</code>。</p>'
        )
        text5.setWordWrap(True)
        text5.setOpenExternalLinks(True)
        text5.setStyleSheet('font-size: 13px; line-height: 1.5;')
        contentLayout.addWidget(text5)

        sep5 = QFrame()
        sep5.setFrameShape(QFrame.HLine)
        sep5.setStyleSheet(f'background-color: {CLR("border")};')
        contentLayout.addWidget(sep5)

        # ---- 2026 车次 ----
        title6 = QLabel('六、2026 版车次规则')
        title6.setStyleSheet(f'color: {CLR("warn")}; font-size: 15px; font-weight: bold;')
        contentLayout.addWidget(title6)
        text6 = QLabel(
            '<p>2026 版《列车车次编排规定》分两批实施：2026-11-24 起货物/路用列车换新号，'
            '11-25 起普速旅客列车换新号，12 月下旬动车组换新号。</p>'
            '<p><b>新字头：</b>X(350+ 复兴号)、G(350)、T(300)、K(200~250)、D(动集)、'
            'C(城际)、S(市郊)；普速改为 Z(160)、N(140)、V(120)，'
            'V6001~V6998 为普通旅客快车、V7001~V7998 为普通旅客慢车；'
            '货运班列 X → B，新增 DH(动货)。</p>'
            '<p><b>兼容旧车次：</b>“车次规则”默认选“自动兼容”，程序用当前速度区分：'
            'T/K/X 速度 ≥200 km/h 按新动车组解释，低于 200 按旧特快/快速/行包解释；'
            '也可强制选择 2026 新版或 2014 旧版。</p>'
        )
        text6.setWordWrap(True)
        text6.setStyleSheet('font-size: 13px; line-height: 1.5;')
        contentLayout.addWidget(text6)

        sep6 = QFrame()
        sep6.setFrameShape(QFrame.HLine)
        sep6.setStyleSheet(f'background-color: {CLR("border")};')
        contentLayout.addWidget(sep6)

        # ---- v2.3 界面与操作 ----
        title7 = QLabel('七、界面与操作')
        title7.setStyleSheet(f'color: {CLR("accent2")}; font-size: 15px; font-weight: bold;')
        contentLayout.addWidget(title7)
        text7 = QLabel(
            '<p><b>布局（全景式，不用切页签）：</b>一屏分三段——'
            '<b>上段</b>左侧是实时地图（约六成宽），右侧上「当前解码」表、下「列车信息」卡片；'
            '<b>中段</b>三块并排：<b>接收频谱 | 车次信息 | 机车信息</b>；'
            '<b>底栏</b>左右各一半：<b>输出 1 · 日志</b>（滚动显示最近日志，点击打开完整日志窗口）'
            '与 <b>输出 2 · 接收状态</b>。所有内容同屏可见，互不遮挡。</p>'
            '<p><b>频谱切换：</b>「图形 / 终端」下拉框现在就在<b>接收频谱卡片的标题栏右侧</b>，'
            '跟频谱放一起，切完立即生效并记住选择。</p>'
            '<p><b>输出 2 · 接收状态：</b>四个等宽方块——信号 / AFC / 干扰 / 链路。'
            '正常只有灰色描边，哪一项不对整块变黄（注意）或变红（异常），边框和数值一起变色；'
            '<b>点任意方块打开运行状态仪表板</b>（也可以按 Ctrl+D）。'
            '告警原文只出现在输出 1 的日志里，这里不复述。</p>'
            '<p><b>运行状态仪表板：</b>「帮助 → 运行状态仪表板」(Ctrl+D) 已改成'
            '<b>分组卡片 + 指标方块</b>：链路 / 射频与频谱 / 门控与 AFC / 解码与去重 / 界面五组，'
            '良好标绿、注意标黄、异常标红，扫一眼就知道该看哪一项；'
            '每秒自动刷新，可暂停、可「复制全部」成文本。</p>'
            '<p><b>自适应：</b>窗口或屏幕变化时，程序自己调上下段比例、地图最小宽度、'
            '字段列数与标题显隐，不需要手拖分隔条；启动时还会按屏幕尺寸选一个合适的界面缩放基准。'
            '手动「视图 → 界面缩放」仍然保留，作为偏好覆盖。</p>'
            '<p><b>配置分页：</b>配置窗口按「数据源与射频 / 到达估算 / 地图与车次 / '
            '解码与界面 / 外观主题 / 数据更新」六页分开，不再是一条长滚动条；'
            '数据源与射频同一页，按「源类型 / 主机 / 端口 → 采样率 / 频率 / 增益 / '
            'PPM / 带宽 / DC 偏移」顺序排列。</p>'
            '<p><b>历史记录：</b>主界面只保留「当前解码」；历史记录在'
            '「工具 → 历史记录…」(Ctrl+H)，可查看列表、双击看详情、删除选中 / 删除全部'
            '（均二次确认）与导出 CSV。</p>'
            '<p><b>外观主题：</b>内置中国铁路标准色——主色 CR 红 #DA291C（Pantone 485C）、'
            '辅色 CR 蓝 #003DA5（Pantone 286C）。'
            '工具栏右上角的 <b>「日间 / 夜间」按钮</b>（或 Ctrl+T、或「视图 → 切换日间 / 夜间」）'
            '<b>点一下立即换色，不需要重启</b>：全局样式、卡片、表格、频谱、地图、仪表板一起变。'
            '也可以「视图 → 外观主题」选 <b>夜间 / 日间 / 跟随系统</b>（跟随系统读取 Windows 的浅色 / 深色设置）。</p>'
            '<p><b>地图：</b>标记按方向着色；车多时会自动避让——放不下的小标记隐藏速度/公里标副行并降低透明度，'
            '放大后恢复；点标记弹出的是不透明信息卡片（含时间、方向、轨迹点数与里程），不再压住底图。'
            '手动拖动/滚轮缩放会自动暂停「跟随」，不会再被下一条报文拉回去；'
            '「中心」按钮回到配置里的默认中心（地名，不加标记）。</p>'
            '<p><b>轨迹：</b>同一列车收到多个详细报文时，按“移动超过约 6 米或间隔超过 3 秒”记录一个点，'
            '最多保留 240 点，画成折线；信息卡片里会显示“N 个点 · x.x km”。</p>'
            '<p><b>实时日志：</b>点底栏「输出 1」里的任一一行，或「帮助 → 实时日志」(Ctrl+L)，'
            '可查看自启动以来的全部输出，支持暂停、清空、另存为。</p>'
            '<p><b>全屏：</b>F11 或「视图 → 全屏」；Esc 退出。全屏时自动隐藏菜单栏。</p>'
            '<p><b>触屏：</b>按钮、表格行高、滚动条已加大，表格支持手指拖动惯性滚动，'
            '适合 Surface 等触屏设备。</p>'
        )
        text7.setWordWrap(True)
        text7.setStyleSheet('font-size: 13px; line-height: 1.5;')
        contentLayout.addWidget(text7)

        sep7 = QFrame()
        sep7.setFrameShape(QFrame.HLine)
        sep7.setStyleSheet(f'background-color: {CLR("border")};')
        contentLayout.addWidget(sep7)

        title8 = QLabel('八、重复报文合并与记录质量')
        title8.setStyleSheet(f'color: {CLR("ok")}; font-size: 15px; font-weight: bold;')
        contentLayout.addWidget(title8)
        text8 = QLabel(
            '<p>同一次 LBJ 发射常被连续解出 2~4 次，表现为“同一车次同一秒出现多条记录”。</p>'
            '<p><b>处理方式：</b>同一车次在“重复报文合并”窗口（默认 2.5 秒）内只保留质量最高的一条：'
            '详细报文优先于基础帧，其次看是否有经纬度、BCH 是否纠错、机车/线路/速度是否完整、'
            '信号强度高低。窗口内后来解出更优的记录会<b>就地替换</b>已显示的那条，'
            '历史库里也是更新而非新增。</p>'
            '<p>窗口可在「配置 → 解码与界面」调整，设为 0 可关闭去重；'
            '“运行状态仪表板”（Ctrl+D 或点底栏右侧状态条）的「解码与去重」组里'
            '可看到「合并丢弃 / 择优升级 / 占用槽位」。</p>'
        )
        text8.setWordWrap(True)
        text8.setStyleSheet('font-size: 13px; line-height: 1.5;')
        contentLayout.addWidget(text8)

        sep8 = QFrame()
        sep8.setFrameShape(QFrame.HLine)
        sep8.setStyleSheet(f'background-color: {CLR("border")};')
        contentLayout.addWidget(sep8)

        title9 = QLabel('九、车次信息卡与时刻表查询（v3.2.1）')
        title9.setStyleSheet(f'color: {CLR("accent")}; font-size: 15px; font-weight: bold;')
        contentLayout.addWidget(title9)
        text9 = QLabel(
            '<p>中段「车次信息」卡片收到详细长报文后<b>自动异步查询</b>，默认先问 '
            '<b>RailGo</b>（字段全），失败自动退回 <b>12306</b>（官方时刻表）。</p>'
            '<p><b>显示内容：</b>始发 → 终到、车次等级、<b>担当局 + 担当段全称</b>'
            '（如「南昌局南昌客运段」）、配属段 / 车辆段、车型；'
            '数据来源与查询结果状态显示在最下面一行。</p>'
            '<p><b>查看时刻表：</b>拿到时刻表数据后按钮可用（也可双击卡片），'
            'RailGo 与 12306 两个来源都支持；货运 / 路用等未收录车次没有时刻表。</p>'
            '<p><b>查不到时：</b>卡片显示「未查询到 … 的车次信息」并给出原因，'
            '不影响解码、地图与历史记录。</p>'
        )
        text9.setWordWrap(True)
        text9.setStyleSheet('font-size: 13px; line-height: 1.5;')
        contentLayout.addWidget(text9)

        sep9b = QFrame()
        sep9b.setFrameShape(QFrame.HLine)
        sep9b.setStyleSheet(f'background-color: {CLR("border")};')
        contentLayout.addWidget(sep9b)

        title10 = QLabel('十、车次查询、机车配属查询与数据自动更新（v3.0 新增）')
        title10.setStyleSheet(f'color: {CLR("ok")}; font-size: 15px; font-weight: bold;')
        contentLayout.addWidget(title10)
        text10 = QLabel(
            '<p><b>车次查询：</b>「工具 → 车次查询…」(Ctrl+F) 或按 Ctrl+F。'
            '输入车次号（G7 / K1234 / Z21），选数据源后查询，结果里有：'
            '列车等级、<b>担当局 / 客运段 / 配属段 / 车型</b>、开行日、'
            '交路（贯通车次）与<b>全程时刻表</b>（站名/到点/发点/停站/里程）。</p>'
            '<p><b>两个数据源：</b><b>RailGo</b> 是社区接口，字段最全，作为首选；'
            '失败会自动退回 <b>12306</b>（官方，只有时刻表，没有担当与配属）。'
            '查询失败时结果区会给出原因，并给「改用 12306 重试 / 改用 RailGo 重试」按钮。'
            '默认数据源在「配置 → 地图与车次 → 车次数据源」里设。</p>'
            '<p><b>机车配属查询：</b>「工具 → 机车配属查询…」(Ctrl+G)。'
            '输入 <code>HXD1D 0123</code>、<code>HXD1D-0123</code>、'
            '<code>韶山4-0123</code> 都可以；也可以先在下拉里选型号、再填机车号。'
            '结果分两张卡：<b>配属</b>（配属局段、号段区间、制造厂、备注）与'
            '<b>车型技术参数</b>（类型/轴式/功率/构造速度/制造厂/简介）。'
            '型号没收录时会给出<b>相近型号</b>，点一下即可改查。</p>'
            '<p><b>从记录直接查：</b>「当前解码」表格上<b>右键</b>，'
            '有「记录详情…」「查该车次…」「查该机车配属…」三项，不用手输；'
            '「列车信息」卡片的「配属查询」按钮也会带上当前机车直接查。</p>'
            '<p><b>配属数据来自哪：</b>机车配属号段表来自开源项目 <b>LBJ_Console</b>'
            '（GPL-3.0），随程序内置一份快照（一万六千多行号段）。'
            '「工具 → 检查数据更新（机车配属表）」可手动从上游拉取增量；'
            '<b>自动检查</b>默认开启（启动 20 秒后、每周一次），'
            '在「配置 → 数据更新」里可以关掉或改间隔，那里也能看到当前数据的'
            '行数、型号数、更新日期与来源，并区分「内置快照 / 已更新」。</p>'
            '<p><b>数据更新安全吗：</b>下载后先<b>严格校验</b>（行数、型号数、'
            '号段数字合法性、中文配属占比），任何一项不过就直接丢弃、保留原数据；'
            '写入的是用户目录 <code>%LOCALAPPDATA%\\CR-LBJ-Receiver\\data</code>，'
            '旧文件留 <code>.bak</code>，内置快照永远可回退。'
            '断网时只会记一条日志，界面照常用。</p>'
        )
        text10.setWordWrap(True)
        text10.setStyleSheet('font-size: 13px; line-height: 1.5;')
        contentLayout.addWidget(text10)

        contentLayout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

        btnClose = QPushButton('关闭')
        btnClose.clicked.connect(self.accept)
        layout.addWidget(btnClose)


# ===========================================================================
# 关于对话框
# ===========================================================================
class AboutDialog(QDialog):
    """关于对话框。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('关于')
        self.setFixedSize(spx(540), spx(480))
        layout = QVBoxLayout(self)

        title = QLabel('中国铁路 LBJ 列车预警器解码程序')
        title.setStyleSheet(f'color: {CLR("accent")}; font-size: 16px; font-weight: bold;')
        title.setWordWrap(True)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        ver = QLabel('v3.2.1  ·  2026-11')
        ver.setStyleSheet(f'color: {CLR("dim")}; font-size: 12px;')
        ver.setAlignment(Qt.AlignCenter)
        layout.addWidget(ver)

        layout.addWidget(self._sep())

        info = QLabel(
            '<p>本项目兼容 RTL_TCP 模式与 OpenWebRX 作为数据源，'
            '对中国铁路机车在 821.2375 MHz 频段发送的 LBJ 列车预警信号'
            '进行实时接收与解码，可解析车次、机车、线路、公里标、'
            '方向、速度等报文信息，并支持 ETA 到达时间估算。</p>'
            '<p>机车参数经中国中车官网、维基百科等公开资料核对。</p>'
            '<p style="margin-top: 10px;">参考 Sdr-Is-Fun 等 GitHub 上众多 LBJ 解码相关代码，'
            '并使用 PySide6、Leaflet、OpenRailwayMap 等技术构建界面与地图。</p>'
            '<p style="margin-top: 12px;"><b>开源致谢</b></p>'
            '<p>· <b>LBJ_Console</b>（<a href="https://github.com/undef-i/LBJ_Console">'
            'github.com/undef-i/LBJ_Console</a>，作者 <b>undef-i</b>，GPL-3.0）：'
            '本项目的<b>机车配属号段表</b>（<code>loco_roster.csv</code>，一万六千余行）与'
            '<b>机车类型代号表</b>（<code>loco_type_info.csv</code>）直接取自该项目'
            '（<code>resources</code> 分支），安卓端界面骨架与地图图源思路亦参考其实现，'
            '特此致谢。</p>'
            '<p>· <b>OpenStreetMap</b> 贡献者（ODbL）：底图与铁路数据基础；'
            '<b>OpenRailwayMap</b>（CC-BY-SA）：铁路图层瓦片；'
            '<b>Leaflet</b>（BSD-2-Clause）：地图渲染引擎；'
            '<b>RailGo</b> / 中国铁路 12306：车次时刻表查询。</p>'
            '<p>· 天地图（国家地理信息公共服务平台）、高德地图、百度地图：底图瓦片服务。</p>'
            '<p style="margin-top: 10px;">特别鸣谢 <b>BI7AIG</b> 对 OWRX 测试提供的帮助。</p>'
            '<p style="margin-top: 12px;"><b>作者：BG2GBQ</b></p>'
        )
        info.setWordWrap(True)
        info.setStyleSheet('font-size: 13px; line-height: 1.6;')
        info.setOpenExternalLinks(True)
        layout.addWidget(info)

        layout.addWidget(self._sep())

        declTitle = QLabel('声明')
        declTitle.setStyleSheet(f'color: {CLR("warn")}; font-size: 14px; font-weight: bold;')
        layout.addWidget(declTitle)

        decl = QLabel(
            f'<p style="color:{CLR("warn")}"><b>本程序仅供学习与研究使用。</b></p>'
            '<p>不得用于任何商业或非法用途。</p>'
        )
        decl.setWordWrap(True)
        decl.setStyleSheet('font-size: 13px; line-height: 1.6;')
        layout.addWidget(decl)

        layout.addWidget(self._sep())

        license = QLabel('License: GPL v3 | Copyright (C) 2026 BG2GBQ')
        license.setStyleSheet(f'color: {CLR("faint")}; font-size: 11px;')
        license.setAlignment(Qt.AlignCenter)
        layout.addWidget(license)

    def _sep(self):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f'background-color: {CLR("border")};')
        return line


# ===========================================================================
# 12306 联网车次查询
# ===========================================================================
