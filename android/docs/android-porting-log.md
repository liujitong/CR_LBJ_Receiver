# Android 版移植过程日志（v3 手机端）

> 用途：记录每个阶段的实施内容、遇到的问题与解决方案，便于异常时归档回溯。
> 项目：CR_LBJ_Receiver Android 移植（`C:\lbj_src`，junction `android/` ← `E:\预警器`）
> 更新规则：每完成一个子步骤立即追加；构建失败/报错原样记录。

## 里程碑总览

| 里程碑 | 内容 | 状态 | git 提交 |
|---|---|---|---|
| M0 | 工程骨架 + JNI 链路打通 | 完成 | 前期提交 |
| M1 | USB/pipe fd 采样 + 环形缓冲 + StatusFrame | 完成 | a9e1eb9 |
| M2a | C++ DSP 1:1 移植 + POCSAG/BCH/GBK | 完成 | a9e1eb9 |
| M2b | 对拍（OWRX 120s 真实 IQ）0 差异 | 完成 | a9e1eb9 / 0f97271 |
| M2c | Kotlin 业务层（分类/去重/ETA）+ 引擎/VM/UI 接线 | **进行中** | — |
| M3 | Room 历史 / CSV / 前台服务 / IQ 录制 / 地图 / 设置页 | 未开始 | — |

## M2c 进行中记录（2026-11-26）

### 已完成
1. **对拍达成 0 差异**（20 条真实 LBJ 报文逐字段一致）。关键修复：
   - scipy lfilter 无条件升 double → C++ 全链改 C128Fir（double 累加）
   - scipy 1.18 Blackman-Harris 系数 0.01168
   - `out[::dec]` 长度 = ceil(n/dec)（3277 不是 3276），影响跨块 FM/DPLL
   - numpy float32 pairwise 求和（AFC 均值）
   - GBK 表列索引 lo>0x7F 时需减一（190 列跳过 0x7F）
   - speed 用 str(int()) 语义 → std::to_string
   - result_json.cpp double 传 %d 的 UB → 类型化 lambda
2. **UsbSource.kt 语法错误修复**：`RECEIVER_EXPORTED if (false) 0 else 0` →
   按 Build.VERSION >= 33 分支注册（RECEIVER_EXPORTED / 旧 API 直注册）。
3. **新建 engine/DecodeEvent.kt**（业务层 1:1 移植）：
   - DecodeEvent：native result_json → Kotlin 模型（含 timestamp/timeStr/uid/eta）
   - TrainClassifier：2026 新版 / 2014 旧版 / auto（T/K/X 按速度≥200 区分，
     速度缺失按 2026-12-25 日期）；纯数字车次回送/货运 25+3 段区间表
   - RecordDeduplicator：key=baseTrain|direction，窗口 2.5s，质量分
     （详细+100/坐标+40/无错+20/线路+10/机车+15/线路名+10/速度+5/公里标+5/RSSI 0~1），
     score>slot+3.0 才替换并沿用 uid，否则丢弃计数
   - ArrivalEstimator：本站公里标 + 线路映射，状态文案与桌面版逐条一致
   - RouteUtils：sanitizeRouteName / isValidRouteName / parseKm / parseRouteKmMap
4. **重写 engine/DecoderEngine.kt**：settings 驱动 init/start/stop/release；
   start(settings, source) → source.open() fd → nativeStart(mode, fd, freq, sr, gain×100, ppm)；
   解码回调线程内：JSON 解析 → 分类 + ETA → 去重 → events StateFlow（保留 100 条）；
   StatusFramePoller 150ms 接 status StateFlow。
5. **重写 vm/ReceiverViewModel.kt**：AndroidViewModel；settings StateFlow +
   SharedPreferences 持久化；updateSettings 会 release→init 重建 DSP 链；
   USB 权限在 IO 协程内经 createSource→UsbSource.requestPermission() 完成。
6. **ReceiverSettings 扩展**：trainScheme / dedupeWindow / etaMaxMin /
   userKm / routeKmText（业务参数），含 prefs 读写。
7. **重写 ui/pages/DecodePage.kt**：真实 RSSI 历史曲线（240 点 @150ms）、
   门限线、门控状态文案；当前解码大卡片 + 最近解码列表（去重 uid key）。

