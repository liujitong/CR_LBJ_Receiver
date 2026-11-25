#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""使用说明与关于对话框。

本模块由 GUI 组装层 cr_lbj/gui.py 导入；共享运行时（Qt 类别名、主题色、
缩放、控件工厂）统一来自 cr_lbj/runtime.py。
"""
from __future__ import annotations

from cr_lbj.runtime import *  # noqa: F401,F403

class ManualDialog(QDialog):
    """使用手册对话框：传统 TCP 与 OWRX 配置说明。"""

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
        title1 = QLabel('一、传统 RTL-TCP 模式')
        title1.setStyleSheet(f'color: {CLR("accent")}; font-size: 15px; font-weight: bold;')
        contentLayout.addWidget(title1)

        text1 = QLabel(
            '<p>使用 RTL-SDR Blog v4 等硬件接收器，通过 <b>rtl_tcp</b> 服务将 IQ 数据'
            '通过网络传输到本程序。</p>'
            '<p><b>配置步骤：</b></p>'
            '<p>1. 安装 RTL-SDR 驱动：使用 <b>Zadig</b> 将 RTL2832U 设备的 Windows 驱动'
            '替换为 <b>WinUSB</b>（在 Zadig 中勾选 "List All Devices"，选择 RTL2832U，'
            '选择 WinUSB 后点击 Replace Driver）。</p>'
            '<p>2. 启动 rtl_tcp 服务：在命令行中运行<br>'
            '<code>rtl_tcp -a 127.0.0.1 -p 1234</code></p>'
            '<p>3. 在本程序配置中设置：</p>'
            '<ul style="margin-left: 20px;">'
            '<li>模式：传统 RTL-TCP</li>'
            '<li>主机：127.0.0.1</li>'
            '<li>端口：1234</li>'
            '<li>DC 偏移：50000 Hz（推荐值，避开零频 DC 干扰）</li>'
            '<li>采样率：960000 Hz</li>'
            '<li>频率：821.2375 MHz</li>'
            '<li>增益：15.7 dB（根据信号强度调整）</li>'
            '<li>PPM 校正：1.0（根据晶振偏差调整）</li>'
            '<li>信道带宽：35 kHz</li>'
            '<li>AFC：建议开启</li>'
            '</ul>'
            '<p><b>说明：</b>传统模式下，SDR 硬件调谐在目标频率 - DC偏移 处，'
            '通过 DDC（数字下变频）将信号搬移到基带，避免零频 DC 分量干扰。</p>'
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
            '<p>2.0 版支持保存多套数据源，在“配置 → 数据源”中切换：</p>'
            '<ul style="margin-left: 20px;">'
            '<li><b>本机 USB（自动）</b>：插上 RTL-SDR 即可，程序自动查找并启动 '
            '<code>rtl_tcp.exe</code>，退出时自动关闭，无需再开命令行。'
            '要求已用 Zadig 安装 WinUSB 驱动。</li>'
            '<li><b>RTL-TCP</b>：连接局域网或本机已有的 rtl_tcp 服务（默认 1234 端口）。</li>'
            '<li><b>OWRX</b>：连接 OpenWebRX 的 rtl_tcp 兼容端口（DC 偏移设为 0）。</li>'
            '</ul>'
            '<p>发布包已内附 <code>rtl_tcp.exe</code>、<code>rtlsdr.dll</code> 等工具，'
            '装好驱动、插上棒子就能用，无需另外安装工具包。'
            '源码运行时把它们放在项目的 <code>tools/rtl/</code> 目录即可（也兼容'
            '<code>RTL_TCP_Server</code> 子目录与 PATH）；'
            '也可在配置里手动指定路径。“检测设备”按钮会调用 '
            '<code>rtl_test -t</code> 列出本机设备。</p>'
        )
        text4.setWordWrap(True)
        text4.setStyleSheet('font-size: 13px; line-height: 1.5;')
        contentLayout.addWidget(text4)

        sep4 = QFrame()
        sep4.setFrameShape(QFrame.HLine)
        sep4.setStyleSheet(f'background-color: {CLR("border")};')
        contentLayout.addWidget(sep4)

        # ---- 地图 ----
        title5 = QLabel('五、高德地图与经纬度')
        title5.setStyleSheet(f'color: {CLR("accent2")}; font-size: 15px; font-weight: bold;')
        contentLayout.addWidget(title5)
        text5 = QLabel(
            '<p><b>经纬度来源：</b>只有扩展长报文（地址 1234002 / 1234001）携带经纬度；'
            '基础帧 1234000 只有车次/速度/公里标。因此地图上出现标记的前提是：'
            '<b>收到同一列车的基础帧 + 长报文</b>。</p>'
            '<p><b>配置步骤：</b></p>'
            '<p>1. 打开 <a href="https://console.amap.com/dev/key/app">高德开放平台控制台</a>，'
            '创建应用并添加 Key，服务平台选择 <b>Web端(JS API)</b>。</p>'
            '<p>2. 复制 <b>Key</b> 与旁边的 <b>安全密钥</b>，填入“配置 → 地图与车次规则”。</p>'
            '<p>3. 同一页的 <b>默认中心</b> 填一个地名（如 <code>南昌站</code>）——'
            '不用填经纬度，程序启动时用高德<b>地理编码</b>把它解析成坐标再把视图挪过去，'
            '<b>不会在图上加任何标记</b>；留空则显示全国概览（不再默认北京）。'
            '解析结果会缓存，断网也能回到上次的位置。</p>'
            '<p>4. 保存后地图立即重建，无需重启 DSP；上段左侧就是实时地图；'
            '点击标记可查看车次、时间、速度、公里标、线路、机车与坐标。'
            '地图卡片上的「中心」按钮可随时回到默认中心。</p>'
            '<p><b>说明：</b>LBJ 经纬度为 WGS-84，高德底图为 GCJ-02。程序在落点前会自动做 '
            'WGS-84 → GCJ-02 纠偏，标记可贴合道路；详情里仍显示原始 WGS-84 坐标。</p>'
            '<p><b>视野与跟随：</b>标签下方的小白球就是<b>真正的坐标点</b>（球心压在报文经纬度上）。'
            '「跟随」只在列车真的移动约 30 米以上时才重新居中；'
            '<b>你一拖动地图或用滚轮缩放，跟随会自动暂停</b>（按钮同步取消勾选），'
            '点一下「跟随」即可恢复。</p>'
            '<p><b>完整文档：</b>程序目录 <code>docs/</code> 下有三份手册——'
            '<code>用户手册.md</code>（操作与排障）、'
            '<code>高德地图配置手册.md</code>（Key 申请与标注开发）、'
            '<code>技术参考.md</code>（报文结构、DSP 链路与车次规则全表）。</p>'
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
        title7 = QLabel('七、界面与操作（v2.3）')
        title7.setStyleSheet(f'color: {CLR("accent2")}; font-size: 15px; font-weight: bold;')
        contentLayout.addWidget(title7)
        text7 = QLabel(
            '<p><b>布局（全景式，不用切页签）：</b>一屏分三段——'
            '<b>上段</b>左侧是实时地图（约六成宽），右侧上「当前解码 / 历史记录」两张表、下「列车信息」卡片；'
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
            '<p><b>配置分页：</b>配置窗口按「数据源配置 / 射频设置 / 到达估算 / 地图与车次 / '
            '解码与界面 / 外观主题」六页分开，不再是一条长滚动条。</p>'
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

        title9 = QLabel('九、车次信息卡与 12306 查询')
        title9.setStyleSheet(f'color: {CLR("accent")}; font-size: 15px; font-weight: bold;')
        contentLayout.addWidget(title9)
        text9 = QLabel(
            '<p>右下角「车次信息」卡片会根据报文里的<b>报文类别</b>自动判断该车次能不能查 12306 时刻表。</p>'
            '<p><b>可查：</b>客运列车——动车组、城际、市郊、旅游、普速（含快速 / 特快旅客列车）、'
            '普通旅客快车 / 慢车、直达特快列车。</p>'
            '<p><b>不查：</b>货运与路用类——快运、货物、班列、始发 / 煤炭 / 石油 / 空车 / 技术直达、'
            '检测、确认、回送、单机、补机、小运转、摘挂、超限、军用、轨道车、路用、救援、试运行、自备等。'
            '这类车次在 12306 上本来就没有时刻表。</p>'
            '<p><b>匹配方式：</b>先剥掉类别串末尾括号里的速度说明（如“快速旅客列车 (160km/h)”），'
            '再按关键字归类，因此类别后面带不带速度后缀都不影响判断。'
            'v2.2 修复了此前“普速旅客列车被误判为不可查询”的问题。</p>'
        )
        text9.setWordWrap(True)
        text9.setStyleSheet('font-size: 13px; line-height: 1.5;')
        contentLayout.addWidget(text9)

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

        ver = QLabel('v2.6  ·  2026-11')
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
            '并使用 PySide6 等技术构建 GUI 界面。</p>'
            '<p>特别鸣谢 <b>BI7AIG</b> 对 OWRX 测试提供的帮助。</p>'
            '<p style="margin-top: 12px;"><b>作者：BG2GBQ</b></p>'
        )
        info.setWordWrap(True)
        info.setStyleSheet('font-size: 13px; line-height: 1.6;')
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
