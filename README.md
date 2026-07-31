# 中国铁路 LBJ 列车预警器解码程序 (CR-LBJ-Receiver)

一款基于 RTL-SDR 的中国铁路 LBJ 列车预警信号实时接收与解码程序，提供 Windows GUI 界面，适合火车迷与无线电爱好者使用。

## 功能特性

- **双数据源支持**：兼容 RTL_TCP 直连模式（RTL-SDR Blog v4 等）与 OpenWebRX (OWRX) 转发 IQ 流
- **实时解码**：对中国铁路机车在 821.2375 MHz 频段发送的 LBJ 列车预警信号进行实时解码
- **全字段解析**：车次、机车号、机车代号、线路、公里标、方向、速度、报文类别
- **报文类型**：支持短报文、合并报文、独立长报文三种格式
- **ETA 估算**：基于本站公里标与列车速度，实时估算列车到达时间与距离
- **机车详情**：双击记录可查看机车图片与技术参数（资料来源：Trainfanz.com）
- **12306 联网查询**：详细报文可一键查询车次时刻表
- **历史记录**：基于 SQLite 的本地历史数据库，支持导出 CSV
- **实时频谱**：pyqtgraph 绘制的实时频谱图与 RSSI 门限显示
- **信号质量监测**：RSSI、AFC 频偏、BCH 纠错状态、网络诊断

## 技术细节

| 项目 | 说明 |
|------|------|
| 中心频率 | 821.2375 MHz |
| 采样率 | 960 kHz → 48 kHz 基带（多级抽取） |
| 接收链路 | IQ 校正 → DDC → 半带抽取 → 信道 FIR → FM 鉴频 → AFC + RSSI 门控 |
| 解码链路 | 高斯平滑 → DPLL 比特恢复 → 帧同步 → BCH(31,21) 译码 → BCD 提取 → 报文解析 |
| 纠错能力 | BCH(31,21) 单比特纠错 + 干扰告警 |
| AFC | 自动频率跟踪，补偿 ±8 kHz 频偏 |
| GUI 框架 | PySide6 + pyqtgraph |

## 环境依赖

- Python 3.10+
- PySide6
- pyqtgraph
- numpy
- scipy

安装依赖：

```bash
pip install PySide6 pyqtgraph numpy scipy
```

## 运行方式

### 从源码运行

```bash
python SDR_ALL_LBJ_GUI.py
```

### 打包为 EXE

```bash
pyinstaller SDR_LBJ.spec --clean --noconfirm
```

打包结果输出至 `dist/CR-LBJ-Receiver.exe`。

## 使用说明

1. **配置数据源**：在配置页填写 RTL_TCP 服务器地址与端口，或勾选 OWRX 模式
2. **设置本站公里标**：用于 ETA 到达时间估算
3. **启动接收**：点击启动按钮，等待 LBJ 信号触发
4. **查看记录**：双击当前列表或历史列表中的记录，查看完整解码详情
5. **机车详情**：在记录详情中点击"机车详情"按钮，查看机车图片与技术参数

## 数据来源

- 机车图片与资料：[Trainfanz.com (我们的火车站)](https://www.trainfanz.com)
  - [电力机车列表](https://www.trainfanz.com/h-col-229.html)
  - [内燃机车列表](https://www.trainfanz.com/h-col-141.html)
- 12306 时刻表：通过公开接口实时查询

## 致谢

- 参考 Sdr-Is-Fun 等 GitHub 上众多 LBJ 解码相关代码
- 特别鸣谢 **BI7AIG** 对 OWRX 测试提供的帮助

## 声明

本程序仅供学习与研究使用，不得用于任何商业或非法用途。

## License

GPL v3 | Copyright (C) 2026 **BG2GBQ**