### 待办（本里程碑内）
- [x] StatusPage 接 StatusFrame 真实统计（块率/丢块/重连/CPU/缓冲/tuner）
- [x] SettingsPage 最小可编辑（数据源/射频/门控/AFC/业务五组，保存即重建链路）
- [x] LbjApp 传参核对（MapPage/HistoryPage M3 前保持占位）
- [x] ./gradlew :app:assembleDebug 构建通过
- [ ] 模拟器（Resizable_Experimental）安装 + OWRX nc.example.com:5678 实测解码
- [ ] git 提交 M2c

### 构建错误记录（已修复）
1. UsbSource.kt `resumeWithException` 未导入 → `import kotlin.coroutines.resumeWithException`
2. DecodePage Divider 在新 Compose 已移除 → 改 Box+1dp 背景线
3. SettingsPage/StatusPage 局部 `fun` 内调用 Composable → 局部函数加 @Composable
4. ReceiverViewModel RouteUtils 包名错（在 engine 不在 core）→ 改 import

### 模拟器实测记录（2026-11-26 凌晨）
1. **首轮 OWRX 实测**：启动后 pipe 链路建立，RSSI -51.5 dB 门控"有信号"，
   2532 块 / 0 丢块 / CPU 7.5%。~3 分钟后 OWRX 上游断开（pump EOF），
   状态帧变为"饥饿帧"（rssi=-140，门控沿用旧值"开启"）——暴露**无自动重连**问题。
2. **App 级解码验证**（rtl_tcp 回放服务器 + capture_960k.iq）：
   - 新增 `tools/duipai/replay_rtl_tcp.py`：rtl_tcp 协议无限循环播放 120s 录制 IQ，
     模拟器 10.0.2.2:5678 直连宿主机。
   - prefs 用 run-as 写入最小 lbj.xml（仅覆盖 host=10.0.2.2，其余键回落默认）。
   - 结果：**端到端解码成功** —— 解码页大卡片 V1281 / 快速旅客列车(120km/h) /
     速度 97 km/h / 公里标 1436.1 / 机车 HXD3C-00948 / RSSI -28.2 dB / AFC -3767 Hz；
     历史列表多记录滚动；ETA"线路未知"（未设本站公里标，语义正确）；
     车次分类与桌面版规则一致。
3. **断流看门狗**（ReceiverViewModel.startWatchdog，3s 周期）：
   检测 status.errorState==1 或 source 关闭 → 自动重建数据源并重连。
   实测：杀掉回放服务器 → "[监护] 数据流中断…自动重连" → 每 3s 重试 →
   恢复服务器 → "[监护] 重连成功"，块率恢复 14.5/s。✅
4. 构建产物：`app/build/outputs/apk/debug/app-debug.apk`（4 ABI native 全量编译）。

### M2c 结论
Kotlin 业务层 + 引擎/VM/UI 接线完成并在模拟器端到端验证（解码事件流、
分类、去重、ETA、状态体检、设置编辑、断流重连）。USB 真机链路仍标注"未验证"。
git 提交：见下方 git log。

### 已知风险 / 未验证项
- USB 真机链路（rtlsdr_open_fd）模拟器无 USB host 设备，保持"未验证"标注
- TRAIN_2026_EMU_BEFORE 用 2026-12-25 UTC 毫秒常量近似（语义等价，
  时区差 ≤8h 不影响车次判定场景）
- watchdog 重连在 socket ECONNREFUSED 时每次等满 10s 连接超时（日志显示
  10000ms），可考虑缩短连接超时，暂不阻塞

## 环境备忘（复用）
- Gradle 构建：`cd /c/lbj_src && JAVA_HOME="C:\Program Files\Java\latest\jdk-21" ./gradlew :app:assembleDebug`
- 对拍工具：`tools/duipai/`（capture_iq.py / offline_decode.py / compare.py，
  Python 用 D:/anaconda3/python.exe，系统 python 无 numpy）
- adb 推送路径 MSYS 转义：`//data/local/tmp/...` 双斜杠；推送后 chmod 755
- CLI 对拍：lbj_cli（x86_64 模拟器 adb 直跑），需 --hash-style=both +
  -Wl,-z,max-page-size=16384
- OWRX 测试源：nc.example.com:5678（960kS/s、增益 15.7dB、dcOffset 0）
