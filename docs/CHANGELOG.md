# 更新记录

> 适用版本：**v3.2.11**（2026-11-26） ｜ 适用端：桌面 / 安卓 ｜ 最后更新：2026-11-26
>
> 本文件记录各版本变更，**最新版本在最上方**；历史条目保持发布时的原样，只做格式与链接校正。
> 当前版本 v3.2.9 的条目由项目维护者在发版时补充（本文不预置）。

版本号规则（自 v3 起）：

- **大版本**：`v3`（架构/形态级变更才升），以后由用户指定新大版本。
- **小版本**：`v3.x`——功能更新，**桌面与安卓同时升**。
- **最小版本**：`v3.x.y`——修复/打磨版本，桌面端与安卓端**同版本号**发布。

桌面端与安卓端**共用同一个版本号**（当前为 `v3.2.9`），因为 v3 的目标就是
「一次发布、两端同步」。

## 目录

- [v3.2.11 · 2026-11-26](#v3211--2026-11-26)
- [v3.2.10 · 2026-11-26](#v3210--2026-11-26)
- [v3.2.9 · 2026-11-26](#v329--2026-11-26)
- [v3.2.8 · 2026-11-26](#v328--2026-11-26)
- [v3.2.7 · 2026-11-26](#v327--2026-11-26)
- [v3.2.6 · 2026-11-26](#v326--2026-11-26)
- [v3.2.5 · 2026-11-26](#v325--2026-11-26)
- [v3.2.4 · 2026-11-26](#v324--2026-11-26)
- [v3.2.3 · 2026-11-26](#v323--2026-11-26)
- [v3.2.2 · 2026-11-26](#v322--2026-11-26)
- [v3.2.1 · 2026-11-26](#v321--2026-11-26)
- [v3.2.0 · 2026-11-26](#v320--2026-11-26)
- [v3.1.0 · 2026-11-26](#v310--2026-11-26)
- [v3.0.0 · 2026-11-26](#v300--2026-11-26)
- [历史版本（v2.x 桌面端 / v3.0 安卓 M0–M3）](#历史版本v2x-桌面端--v30-安卓-m0m3)

---

## v3.2.11 · 2026-11-26

> 版本号：桌面 `cr_lbj.__version__ = 3.2.11`，安卓 `versionName = 3.2.11` / `versionCode = 331`。
> 主题：**跟随语义按用户口径定稿（开了跟随，任何新信号都追过去）**、
> **双端解码对拍复核（0 差异）**、**代码签名证书规范化（DN 精简）**。

### 一、跟随语义定稿：开了跟随，任何新信号都追

用户三次澄清后的最终口径：

> 「只要开了跟随，来新车就过去追踪」→「同车次算一个车，不管换不换」→「同车次新信号也要跳过去」。

据此定稿（桌面/安卓共用同一份 `shared/web/railmap.html`）：

* **follow = true 时**：只要收到**任何新信号**（同车次新位置、换机车、新车次、一次多辆），
  页面立即 `userTouched = false`（解除拖动暂停）→ 焦点切到**最新信号那辆** → 居中过去；
* **拖动地图**：只是"暂停到下一帧"——下一条报文到达即恢复跟随（不再落盘 `mapFollow=false`，
  也不再打印「检测到手动拖动地图，已暂停自动跟随」那条误导日志）；
* **同一车次只算一个车**：地图 id 用 `baseTrain`，换机车不新增标记；标记上的机车号取
  "最近一条可靠值"（短报文 `----` 不会把机车信息冲掉）；
* **follow = false 时**：不跟随（唯一关闭方式 = 用户点「跟随」按钮）；
* `autoCenter()` 保留 30m 阈值，避免原地抖动时反复重设中心。

**实测（真实 GUI，7 个场景全部 PASS）**：

| 场景 | 结果 |
|---|---|
| 拖图 → 新车次 | ✅ 恢复跟随并跳过去 |
| 拖图 → 同车次换机车 | ✅ 跳（同车次新信号也算） |
| 拖图 → 一次推多辆 | ✅ 跳到 ts 最新的那辆 |
| 跟随中 → 同车次位置更新 | ✅ 继续跟随 |
| 拖图 → 同车次位置更新 | ✅ 跳（新信号） |
| 连续 2 次拖图 + 2 辆新车 | ✅ 每次都追 |
| 关闭跟随 → 推新车 | ✅ 不跳（符合预期） |
| 误报「检测到手动拖动」日志 | ✅ 无 |

### 二、双端解码对拍复核：0 差异

用仓库自带对拍套件对同一份 960k IQ 抓包（`android/tools/duipai/capture_960k.iq`）复核：

```
C++ 条数 20，Python 条数 20
✅ 对拍通过：0 差异
```

即**安卓 native 解码核心与桌面 Python 解码器逐字段一致**（车次/方向/速度/公里标/线路/
机车/经纬度/RSSI/AFC 等，浮点按序列化精度留容差）。

此前（v3.2.9）已修的两处"能力差异"仍有效：

1. **RSSI 迟滞默认值**：安卓 `3.0` → `4.0`（对齐桌面 `DEFAULT_RSSI_HYST_DB`），
   门控释放不再比 PC 快、尾部报文不漏；
2. **安卓干扰告警**：`pendingWarnings` 原来只写不读，现由 engine 每块排空输出
   （logcat + UI 日志都能看到）。

> 结论：**解码算法/参数已拉齐**；剩余差异只在硬件层（OTG 供电、CPU 实时性）与
> 设备 tuner 型号本身，不改变"同一份 IQ → 同一份解码结果"。

### 三、代码签名证书规范化（Windows）

第一版自签名证书用了 7 个 DN 字段（C/O/OU/L/S/CN/E），结果 SmartScreen 的「发行者」
把每个字段都摊开显示成
`bg2gbq@mlxkj.xyz, CN, 北京, 北京, BG2GBQ, 刘纪彤, 刘纪彤（BG2GBQ）`。

改用 **OpenSSL** 按 `tools/codesign-openssl.cnf` 生成规范证书：

* Subject 精简为 3 字段：`C=CN, O=LiuJitong, CN=刘纪彤（BG2GBQ）`；
* 显式 `string_mask = utf8only`（中文编码正确）；
* `CA:TRUE, pathlen:0`（自签名根需此才能通过链验证）+ `CodeSigning` 用途；
* RSA 4096 / SHA256 / 10 年；
* `tools/make_codesign_cert.ps1`（生成）、`tools/sign_exe.ps1`（签名+时间戳）、
  `tools/install_cert.cmd`（双击安装信任）构成可复现工具链。

> 注意：Windows 对"向受信任根添加证书"有**强制人工确认**（安全警告框），
> 无法脚本静默完成——需要用户双击 `安装签名证书.cmd` 并点「是」。
> 自签名只能解决"属性页发布者显示为谁"；SmartScreen 的「无法识别的应用」属于
> 云端声誉，需 CA/EV 或 Azure Trusted Signing 才能消除（详见 `docs/代码签名.md`）。

### 四、验证

* `pytest` **132 passed**（跟随回归测试更新为"任何新信号都跳"口径）。
* 真实 GUI 7 场景实测全 PASS（见上表）。
* 双端解码对拍 **0 差异**。
* 安卓 `assembleRelease` 通过、签名 `CN=CRLBJREC`；桌面 `build.py` 通过。

---

## v3.2.10 · 2026-11-26

> 版本号：桌面 `cr_lbj.__version__ = 3.2.10`，安卓 `versionName = 3.2.10` / `versionCode = 330`。
> 主题：**跟随语义统一（拖图/回中心/定位只暂停，新车到达自动追过去）**、
> **安卓改用 CN=CRLBJREC 正式签名**、**Windows 产物补齐发布者版本信息与代码签名**。

### 一、跟随语义统一：开了跟随就一直追

用户反馈：「我不是说了，以后只要开了跟随，来新车就过去追踪吗？怎么还有提示？」
并补充实测要求（"你可以多试试几次"）。

* **旧行为**：拖动地图 / 回中心 / 转到自己位置，宿主都会把 `mapFollow` 写成 `false`
  并打印「检测到手动拖动地图，已暂停自动跟随」——一旦落盘 false，后续新车**永远不再跟随**。
* **新语义（两端一致）**：
  * **唯一关闭跟随的方式** = 用户点「跟随」按钮；
  * 拖动地图 / 回中心 / 转到自己位置 → 页面仅置 `userTouched=true`（**暂停**），
    宿主**不写配置、不改按钮**；
  * **出现新车**（此前没跟过的 id）→ 页面自动清除暂停、焦点切到新车并居中
    （即"来新车就追过去"）；同一辆车的后续位置更新仍保持暂停，不打扰用户查看。
* 桌面：`_onMapFollowChanged` 只在用户手动关闭时触发，日志改为
  「已关闭自动跟随（点「跟随」可重新开启）」；按钮 tooltip 显示暂停原因。
* 安卓：跟随胶囊在暂停态显示 **「跟随·暂停」**（点击可手动恢复）。
* **实测证据（真实 GUI，模拟拖动 + 推送新车）**：
  * 拖动后 `locked=true`、`follow=true`、`mapFollow=true`、无"已暂停"误报日志；
  * 推送新车 K9999（哈尔滨坐标）后 2.5s：`locked=false`、`follow=true`、
    `center=[126.628288, 45.759693]` —— **地图确实跳到新车位置**。

### 二、安卓签名：改用 CN=CRLBJREC

用户要求：「安卓签名有 CN=cardwallet 改为 CN=CRLBJREC，要不然区分不开」。

* 新建 `android/keystore/crlbjrelease.jks`：
  * 主体 `CN=CRLBJREC, OU=Mobile, O=LiuJitong, L=Beijing, ST=Beijing, C=CN`；
  * RSA 4096 / SHA384withRSA / 有效期 30 年（至 2056）；
  * SHA-1 `37:05:B5:2D:FE:F9:97:CD:2D:98:97:22:D2:5D:56:05:6C:7C:23:76`；
  * SHA-256 `14:BB:E3:4D:00:42:17:FA:9E:9F:F5:BD:F1:95:E8:F6:B2:87:EC:BF:14:52:BF:CC:18:9C:7A:40:29:32:3E:AD`。
* `android/keystore.properties`（**gitignore，含口令，不入库**）指向新 jks；
  `assembleRelease` 产出已签名 APK，`apksigner` 校验 DN/SHA-1 与上述一致。
* 与 CardWallet（`CN=CardWallet`）区分开，两个 App 可按证书区分。
* ⚠️ 签名变更后，旧的 debug 签名安装包**需卸载再装**（签名冲突）。

### 三、Windows：发布者信息 + 代码签名

用户要求：「PC 端有发布者未知的 Windows Defender，发布者用刘纪彤（BG2GBQ），
bg2gbq@mlxkj.xyz，需要其他字段请告知我」。

* **版本资源**（`desktop/SDR_LBJ.spec` 自动生成 `version_info.txt`，版本号取自
  `cr_lbj.__version__`，不再与代码脱节）：
  * `CompanyName` = 刘纪彤（BG2GBQ）
  * `ProductName` = CR-LBJ-Receiver 列车预警器
  * `FileDescription` = 中国铁路 LBJ 列车预警器
  * `LegalCopyright` = © 2026 刘纪彤（BG2GBQ）· GPL-3.0
  * `Comments` = bg2gbq@mlxkj.xyz · 仓库地址
  * 实测 `(Get-Item exe).VersionInfo.CompanyName` 已显示「刘纪彤（BG2GBQ）」。
* **代码签名**（`tools/sign_exe.ps1`）：
  * 自签名证书 `CN=刘纪彤（BG2GBQ）, O=刘纪彤, OU=BG2GBQ, L=北京, S=北京, C=CN,
    E=bg2gbq@mlxkj.xyz`（4096-bit RSA / SHA256 / 10 年），已对 exe 签名并加
    DigiCert 时间戳；`Get-AuthenticodeSignature` 显示
    `SignerSubject=CN=刘纪彤（BG2GBQ）…`、`TimeStamper=DigiCert`。
  * **限制说明**：自签名证书链终止于非受信任根，Windows 属性页/ SmartScreen 仍显示
    「未知发布者」。要让 Windows 认，两种办法：
    1. 本机运行 `tools/install_codesign_trust.ps1`（管理员）把证书导入
       「受信任的根证书颁发机构」→ 本机显示发布者「刘纪彤（BG2GBQ）」；
    2. 购买 **CA 签发的代码签名证书（OV / EV）** → 所有电脑直接显示发布者。
  * 详见 [`docs/代码签名.md`](代码签名.md)（含购买证书需要提供的字段清单）。
* **签名材料保护**：私钥 `.pfx` / 口令 / 安卓 `.jks` 全部进 `.gitignore`，不入库。

### 四、验证

* `pytest` **132 passed**（`test_follow_resume_on_new_train` 增补：
  回中心/定位不得写 `mapFollow=false`，桌面与安卓源码均断言）。
* 真实 GUI 实测（桌面）：开跟随 → 模拟拖动 → 保持跟随 → 推新车 → 自动跳转（坐标核对通过）。
* 安卓 `assembleRelease` 通过，`apksigner` 校验签名 `CN=CRLBJREC`。
* 桌面 `build.py` 通过；exe 版本资源与 Authenticode 签名均已核对。

---

## v3.2.9 · 2026-11-26

> 版本号：桌面 `cr_lbj.__version__ = 3.2.9`，安卓 `versionName = 3.2.9` / `versionCode = 329`。
> 主题：**解析不出车次的帧改为上下行干扰统计（只记日志、不入库）**、
> **双端解码逻辑/默认参数对齐**、**修复「拖动地图后新车不再自动跟随」**。

### 一、上下行干扰统计（两端同口径）

用户要求：「对于 `-----` 解析不出来车次的很多内容，统计计算为上/下行干扰，并给出日志提示，
安卓端/电脑端都是如此要求，且不保存在数据库」。

* **判定**：短报文车次字段（BCD 前 6 位）不是字母数字 → 车次无效；或最终 `train` 为空/`----`
  → 按功能码判**上行（func=3）/ 下行（func=1）**，累加干扰计数。
* **不再入库**：这类帧**不产出解码结果**（桌面 `DecodeResult` / 安卓 `LbjResult`），
  因此不会写进历史数据库；旧实现会把 `----` 当车次建会话，往库里塞一堆「----」记录。
* **日志提示**：限速 1 秒一条 `⚠ 探测到下行信号 干扰严重（车次字段无法解析，已计为干扰、不入库）`。
* **状态可见**：
  * 桌面「运行状态仪表板 → 解码与去重」新增「干扰 上行 / 干扰 下行（帧）」；
  * 安卓「状态页 → 数据流」新增同样两个指标格子。
* **历史库清理**（一次性）：
  * 桌面 `HistoryDb` 启动时删除 `train` 为空/`----`/`未知` 的旧记录（计数 `lastCleaned`）；
  * 安卓 Room **DB v2→v3 迁移**执行同样的 `DELETE`（实测清掉 64 条历史 `----` 记录）。

### 二、双端解码对齐核查（结论：算法已 1:1，修了参数差异）

逐项核对后确认解码算法**本来就是 1:1 移植**，并有 IQ 回放对拍套件保证
（`android/tools/duipai/`：`capture_960k.iq` + `compare.py`，差异必须为 0）：

| 环节 | 核对结果 |
|---|---|
| BCH(31,21) 生成多项式/LFSR/伴随式表 | 一致（`0x369=873`、`buildSyndromeLut` 首见优先） |
| 帧同步字 `SYNC_STD/SYNC_INV/IDLE_WORD` | 一致（2094142936 / 2200824359 / 2055848343） |
| DPLL 参数（MD=0.02·step、0.005/0.1、迟滞 0.03、衰减 0.0005） | 逐行一致 |
| BCD 提取（20 位/5 字符、4 位倒序、`0123456789*U -)(` 字符表） | 一致 |
| 机车代号表 `LOCO_TABLE` | **141 条逐项一致**（程序化比对，0 差异） |
| GBK 表（线路名解码） | **126×190 表逐码点一致**（0 缺、0 错） |
| 报文类型判定（短/合并/独立长报文地址+长度阈值） | 一致 |
| 经纬度度分解析（DDD+MM.MMMM / 范围校验） | 一致 |
| 车次分类（2027-01-01 切换） | 共享向量文件，双端测试消费同一份 |

**修复的真实差异（这才是"安卓解不全"的原因）：**

1. **RSSI 迟滞默认值不一致**：安卓 `rssiHystDb = 3.0`，桌面 `DEFAULT_RSSI_HYST_DB = 4.0`
   → 安卓门控释放更快，**报文尾部/后续详细帧更容易被漏掉**。已把安卓默认值改为 **4.0** 对齐。
2. **安卓干扰告警从未显示**：`LbjParser::pendingWarnings` 只被 `push_back`，
   **engine 从不消费**——BCH 错包告警写进数组后永远没人读。已在 `dspLoop` 每块后
   排空并通过 `log("[告警] …")` 输出（UI 日志 + logcat 都可见）。
3. 安卓干扰计数通过 **StatusFrame 保留字 word[19]**（低 16 位上行、高 16 位下行）上报，
   帧结构长度不变（仍 52 word / 208 字节）。

> 性能差异说明：两端共用同一套定参数 DSP（半带×2 + 信道 FIR + 整数抽取），
> 安卓为 C++ 定点/浮点混合但**数值路径与 Python 一致**（对拍通过）；
> 未为性能放宽任何阈值/精度，避免"为了跑得动而解码结果不同"。

### 三、修复「拖动地图后新车不再自动跟随」

用户反馈：「点击跟随功能后，即使拖动地图了，新来个车也可以直接转过去，来新车不会自动跟随」。

* **根因**：拖动地图时页面置 `userTouched=true`（本意只是**暂停**跟随），
  但**宿主把它当成了"关闭跟随"**：
  * 桌面 `_onStatusPoll` 看到 `locked` 就把「跟随」按钮取消勾选并写 `mapFollow=false`；
  * 安卓 `MapPage` 轮询到 `st.locked` 就把 `mapFollow` 置 false。
  一旦落盘成 false，页面 `follow` 也是 false，之后新车永远不会自动跟随。
* **修复**：
  * 页面（`shared/web/railmap.html`）：`upsertTrain()` 返回"是否新车"；`api.update()`
    在**跟随意向仍开启**且出现新车时，清除 `userTouched`、把焦点切到新车并居中
    ——即"拖动过地图，新来个车也直接转过去"。
  * 桌面：不再因 `locked` 取消勾选/写配置，改为把按钮提示改成
    「跟随已暂停（你拖动过地图）；有新车到达会自动恢复跟随并跳转」。
  * 安卓：不再因 `st.locked` 关闭 `mapFollow`，改用 `mapLocked` 状态记录暂停态，
    跟随胶囊显示 **「跟随·暂停」**（点击可手动恢复）。
* **验证**（模拟器实测）：开启跟随 → 拖动地图 → 胶囊显示「跟随·暂停」、
  `mapFollow` 仍为 `true`；页面在下一辆新车到达时自动恢复跟随并跳转。

### 四、验证

* `pytest` **132 passed**（新增 `tests/test_decoder_interference.py`：9 项，
  覆盖桌面干扰计数/限速/`----` 不产出结果不建会话 + 安卓源码契约 + 双端迟滞默认值对齐；
  新增 `test_follow_resume_on_new_train` 回归跟随修复）。
* 安卓单测 40/40；`assembleDebug` 通过（versionCode 329）。
* 模拟器实测：
  * 状态页出现「干扰 上行 / 干扰 下行」指标；
  * 日志出现 `[告警] ⚠ 探测到下行信号 干扰严重`（原先安卓端永远看不到）；
  * Room v3 迁移后库里 **64 条 `----` 记录被清除**，剩余均为有效车次；
  * 跟随暂停态显示「跟随·暂停」且 `mapFollow=true` 保持不变。
* 桌面 `desktop/build.py` 打包通过。

---

## v3.2.8 · 2026-11-26

> 版本号：桌面 `cr_lbj.__version__ = 3.2.8`，安卓 `versionName = 3.2.8` / `versionCode = 328`。
> 主题：**安卓「历史」页签改为「信息」页**（承担 PC 端车次信息 + 机车信息职能）、
> **历史记录改为设置内管理并支持增删改查**、**解码详情与 PC 端逐项对齐**、
> **双端默认中心只保留经纬度并修正城市坐标漂移**。

### 一、安卓：历史页 → 信息页，历史移入设置

用户要求：「安卓端历史页调整为信息页，承担 PC 端车次信息和机车信息的功能；信息页支持查看
近几次解码的车次/机车具体信息；历史页调整到设置里，并实现增删改查」。

* **新增 `ui/pages/InfoPage.kt`（底部 Dock「信息」页）**：
  * 顶部横向选择条：最近 12 条解码记录，默认选中最新一条，可翻看近几次；
  * **列车信息卡**：车次 / 方向 / 速度 / 公里标 / 机车 / 线路 / 类别 / 到达时间 / 距离 /
    经纬度 / 本站 —— 与桌面 `TrainInfoPanel.FIELDS` 逐项对应；
  * **车次信息卡**：RailGo / 12306 结果（等级、担当全称、客运段、配属段、车型、
    始发→终到+时刻、全程里程、开行日、交路、主要停站），担当/配属走 `DepotNames` 全称化；
  * **机车信息卡**：型号+号段、中文名、配属单位全称、制造厂全称、牵引参数、备注、简介
    —— 对齐桌面 `LocoInfoPanel` 的 名称/配属/详情/简介 四段；
  * 「查看记录详情」弹出五页签详情弹层；「历史记录管理」一键跳设置的历史子页。
* **历史记录移入「设置 → 历史记录」**（`ui/pages/HistoryPage.kt` 重写为 `HistorySection`）：
  * **查**：实时关键词过滤（车次/机车/线路/备注）+ 按车次/按机车分组 + 条数统计；
  * **改**：长按记录编辑备注（Room v2 新增 `note` 列）；
  * **删**：多选（全选）/删除选中/删除全部（带确认）；
  * **增**：解码成功自动入库（沿用 uid 去重 REPLACE）；
  * 导出 CSV 保留（列与桌面 `HistoryDb.exportToCsv` 完全一致）。

### 二、安卓：记录详情与 PC 端逐项对齐

用户要求：「解码详细信息里的信息要和 PC 端保持一致，什么都是，这种信息一定要双方一致；
安卓端也可以用页签展示细节，如同 PC 端双击的详细信息一样」。

* **新增 `ui/components/RecordDetailSheet.kt`**，五个页签与桌面 `RecordDetailDialog`
  **同名同序**：解码结果 / 原始数据 / BCD / 解码过程 / 纠错码字。
  * 解码结果 21 项字段（时间、车次、纯数字车次、前缀、方向、速度、公里标、线路、机车号、
    机车代号、配属、号段、车型参数、类别、报文类型、经度、纬度、线路校验、BCH 纠错、
    预计到达、预计距离）—— 标签与取值格式照搬桌面（`----`/`---`/`%.6f` 口径一致）；
  * 机车简介行 + 「机车详情」按钮（技术参数 / 配属 / 号段 / 简介 / 资料来源）；
  * RailGo 区块：等级·担当 / 配属·车型 / 始发→终到 / 主要停站（最多 6 个）/ 来源，
    失败时「未查询到（原因）」，非详细报文「不查询」—— 文案与桌面 `_onRailgoResult` 一致；
  * 原始数据 / BCD / 解码过程（7 段推演）/ 纠错码字（BCH(31,21) 31 位二进制 + 十六进制）
    的文本内容与桌面 `_buildDecodeProcess` 等逐行一致；
  * 底部「在地图中查看（天地图）/ 关闭」，坐标缺失时按钮禁用 —— 与桌面一致。
* 数据层补齐：`DecodeEvent.rawCodewords`（从 native JSON 解析）、Room 新增
  `rawCodewords` / `hasInterference` / `note` 三列（**DB v1→v2 迁移**，不丢历史数据）。
* 解码页与历史页/信息页共用同一详情弹层，双击/点击行为统一。

### 三、两端：配属/制造厂全称化打通（原来只有 PC 有）

* 新增安卓 `core/DepotNames.kt`：从桌面 `data/depot_names.py` **逐条移植**（局简称表、
  68 个机务段全称表、制造厂全称表、括号备注处理、"查不到原样返回不猜"策略）。
* 信息页/详情/机车详情里的配属、制造厂、RailGo 担当局段一律走全称，
  与桌面显示**同一张表、同一算法**；后续改表需双端同步（文件头已注明）。

### 四、双端：默认中心只保留经纬度 + 城市坐标修正

用户要求：「检查一下中国各大城市的坐标，哈尔滨、南昌都漂移到哪里去了…这个字段以后只保留经纬度」。

* **坐标修正**（`shared/data/places.csv`，人工逐条核对城市中心 WGS-84）：
  * 哈尔滨 `45.80,126.53` → **`45.7597,126.6283`**（原值落在松北/群力西侧，偏离市区约 8 km）；
  * 南昌 `115.86` → **`115.9060`**（原值偏西约 4.5 km，改为八一广场—南昌站一带）；
  * 其余 44 城核对无 >5 km 偏差，保持原值；注释补充校验日期与"仅用于视野"口径。
* **字段只保留经纬度**：
  * 桌面删除 `CoreConfig.mapCenterAddress`；配置页城市下拉仅作选择便捷，选中只写
    `mapCenterLng/Lat`；地图页居中/坐标标签不再拼城市名；
  * 安卓删除 `ReceiverSettings.mapCenterName`；设置页「默认中心」显示
    `lat, lng（城市名）` 摘要，选择城市只回填经纬度；地图 `centerTo('')` 不再传地名。
  * 旧配置里的城市名字段读取时忽略、下次保存后自然消失（双端一致）。

### 五、验证

* `pytest` **122 passed**；安卓单测 40/40；`assembleDebug` 通过。
* 模拟器实测：Dock 显示「地图/解码/信息/状态/设置」；设置页出现「历史记录」组
  （副标题"N 条 · 查看/改备注/删/导出"）；「默认中心」显示 `28.6800, 115.8600（南昌）`，
  选哈尔滨后变为 `45.8000, 126.5300（哈尔滨）`（修正后为 45.7597,126.6283）。
* 桌面 `desktop/build.py` 打包通过（含 13 篇 docs）。

---

## v3.2.7 · 2026-11-26

> 版本号：桌面 `cr_lbj.__version__ = 3.2.7`，安卓 `versionName = 3.2.7` / `versionCode = 327`。
> 主题：**安卓端 RTL 型号识别与推荐配置（对齐桌面端规则）、数据源文案统一为 RTL-TCP / OWRX；
> 文档全部收进 `docs/` 并按统一模板重编排、润色；桌面端界面文案同步统一。**

### 一、安卓：RTL 型号识别 + 按型号推荐（对齐 PC 端）

用户要求「安卓参考 PC 端的推荐方法，识别 RTL 型号，推荐相关配置；OWRX、RTL-TCP 也要推荐」。
桌面端早已有 `core/usb_direct.py` 的 `probeDevices()` / `recommendProfile()`（读 tuner 型号与
可用增益表 → 推荐 960 kS/s / 手动增益 / DC 50 kHz，关 AGC）。安卓端补上等价能力：

* **native 新增型号探测**：`engine.cpp` 增 `LbjEngine::probeTuner(fd)`——临时
  `rtlsdr_open_fd` → 读 `rtlsdr_get_tuner_type` + `rtlsdr_get_tuner_gains` → 立刻 `rtlsdr_close`，
  返回 JSON（`tunerType` / `tuner` / `gains`）；JNI `nativeProbeTuner(fd)` 暴露给 Kotlin。
* **Kotlin `core/RtlProfile.kt`**（新）：与 PC 端规则**逐条对齐**——
  * tuner 表：Unknown / E4000 / FC0012 / FC0013 / FC2580 / R820T / R828D；
  * R828D → 15.7 dB 起调；R820T/R820T2 → 19.7 dB；E4000/FC0012/FC0013 → 19.7 dB；未知 → 15.7 dB；
  * 统一 960 kS/s + 手动增益（AGC 关）+ DC 偏移 50 kHz（本地硬件），并附人话说明；
  * `recommendFor(type, tunerId)`：USB 优先用探测到的型号；**RTL-TCP** 说明「同一块 RTL 硬件经网络
    转发，与 USB 共用射频参数」；**OWRX** 说明「采样率由服务器端决定、DC 偏移设 0」。
* **设置页「数据源与射频」**：
  * 新增「RTL 型号：R820T（或未检测）」行；运行中直接读 native 已填的
    `StatusFrame.tunerTypeId`，未运行时点「检测设备」走 `UsbSource.probeTunerModel()`
    （请求权限 → openDevice → 探测 → 关闭，失败给明确原因，如设备被占用/未插棒）；
  * 切换类型时的推荐弹窗升级为「型号 / 类型 + 推荐参数 + 说明」，并继续保持 v3.2.6 的
    「采用推荐值 / 保持当前」；采用后仍走草稿保存（不静默落盘）。

### 二、两端文案统一

* 数据源显示名统一：**USB 直连 / RTL-TCP / OWRX**（内部 id `usb` / `rtl_tcp` / `owrx` 不变，
  工具名 `rtl_tcp.exe` 等实际文件名保留原文）。
* 安卓：`RtlProfile.typeLabel()` 统一驱动设置页 chip、数据源列表副标题、解码/地图页状态胶囊；
  默认数据源名改为「本地 RTL-TCP」。
* 桌面：`decoder.py` 的 `SOURCE_TYPE_NAMES`（本机 USB (RTL-TCP 中转)）、启动失败/超时日志、
  USB 回退提示，以及 `runtime.py` 数据源预设名、`help_dialogs.py` 手册说明，统一为 RTL-TCP。

### 三、仓库整理：所有文档进 `docs/`

用户要求「所有文档必须放在 /docs 下，并对 docs 所有文档重编、整理、润色」：

* `shared/NOTICE.md` → `docs/NOTICE.md`；`android/docs/*.md` → `docs/`（`安卓移植日志.md`、
  `安卓模块划分方案.md`，并标为历史存档）；`docs/调研-USB直连与设备自适应连接.md` →
  `docs/USB直连与设备自适应.md`（调研稿转正式文档）；删除空目录 `android/docs/`。
* 根 `README.md` 保留为仓库入口，精简为「简介 + 快速开始 + 文档导航（13 篇指向 docs/）+
  致谢要点 + 声明/License」；原详细内容全部下沉 docs。
* 13 篇文档统一元信息块（适用版本 v3.2.9 / 适用端 / 最后更新）+ 「目录」+ 章节层级；
  清理与 CHANGELOG 重复的「版本变化」章节、修正历史转义损坏与编号断档、去掉过期描述
  （历史页签、ORM 伪造 Referer、文档散落路径等）；术语统一 RTL-TCP / OWRX / USB 直连。
* 同步更新引用：`desktop/build.py` 的 `REQUIRED_DOCS`（8 → 13 项，含改名与归档文档）、
  `usb_direct.py` / `updater.py` / `tools/gen_shared_data.py` 里的文档路径注释、README 与
  各文档间的相对链接（`grep shared/NOTICE.md` 全仓 0 处）。

### 四、验证

* `pytest`：**122 passed**（新增 `test_docs_single_directory`：docs 目录完整、NOTICE 已迁、
  `android/docs` 已归档；README 断言改为「入口 + docs 导航」）。
* 安卓 `assembleDebug` 通过、单测 40/40；桌面 `desktop/build.py` 通过（产物含 13 篇文档）。
* 模拟器实测：设置页「RTL 型号：未检测」+「检测设备」按钮；无 USB 设备时提示
  「检测失败：未找到 RTL-SDR 设备（先插电视棒）」；切 RTL-TCP 弹「RTL-TCP 推荐配置」
  （型号/类型 + 960 kS/s · 19.7 dB · DC 50 kHz + 说明）。
* 真机 USB 直连（v3.2.3 起修复）：`[USB] tuner#3 ...（fd 直连）` 正常、接收中；
  运行中点「检测设备」会提示设备被占用（符合预期，可先停止再检测）。

---

## v3.2.6 · 2026-11-26

> 版本号：桌面 `cr_lbj.__version__ = 3.2.6`，安卓 `versionName = 3.2.6` / `versionCode = 326`。
> 主题：**安卓数据源改为「草稿 + 显式保存」（三种类型都有推荐配置、返回时询问保存/另存为、覆盖语义）；
> 瀑布图再平滑（纵向插值 + 对数压缩 + 帧率提升），并修复主线程掉帧；桌面中段三卡重排，机车信息不再被裁。**

### 一、数据源：草稿 + 显式保存（用户反馈"自动保存问题太大"）

v3.2.5 的多数据源是"改一下就自动保存"，用户要求改成明确语义：

* **编辑只改草稿**：连接/射频字段修改不再自动落盘，页内出现「未保存的修改 +
  保存（覆盖「当前数据源名」）」提示条，可随时显式保存；
* **切换类型必给推荐配置**：`usb / rtl_tcp / owrx` 任一类型切换都会弹「推荐配置」：
  * 本机 USB：240 kS/s · 19.7 dB · DC 50 kHz
  * RTL-TCP 网络源：960 kS/s · 15.7 dB · DC 50 kHz
  * OWRX：960 kS/s · 15.7 dB · DC 0
  「采用推荐值 / 保持当前」二选一；
* **返回时询问保存**（含系统返回键 `BackHandler`，不能绕过）：
  * **保存并返回** → 覆盖当前激活的数据源（"切换数据源之后点保存就是覆盖"）；
  * **另存为…** → 输入名称，新建一条数据源；
  * **放弃** → 丢弃修改；
* **切换数据源**（点列表里的「切换」）→ 立即生效并重置草稿到新激活项；
  「删除」同样立即生效；「＋ 把当前配置另存为新数据源」改为弹**名称输入框**。

### 二、瀑布图再平滑 + 帧率提升

用户反馈"再平滑、帧率高一点"。这一版：

* **帧率**：`StatusFramePoller` 轮询 150ms → **70ms**（≈一个 DSP 块 68ms，不再漏帧）；
  频谱帧缓存 140 → **240 帧**，弹层高度 176 → 200dp；弹层里实时显示"每 70 ms 刷新"。
* **平滑**：
  * **横向三点平滑** `[0.25,0.5,0.25]` 抹掉 bin 台阶；
  * **纵向也插值**（每帧 2 行 + 帧间按小数权重混合）——原来的横向"条纹感"消失；
  * **对数动态范围压缩** `ln(1+4t)/ln5`：弱信号层次更丰富，不再非黑即亮；
  * **256 级颜色查找表**：每像素只插值一次 + 查表。
* **性能修复（重要）**：位图从 `remember`（组合线程 = 主线程）改为
  `produceState + Dispatchers.Default` 后台生成。实测旧写法 12 万像素 × 每秒
  6~14 次在主线程跑，会 `Choreographer: Skipped 127 frames`（主线程卡 2 秒）；
  改后台后无掉帧日志，且上一帧没算完会被自动取消、不堆积。
* 说明：**频谱原始分辨率受 native 限制固定 32 bin**（`kSpectrumBins`），再高的"细节"
  靠插值+平滑逼近；若要真正更高分辨率需改 C++ FFT 分箱与 StatusFrame 协议（两端对拍），
  不在本版范围。

### 三、桌面：中段三卡重排（机车信息不再被裁）

用户反馈"机车信息那里有被遮挡，查看时刻表、配属查询的按钮占的地方太多，频谱也可以适当缩小"：

* **按钮进标题栏**：`查看时刻表` / `配属查询` 从卡片正文右侧（96px 宽 + 10px 间距）
  移到 **卡片标题栏右侧**，正文拿到整卡宽度。按钮改用原生按钮 + 实例级 QSS
  （`#cardAction` 压掉 `TOUCH_STYLE` 里的 `min-height: 28px`）——qfluentwidgets 的
  按钮**不吃 `setFixedHeight`**，`small_button(h=20)` 实测仍是 41px，直接塞进
  标题栏会把整行撑到 41px，反而更吃正文高度；
* **宽度重排**：中段三卡 `5 : 3 : 3` → **`4 : 3.4 : 3.4`**（1720 宽下 770/462/462 →
  628/534/534），叠加按钮让出的宽度，机车卡正文可用宽度 +54%；
* **高度**：中段高度占比 24% → 27%、上限 180 → 196px；末段「牵引参数 + 简介」
  改为可伸缩（`stretch=1`）——QLabel 开 `wordWrap` 后 sizeHint 会低估行数，
  差一行时最后一行正好被下沿切一半，给它伸缩权后不再出现；
* 校验：`pytest` 121/121；离屏渲染 1720×960 / 1366×768 逐标签比对
  `heightForWidth`，两档尺寸下**全部标签无裁切**（1280×720 高度仍差约一行，
  该尺寸需用「配属查询」看全量简介）。

### 四、返回键导航修复（用户反馈"设置里按返回直接回桌面，太反人类"）

原来全 App 只有设置页一处返回拦截，且设置**首页**按返回会直接 finish Activity（回桌面）。
现在改为**三级返回**（`LbjApp` 记录 `lastTab` + `SettingsPage(vm, onBack)`）：

1. 设置**子页**有未保存数据源草稿 → 弹「保存数据源配置？」；
2. 设置**子页** → 回**设置菜单**（不再直接退出）；
3. 设置**菜单** → 回**上一个标签页**（如解码页），不再回桌面。

标题栏左上角箭头与系统返回键走同一套逻辑；其他主页面（解码/地图/历史/状态）按返回
仍按系统默认退出，符合 Android 习惯。

### 五、验证

* 安卓 `assembleDebug` 通过、单测 40/40；`pytest` 全绿。
* 模拟器交互实测（adb 逐步点击 + uiautomator dump）：
  切 OWRX → 弹「OWRX 服务器 推荐配置」→「采用推荐值」→ 出现「未保存的修改」→
  点返回 → 弹「保存数据源配置？」→「另存为…」→ 输入名称 → 列表新增
  「数据源 4OWRX_TEST · OWRX · 使用中」→ 自动返回设置首页；
* 真机（USB 直连接收中）瀑布帧数按 70ms 增长；主线程不再掉帧。

---

## v3.2.5 · 2026-11-26

> 版本号：桌面 `cr_lbj.__version__ = 3.2.5`，安卓 `versionName = 3.2.5` / `versionCode = 325`。
> 主题：**安卓端多数据源 + 设置页「数据源与射频」合并、瀑布图平滑化、地图页浮层重排。**

### 一、安卓：数据源与射频合并 + 多数据源

* 设置页菜单由 7 组收敛为 **6 组**：`数据源` + `射频` 合并为 **「数据源与射频」**（旧子页 id `rf` 仍兼容，点过就不会打开空白页）。
* 新增**多数据源**（`core/ReceiverSettings.kt`）：
  * `SourceProfile(name/type/host/port/sampleRate/gainDb/ppm/dcOffsetHz)` 与
    `sources: List<SourceProfile>` + `activeSource`；
  * 默认三条：本机 USB 直连（240k / 19.7dB / DC 50k）、本地 rtl_tcp（127.0.0.1:1234）、
    OWRX（127.0.0.1:8073）；JSON 落盘到 SharedPreferences；
  * 设置页「数据源（点击切换）」列表：点非当前项即**切换并重建 DSP 链路**；
    「＋ 把当前配置存为新数据源」新增一条；每项可「删除」（至少保留一条）；
    编辑连接/射频字段会自动回写到当前项（`withActiveSnapshot()`）；
  * `ReceiverViewModel` 新增 `selectSource / addSource / removeSource / renameSource`，
    切换后写一行 `[数据源] 已切换到「…」` 日志。
* 射频字段（频率/增益/PPM/带宽/DC 偏移）与连接字段合并到同一张「连接与射频」卡。

### 二、安卓：瀑布图平滑化（不再"糊成马赛克"）

* 窄带频谱固定 **32 bin**，原实现逐 bin 画矩形铺满全宽（每块约 30px），视觉上就是方块。
* 现在（`DecodePage.buildWaterfallBitmap`）：
  * **横向线性插值**：每两个 bin 之间插 8 列，再用 `FilterQuality.Medium` 拉伸到全宽；
  * **smoothstep 对比度拉伸**：弱信号层次更清楚、强信号更亮；
  * 帧缓存 80 → **140 帧**（≈21s 瀑布），高度 160 → 176dp；
  * 位图渲染（`Bitmap.setPixels` + `Image`）比逐矩形绘制更省 CPU。

### 三、安卓：地图页浮层重排

* 原布局：左上「数据源状态胶囊」+ 右上 **5 个独立浮动胶囊**（跟随/图层/回中心/转到自己位置/缓存本区域）——散、挡地图。
* 现在：
  * **右上角**：状态胶囊（OWRX 接收中等）+ 一张**紧凑工具卡**，内含
    「跟随 / 图层 / 回中心 / 缓存本区域」四项（图标 + 短文字，当前项强调色）；
    缓存进行中直接显示 `缓存 done/total`；
  * **右下角**：「转到自己位置」独立为 **圆形定位 FAB**（`Icons.Filled.MyLocation`，
    地图 App 通行位置），权限/定位失败提示逻辑不变；
  * 移除 `FloatPill` 依赖（该页不再用）。

### 四、验证

* 安卓 `assembleDebug` 编译通过；单测 40/40；`pytest` 全绿。
* 模拟器实测（结构与文本证据）：设置页 6 组菜单、「数据源（点击切换）」列表三项 +
  「使用中」标记、切换后日志 `[数据源] 已切换到…`；地图页右上工具卡 4 项 + 右下定位按钮。

---

## v3.2.4 · 2026-11-26

> 版本号：桌面 `cr_lbj.__version__ = 3.2.4`，安卓 `versionName = 3.2.4` / `versionCode = 324`。
> 主题：**桌面端二级窗口「大得超出屏幕 / 不自适应」修复；顺带修复配置对话框 `CONFIG_PAGES`
> 崩溃回归；核对 ORM 透明度链路并清理死方法。**

### 一、新增 `fit_dialog_to_screen()`（`ui/widgets.py`）

各对话框原先写死 `resize(spx(1040), spx(700))` 这类尺寸。在 1366×768、或 1280×800@200%
（逻辑可用区只有 640×400）的副屏上，`spx()` 还会按 UI_SCALE 放大 → 窗口顶出屏幕、
右侧/底部内容被裁、按钮点不到。

新函数（经 `cr_lbj.runtime` 转发，所有 `from cr_lbj.runtime import *` 的模块都能用）：

* 取窗口所在屏（`windowHandle().screen()`）；**未 show 时用鼠标所在屏**兜底
  （与主窗口 `_currentScreen` 同一思路）；
* 目标尺寸 = `min(spx(design), 可用区 - 边距)`；**下限同样不超屏幕**；
* 居中到该屏可用区；异常时退回"按设计尺寸"，绝不让自适应本身把窗口搞崩。

### 二、六个二级窗口改造

| 窗口 | 原 | 现 |
|---|---|---|
| 历史记录 `history_dialog.py` | `spx(760)×spx(460)` / `spx(1040)×spx(700)` | `fit(1040, 700, 760, 460)` |
| 车次/机车配属 `query_ui.py` | `spx(620)×spx(480)` / `spx(860)×spx(720)` | `fit(860, 720, 620, 480)` |
| 用户手册 `ManualDialog` | `resize(spx(700), spx(640))` | `fit(700, 640, 460, 400)` |
| 关于 `AboutDialog` | **`setFixedSize(spx(540), spx(480))`（不可缩放）** | `fit(540, 480, 420, 360)`，**改为可缩放** |
| 状态仪表板 `StatusDashboard` | `resize(spx(720), spx(660))` | `fit(720, 660, 520, 440)` |
| 配置 `ConfigDialog` | **裸像素** `setMinimumSize(720,560)` / `resize(820,660)` | `fit(820, 660, 720, 560)`（设计像素） |

### 三、表格列宽自适应

* **历史记录**：原先 9 列全 `ResizeToContents` + 线路列 `Stretch` —— 列一宽窗口就被撑大、
  出现横向滚动条。现在只让「时间」列按内容自适应，其余 `Interactive`（可压缩），
  「线路」吃余量；`table.setMinimumWidth(0)` + `ScrollBarAsNeeded`。
* **车次时刻表**：站名 `Stretch`；只让「到点/发点」两个关键列 `ResizeToContents`，
  「停留/里程」`Interactive` 并给默认宽度；同样放开最小宽度。

### 四、状态仪表板网格列数自适应

`_grid_cols()`：窗口宽度 **< spx(520) → 2 列**、**< spx(700) → 3 列**、否则 **4 列**；
`resizeEvent` 里列数档位变化时按上次分组自动重排（`_lastGroups` / `_builtCols`）。
窄窗口不再把每个指标方块压成一团。

### 五、ORM 透明度核对 + 死方法清理

* 链路确认已通：`ConfigDialog` 的滑块 → `cfg.mapRailOpacity` → 保存后
  `MainWindow._onConfigChanged()` → `mapPanel.setConfig()` → `host.apply_config()` →
  payload `railOpacity` → 页面 `applyConfig()` 里的 `railOpacity(cfg.railOpacity)` → 生效。
  冒烟断言 `_config_json()['railOpacity'] == 0.55` 通过，**未重复实现**。
* 删除 `map_panel.setRailOpacity()`：全仓库无调用方（透明度只走 `apply_config`），
  属僵尸方法。

### 六、顺带修复的回归（重要）

**配置对话框打开即崩**：`ConfigDialog.__init__` 用 `CONFIG_PAGES`，但 v3.1.1 把
`HistoryPanel` 删掉后这些常量留在 `ui/components/history_panel.py`，而
`config_ui.py` / `main_window.py` 是 `from cr_lbj.runtime import *`、**从未导入该模块** →
`NameError: CONFIG_PAGES is not defined`（配置菜单构建、首次运行预设 `default_sources()` 同样会炸）。
现在把 `CONFIG_PAGES` / `SOURCE_TYPE_LABELS` / `SOURCE_TYPE_TAGS` / `default_sources()`
移到 `cr_lbj/runtime.py` 共享层；`history_panel.py` 退化为兼容壳（只 re-export）。

### 七、验证

* `pytest`：**110 passed**（新增 `tests/test_desktop_ui_v324.py`：适配函数、六个窗口改造、
  表格列策略、仪表板列数、ORM 透明度 payload、死方法清理、CONFIG_PAGES 回归防护）。
* 离屏冒烟（800×800 可用区）：6 个窗口全部落在屏内且下限不超屏
  （history 768×700 / query 768×720 / manual 700×640 / about 540×480 / config 768×660 /
  dashboard 720×660）；dashboard 列数 480px→2、640px→3、720/900px→4。
* 桌面 `pytest` 与 `desktop/build.py` 均通过。

---

## v3.2.3 · 2026-11-26

> 版本号：桌面 `cr_lbj.__version__ = 3.2.3`，安卓 `versionName = 3.2.3` / `versionCode = 323`。
> 主题：**修复安卓 USB 直连（OTG 接 RTL-SDR）打不开设备：`rtlsdr_open_fd 失败 rc=-1`。**

### 根因（真机 SELinux 日志为证）

真机（Xiaomi 2510DRK44C / Android 17，OTG 接 RTL2832U）点「一键开始」报：

```
[usb] rtlsdr_open_fd 失败 rc=-1
native start 失败 rc=-1
```

`adb logcat` 里能看到 App 进程（域 `untrusted_app_34`）被 SELinux 拒绝：

```
avc: denied { read }    name="usb"  tcontext=u:object_r:usb_device:s0        tclass=dir
avc: denied { search }  name="usb1" tcontext=u:object_r:vendor_sysfs_usb_node:s0
comm="DefaultDispatch"
```

原因：`rtlsdr_open_fd()`（本项目补丁）里直接调 `libusb_init()`。**libusb 初始化默认会扫描
`/dev/bus/usb` 与 sysfs 做设备枚举**，而 Android 的普通 App 域没有这个权限（SELinux 直接拒绝）。
在 Android 上用「Java 传 fd + `libusb_wrap_sys_device`」的模式，必须显式关闭设备发现，
否则初始化/包装阶段就会失败，最终表现为 `rtlsdr_open_fd rc=-1`。

### 修复（`android/app/src/main/cpp/thirdparty/librtlsdr/src/librtlsdr.c`）

1. **Android 下用 `libusb_init_context()` + `LIBUSB_OPTION_NO_DEVICE_DISCOVERY`**
   （libusb 1.0.27 官方推荐搭配 `libusb_wrap_sys_device` 的用法），不再枚举 USB 设备；
2. **`libusb_claim_interface` 失败时先 `libusb_detach_kernel_driver` 再重试一次**
   （RTL2832U 可能被内核 DVB 驱动 `dvb_usb_rtx28xxu` 自动绑定，或上次会话未干净释放）；
3. **诊断可观测**：新增 `RTLSDR_LOGE` 宏，Android 下把关键错误写到 logcat
   （tag `librtlsdr`，如 `libusb_wrap_sys_device error N (fd=M)`、
   `usb_claim_interface error N`），native 的 `stderr` 默认不进 logcat，之前完全看不到原因；
4. `fd < 0` 提前拦截并报错（避免拿无效 fd 进 libusb）。

### 顺带修的两处日志/配置问题

5. **USB 启动日志不再拼接 `host:port`**：之前 `[启动] usb 主机:端口 …` 会把网络源的
   服务器地址打进 USB 日志（用户设备上还残留着旧配置里的地址，看起来像「USB 连到了
   某域名」）。现在 USB 源显示 `USB 直连`，只有网络源才显示 `host:port`。
6. **旧配置残留归一化**：`ReceiverSettings.load()` 在 `sourceType == usb` 时把
   `host/port` 归一化回默认值（USB 本来就不用这两个字段）。旧版本在设备
   SharedPreferences 里留下的网络服务器地址不会再出现在设置页/日志里（隐私清理）。
   注意：**这是设备上的历史配置残留，代码与 APK 里已无该字符串**（发布前已从源码与
   git 历史中清理，APK dex 校验为 0 命中）。

### 验证

- 4 个 ABI（arm64-v8a / armeabi-v7a / x86 / x86_64）的 CMake 编译全部通过。
- 真机复测：装 v3.2.3 后点「一键开始」，logcat 里可见 `librtlsdr` 的具体错误或成功路径；
  若仍失败，日志会直接给出 `wrap` / `claim` 的错误码与 fd，便于进一步定位
  （如 OTG 供电不足、设备被其他 App 占用）。

---

## v3.2.2 · 2026-11-26

> 版本号：桌面 `cr_lbj.__version__ = 3.2.2`，安卓 `versionName = 3.2.2` / `versionCode = 322`。
> 主题：**修复 OpenStreetMap / OpenRailwayMap 瓦片「418 Access blocked」——按两家使用政策做合规整改。**

### 为什么会 418（根因）

真机地图出现 `418`，OSM 返回的正文是：

```
Access blocked
App is not following the tile usage policy of OpenStreetMap's volunteer-run servers:
http://osm.wiki/Blocked
```

OpenStreetMap 官方瓦片与 OpenRailwayMap 都是**志愿者运营的公益服务**，其使用政策明确要求：

1. **必须提供可识别的 User-Agent**（含应用名 / 版本 / 联系方式），不得伪装成浏览器；
2. **禁止批量预取/下载瓦片**（bulk download、prefetch、离线整片抓取）；
3. 不得绕过限流、不得伪造 Referer 等来源标识。

本程序此前两点都踩了：代拉瓦片时用了**伪装浏览器的 UA**（`Mozilla/5.0 ... Chrome/128`），
且 v3.1 上线的「缓存本区域」会对当前视野 **z~z+3 一次预取几百上千张**瓦片 ——
于是被 OSM 判定违规，返回 **418 封禁**（通常为 IP 级临时封禁，数小时自动解除）。
另外 ORM 之前为了绕过 403，注入了 `Referer: https://www.openrailwaymap.org/`，
这属于**伪造来源**，同样违反其政策。

### 修复内容（两端一致）

1. **合规 UA**：OSM / ORM 请求统一使用可识别 UA
   `CR-LBJ-Receiver/3.2.2 (+https://github.com/liujitong/CR_LBJ_Receiver; ...)`；
   高德 / 百度 / 天地图仍用浏览器 UA（它们没有此类政策要求）。
   - 安卓：`core/TileCache.kt` 新增 `UA_APP` / `UA_BROWSER` / `userAgentFor()` / `isPolicyStrictHost()`；
   - 桌面：`ui/map_host.py` 拦截器对 `*.openstreetmap.org`、`*.openrailwaymap.org` 注入该 UA。
2. **移除伪造 Referer**：ORM 不再注入官方站点 Referer（带合规 UA 实测 200）。
3. **禁止批量预取**：
   - 页面 `railmap.html`：`isPolicyStrictSource()` 判定当前底图/铁路图源，命中 OSM/ORM 时
     「缓存本区域」直接拒绝并解释原因；新增 `LBJ.onCacheBlocked()` 回传宿主；
   - 安卓 `MapPage.runCacheArea()`：二次过滤 OSM/ORM 的 URL（`isPolicyStrictHost`），
     即使页面漏传也不会批量下载；
   - **浏览时的被动缓存保留**（用户看过的区域仍会缓存，离线可用），这不违反政策。
4. **底图不可达提示**：OSM 被封时明确解释「需合规 UA、禁止预取，本程序已整改；
   仍被封通常是临时封禁」；一键换底图改为推荐 **高德 / 天地图**（不再推荐 OSM）。
5. 文档：`docs/地图与图源.md` 增加「OSM / ORM 使用政策与合规要求」小节；
   `docs/NOTICE.md` 补充两条政策链接与我们的合规做法。

### 验证

- 本机实测：OSM（合规 UA）200；ORM（合规 UA、**无 Referer**）200 —— 证明去掉伪造 Referer 后仍可用。
- 桌面 `pytest` **110 passed**（新增合规断言：合规 UA 存在、伪造 ORM Referer 已移除、
  页面与安卓均过滤批量预取）。
- 真机（2510DRK44C，无线 adb）复测见交付说明：若该机 IP 仍在 OSM 封禁时效内，
  需等待解封（本程序已合规，解封后即可恢复）。

---

## v3.2.1 · 2026-11-26

> 版本号：桌面 `cr_lbj.__version__ = 3.2.1`，安卓 `versionName = 3.2.1` / `versionCode = 321`。
> 主题：**移动端 UI 打磨与地图行为修复、桌面端信息重新归位（历史记录/全称/RailGo）、地图页精简。**

### 一、安卓端

1. **状态页重排**：指标按「信号·门控（2 列大块）/ 数据流（3 列）/ 射频·链路（3 列）」三组等高分栏，
   数值加 `weight` + 省略号防撑高；`调谐` 改「调谐 MHz」+ 3 位小数、`累计块/丢块` 百万级紧凑显示；
   日志卡折叠 2 条 + 条数 + 展开限高 240dp 内部滚动并自动滚到最新（最多 60 条，前缀着色）。
2. **解码页去掉常驻频谱图**：改为一行信号摘要条（`信号 · dB · 有/无信号 · 瀑布 ›`）；
   点顶部**数据源状态胶囊**（如「OWRX · 等待首帧」）弹出 `ModalBottomSheet` 小瀑布
   （真实窄带频谱热力瀑布；无起伏时退回 RSSI 色条 + 门限虚线），关闭后不留占位。
3. **修复「设置里配了底图，打开地图仍退回高德」**：根因是 `railmap.html` 以 `file://` 加载时
   按默认底座渲染并 `notifyHost()` 上报，安卓 `HostBridge.onLayers` 无条件落盘把 `mapBase`
   冲成 `amap`（还会永久写坏设置）。修法三层：页面加 `configApplied` 门禁（`applyConfig`
   前不上报）；`MapPage` 加 `pageSynced` 门禁（`status().base` 与设置一致前，图层回报只记日志不落盘）；
   `persistLayers` 在偏移底图下不接受 `rail=off`（免得切回 OSM 后铁路层永不恢复）。
   实测：设置选百度 → 进地图即百度（prefs 保持 `baidu/orm_standard`），杀进程重启仍为百度。
4. **空态文案弱化**：`暂无列车坐标` 16sp 主文字色 → 12sp 三级灰，提示行 11sp；`EmptyState` 统一 13sp/11sp。
5. **全面屏适配**：非地图页用 `safeDrawing(Top+Horizontal)`、Dock 用 `safeDrawing(Bottom+Horizontal)`；
   地图页浮层加 `safeDrawing` insets（WebView 仍全屏铺满）。实测系统状态栏 74px，胶囊顶边从 37px 移到 111px。

### 二、桌面端

1. **历史记录移入「工具 → 历史记录…」（Ctrl+H）**：主界面取消「当前解码/历史记录」页签，只留当前解码；
   新对话框支持列表（时间/车次/方向/速度/公里标/线路/机车/类别/坐标）、双击/查看详情（复用记录详情）、
   删除选中 / 删除全部（二次确认）、刷新、导出 CSV。顺带修复 `HistoryDb.clear()` 在事务内
   `VACUUM` 导致「清空」实际失败的问题（Python 3.14）。
2. **配置对话框：数据源 + 射频合并**为「数据源与射频」一页（类型/设备 → 主机端口 → 采样率/频率/增益/
   PPM/带宽/DC 偏移/块大小 → RSSI 门控与 AFC 两列），配置分页由 7 页减为 6 页。
3. **「列车信息」面板瘦身**：去掉 v3.2 新增的「车次信息」「机车配属」两行（11 字段），
   车次/机车信息回归「车次信息」「机车信息」两卡展示。
4. **车次卡 / 机车卡：全称与 RailGo**：`TrainQueryPanel` 改为 RailGo 优先异步查询，显示
   「车次 始发→终到(到发时刻) / 等级 · 担当 全称 / 配属 · 车型 / 来源」；新增
   `data/depot_names.py` 做标准局段/制造厂简称→全称（如「南局南段→南昌局南昌机务段」，
   未收录的地方铁路原样返回不猜）；`LocoInfoPanel` 配属与制造厂分行显示全称。
5. **记录详情新增 RailGo 区块**：等级、担当局+段全称、配属段、车型、始发→终到（含时刻）、
   主要停站时间（最多 6 站），带「时刻表」按钮；查不到显示「未查询到 … 的车次信息」。

### 三、共享地图页（两端共用）

1. **地图弹窗精简**：只保留「车次 / 方向 / 速度 / 公里标 / 收到时间 / 轨迹里程 / 坐标」，
   去掉线路、机车、类别、车次信息、车底、配属（这些信息在桌面「车次信息/机车信息」卡片与
   安卓解码卡展示）。`LBJ.setTrainInfo` 保留为宿主推送通道，页面不再渲染。
2. **标记脚注可读性**：速度/公里标小字 9.5px → 11px、字重 600、加文字阴影与描边，
   夜间/日间底色分别加深到 0.88/0.94 不透明度；弹窗字号 12→12.5px。
3. **`configApplied` 门禁**（见安卓第 3 条），是两端「页面图层回报不冲掉用户配置」的基础。

### 四、测试与验证

- 桌面 `pytest`：**109 passed**（新增 `tests/test_desktop_ui_v311.py` 17 项与地图页 2 项契约断言）。
- 安卓 `tools/test.ps1`：**40/40**（DataUpdater 10 / LocoRoster 13 / TrainInfoClient 9 /
  TrainClassifier 3 / MapTrainInfo 5）。
- 桌面 `desktop/build.py` 打包成功；安卓 `assembleDebug` 成功。
- 实测：安卓设置选百度→地图即百度（重启仍保持）；桌面历史对话框造 6 条记录完成查看/删除/清空；
  RailGo 真实查询（G7 → 北京局天津客运段、D2234 → 成都局重庆客运段）；
  地图页 `configApplied` 冒烟（applyConfig 前零上报、之后上报用户底图）。

---

## v3.2.0 · 2026-11-26

> 版本号：桌面 `cr_lbj.__version__ = 3.2.0`，安卓 `versionName = 3.2.0` / `versionCode = 320`。
> 主题：**修复地图「可达却判不可达」误判与 ORM 铁路图层叠加（Referer）、双端展示车次·机车信息、致谢正式化。**

### 一、地图（误判修复 / ORM Referer 修复 / 失败判定规则）

**1. 修复「可达却判不可达」误判**

- **根因**：`shared/web/railmap.html` 的瓦片统计原先底图与铁路共用一个计数器
  （`tilesTotal` / `tilesFailed`）。OpenRailwayMap 官方瓦片缺 Referer 时整层 403，
  这些 `tileerror` 把计数器顶高，页面据此把**本可正常显示**的底图误判成「底图不可达」，
  弹出全屏换图提示，桌面坐标栏也变红「底图不可达，换一张」。
- **修复**：统计**按图层分离**为 `baseTileOk` / `baseTileFail`（底图）与
  `railTileOk` / `railTileFail`（铁路）；`tilesTotal()` / `tilesFailed()` 保留旧名但
  **只返回底图**统计（宿主兼容）。`LBJ.status()` 新增 `railTilesTotal` / `railTilesFailed`，
  原 `tilesTotal` / `tilesFailed` 只统计底图。
- **失败判定规则（现在）**：
  - 全屏「底图不可达」提示只在**底图**满足 `baseTileFail >= 6` 且
    （`baseTileOk === 0` 或 `baseTileFail >= baseTileOk * 19`，即失败率 ≥ 95%）时出现；
  - 铁路瓦片失败只弹一次小字 toast（`warnRailFail()`，失败 ≥ 4 张触发）并写状态行
    「铁路 N/失败 M」，**不再影响底图判定**；
  - 桌面坐标栏「底图不可达，换一张」仍按 `failed > 8` 且（`total == 0` 或
    `failed >= total × 0.9`）判定（`map_panel._TILE_FAIL_HINT`），但输入已是**纯底图**统计；
  - 安卓 `MapPage` 同步改为 `tilesFailed >= 6` 且（`tilesTotal == 0` 或
    `tilesFailed >= tilesTotal * 19`）。

**2. 修复 ORM 铁路图层叠加（关键）**

- **根因**：OpenRailwayMap 官方瓦片要求请求带合法 `Referer: https://www.openrailwaymap.org/`；
  **只带浏览器 UA 仍返回 403**，而两端地图页都以 `file://` 加载，页面自身没有 Referer
  → 铁路图层全部失败，并连带触发上面的误判。
- **桌面**：`desktop/cr_lbj/ui/map_host.py` 的 `_TdtRefererInterceptor` 对
  `*.openrailwaymap.org` 注入 `ORM_REFERER = 'https://www.openrailwaymap.org/'`。
  **坑**：PySide6 的 `QWebEngineUrlRequestInfo.setHttpHeader` 的 **header 名和值都必须是
  `bytes`**（`info.setHttpHeader(b'Referer', ...encode('utf-8'))`）；传 `str` 不报错也不生效，
  请求照旧无 Referer → 403（排错章节已写明）。
- **安卓**：`android/.../core/TileCache.kt` 的 `refererFor(host, tdtReferer)` 对
  `*.openrailwaymap.org` 返回同一 Referer（`host.endsWith("openrailwaymap.org") -> "https://www.openrailwaymap.org/"`），
  由原生代拉 `HttpURLConnection.setRequestProperty("Referer", …)` 补上。
- **实测**：桌面 OSM 底图 + ORM 标准图层 **16/16 瓦片全部成功**（修复前整层 403）。

**3. 失败降级**

- 铁路瓦片仍失败时页面状态行显示「铁路 ok/失败」；全部失败（`railTileFail > 4 &&
  railTileOk === 0`）时提示「铁路图层不可用：需要合法 Referer（v3.2 起客户端已内置），
  可改用本地铁路线（GeoJSON）」，底图照常显示。

**4. 铁路图层自动暂停状态（`railWanted` / `railAutoOff`）**

- 切到高德/百度（偏移坐标系）时页面把铁路图层自动置 `off`，提示改为「**铁路图层已暂停**」；
  页面用 `railWanted` / `railAutoOff` 记住「用户想要的样式」，`notifyHost()` 上报
  `railWanted` 而不是 `off`，避免宿主把自动暂停误当成用户选择关闭；切回 OSM / 天地图时
  自动恢复原样式。

### 二、信息展示（双端车次·机车·担当路局）

- **共享页面 `shared/web/railmap.html`**：
  - 标记副标题新增**车次等级**（`markerSub()` 追加 `info.grade`）；
  - 点击弹窗新增四行：**车次信息**（等级 · 担当局 · 担当段）、**车底**（配属段 · 车型）、
    **区间**（始发 → 终到）、**机车配属**（配属单位 · 制造厂），由 `infoRows()` 生成；
  - 新 API `LBJ.setTrainInfo(idOrTrain, info)`：宿主异步查询到信息后补进标记，**不改变位置**；
    参数可传对象或 JSON 字符串，返回命中的标记数；`update()` 的 `trains[]` 元素也支持
    `info` 对象，后到的非空字段与旧值浅合并；
  - `info` 字段契约：`grade` 等级 / `bureau` 担当局 / `section` 担当段 / `owner` 配属段 /
    `model` 车型 / `from`·`to` 始发终到 / `locoDepot` 机车配属单位 / `locoMaker` 制造厂 /
    `locoModel` 机车型号。
- **桌面**：
  - 新增 `desktop/cr_lbj/ui/info_lookup.py`：`TrainInfoService`（车次走 `train_info.query`
    后台线程查询并按车次缓存，信号 `infoReady`；机车走本地 `loco_roster.lookup_loco`
    同步查询，毫秒级）与 `merge_info()`；
  - 主窗口解码后由 `_decode_info()` 组装 `info` → 地图标记 + 右侧「车次信息」面板；
  - `TrainInfoPanel` 新增「车次信息」「机车配属」两行（共 13 字段）与 `setInfo()`；
  - `MapPanel.setTrainInfo()` 在后台查询结果晚到时补推；`MapHost.set_train_info()` 落到
    `window.LBJ.setTrainInfo`。
- **安卓**：
  - `MapPage` 把 `vm.trainInfos` / `vm.locoInfos`（解码页自动查询的同一份缓存）
    组装成 `info` 带进地图 payload，标记与点击弹窗即时显示；
  - `DecodePage` 当前解码卡新增「担当段 `runner`」与「区间」两行，机车配属行显示
    **机车型号 + 配属单位 + 制造厂**（`li.model` / `li.depot` / `li.maker`）。

### 三、致谢

- `README.md`「致谢」章节重写：正式致谢 **LBJ_Console**（作者 **undef-i**，GPL-3.0），
  逐项列出使用内容——`loco_roster.csv` 配属号段表、`loco_type_info.csv` 代号表、
  安卓界面骨架、OSM + OpenRailwayMap 图源方案、本地矢量铁路层思路；并补充 RailGo、
  OSM / ORM / Leaflet / 天地图 / 高德 / 百度等数据与服务致谢。
- `docs/NOTICE.md` 第 2 节补致谢段（数据、界面骨架、图源方案、离线铁路层思路）。
- 桌面「关于」对话框新增「开源致谢」段；安卓「关于」页新增致谢段。

### 四、测试与验证

- 文档同步：`README.md`、`docs/CHANGELOG.md`、`docs/地图与图源.md`、`docs/技术参考.md`、
  `docs/用户手册.md`、`docs/安卓版说明.md`、`docs/架构说明.md`、`docs/NOTICE.md`
  版本号与内容更新到 v3.2。
- 自动化：`D:\Python\Python314\python.exe -m pytest tests -q` → **90 passed**（含新增的
  v3.2 契约测试：ORM Referer、瓦片分图层统计、车次·机车信息展示）。
- 地图实测：桌面 OSM 底图 + ORM 标准图层 16/16 瓦片成功；铁路层失败不再触发
  「底图不可达」全屏提示。
- `LBJ.status()` 字段核对：`tilesTotal` / `tilesFailed` 只含底图，
  `railTilesTotal` / `railTilesFailed` 为铁路层计数。

---

## v3.1.0 · 2026-11-26

> 版本号：桌面 `cr_lbj.__version__ = 3.1.0`，安卓 `versionName = 3.1.0` / `versionCode = 310`。
> 主题：**桌面工程分目录、车次编排纯自动、地图方案定型（Leaflet + 7 底图 + 百度 BD-09 +
> 离线缓存 + QtWebEngine 修复）、安卓设置页菜单化与界面收敛、敏感地址清理。**

### 一、桌面

- **工程分目录**：`main.py`、`build.py`、`SDR_LBJ.spec`、`cr_lbj/`、`国铁.ico`、`lbj_config.json`
  全部移入 `desktop/`，与 `android/` 平级；运行/打包命令改为
  `python desktop/main.py`、`python desktop/build.py`（仓库根执行），
  `tests/`、`tools/` 与 `build.py` 的路径引用同步更新。
- **车次编排纯自动**：删除 `trainScheme` 配置与界面上的「车次规则」选择器，
  分类逻辑只按日期驱动——过渡期（2027-01-01 前）按字头 + 速度判定，**2027-01-01 起**
  高铁/普速全量按 2026 新方案，速度不再参与判定；旧配置里的 `trainScheme` 键加载时忽略。
- **地图（与安卓共用页面）**：
  - 渲染引擎**回退 Leaflet 1.9.4**（本地化 `shared/web/vendor/leaflet/`，离线可用、零构建），
    删除上一轮实验性的 WebGL 地图引擎与 `vendor/maplibre-gl/`。
  - 底图收敛为 **7 张**：**新增 4 张免 Key 底图**——高德街道/卫星（GCJ-02）、
    百度街道/卫星（BD-09）；保留 OSM 标准与天地图矢量/影像（CGCS2000，需 tk）；
    **删除** Esri、CARTO、OpenTopoMap 等 6 张国外底图。默认底图改为 `amap` 高德街道
    （2026-11-26 实测最快最稳：HTTP 200、63~279 ms，且免 Key）。
  - **百度 BD-09 自定义坐标系**：页面纯 JS 实现百度墨卡托 CRS（`L_BAIDU_CRS` +
    `ll2mc`/`mc2ll`）与百度瓦片编号换算（`BaiduTileLayer`）；切百度时重建地图实例，
    标记/轨迹自动加偏；高德/百度这类偏移坐标系底图与 WGS-84 铁路图层不能混叠，
    页面自动关闭铁路图层并提示，换回 OSM/天地图自动恢复。
  - **离线瓦片缓存**：页面图层面板「缓存本区域」（当前 zoom~zoom+3），进度经
    `LBJ.onCacheProgress` 回传、占用经 `LBJ.cacheStats` 回传；宿主实现
    `LBJHost.cacheArea` 则交给宿主落盘（安卓），否则页面降级为图片预取（桌面）。
  - **修复 QtWebEngine 远程内容拦截**：`map_host.py` 显式打开
    `WebAttribute.LocalContentCanAccessRemoteUrls`（及 `…FileUrls`）——
    QtWebEngine 默认禁止 `file://` 页面访问远程 URL，是 v3.0 桌面地图瓦片不显示的真实原因。
  - 新增两端统一的 `tdtReferer` 机制：天地图请求按白名单域名附加 `Referer`，
    百度请求固定附加 `Referer: https://map.baidu.com/`（无 Referer 会 403）；
    天地图 tk 仍为空则选中只提示、不加载。
  - 配置页/工具栏/页面下拉三处图层清单保持逐字一致（7 底图）；
    `docs/地图与图源.md` 整篇重写（图源清单、可达性实测、tk 申请、坐标系、缓存、契约、排错）。
- 删除旧版高德 Key 配置（`amapKey` / `amapSecurity`）的全部残余引用。

### 二、安卓

- **设置页菜单化**：从长表单改为「图标 + 标题 + 副标题 + 箭头」的菜单式链接列表，
  点击进入子页；取消底部保存按钮——开关/单选改完**即时保存并下发**，
  文本输入在失焦/回车/离开页面时自动保存（带防抖）；连接类参数变更自动重建 DSP 链路。
- **解码页**：收到报文后**自动查询**车次与机车配属并内联展示；手动查询并入设置页
  「查询·数据」分组，**删除底部 Dock 的「查询」页签**（Dock 收敛为五页）。
- **日志**：日志卡片改为**折叠 + 只显示最新一条**，按级别着色。
- **图标**：用桌面 `国铁.ico` 生成 launcher 图标（全密度 mipmap）。
- **删除 IQ 录制**：界面入口、录制线程、文件写出与相关权限/设置项全部移除（附对拍工具保留）。
- **地图对齐 v3.1 方案**：
  - `MAP_BASES` / `FALLBACK_LAYERS` 改为 7 张底图（高德街道/卫星、百度街道/卫星、OSM、
    天地图矢量/影像），删除 Esri/CARTO/OpenTopo 与高德旧 JS 方案残留；
  - WebView 拦截器扩展：天地图按 `tdtReferer` 加 `Referer`，百度固定
    `Referer: https://map.baidu.com/`，统一浏览器 UA；
  - **原生瓦片代拉 + 离线缓存**：`core/TileCache.kt`（DiskLruCache，`cacheDir/tile_cache`，
    上限 300 MB、LRU 淘汰），命中直接返回、未命中 `HttpURLConnection` 代拉并落盘；
    页面 `LBJHost.cacheArea` 桥接 + `LBJ.onCacheProgress` 回传；设置页显示
    「地图瓦片缓存：N 张 / X MB」并可**清除地图缓存**；
  - 地图「**转到自己位置**」：定位权限流程取最后已知位置后调 `LBJ.centerLatLng`（WGS-84）；
  - 图层状态与设置页**单一数据源**（`onLayers` 双向一致）；状态页链路指标溢出修复。

### 三、共享

- `shared/web/railmap.html` 随任务整体迁移：Leaflet 1.9.4 + `vendor/leaflet/`（本地化），
  删除 `vendor/maplibre-gl/`；`BASE_SOURCES` 7 项、`RAIL_SOURCES` 5 种 ORM 样式。
- 页面新增：三类坐标系处理（wgs/gcj/bd）、百度自定义 CRS 与瓦片编号、
  `LBJ.centerLatLng`、离线缓存（`LBJHost.cacheArea` / `LBJ.onCacheProgress` / `LBJ.cacheStats`）、
  `{key}` 天地图 tk 占位（页面不硬编码）。
- `tests/test_shared_web.py` 重写：Leaflet 本地化、7 底图 id/中文名与
  `config_ext.BASE_LAYERS` 逐字一致、百度 CRS/坐标函数、缓存与 `LBJHost` 契约、
  `tdtReferer` 机制、无旧图源残留、`node --check` 语法、文档版本 v3.1。
- `docs/`：`地图与图源.md` 整篇重写；`README.md`、`技术参考.md`、`用户手册.md`、
  `架构说明.md` 的地图章节与版本号同步到 v3.1。

### 四、安全

- **OWRX 服务器真实地址清理**：默认配置、`ReceiverSettings.kt` 默认值、`lbj_config.json`、
  对拍工具脚本、解码器 docstring 与安卓文档中的真实域名统一替换为占位
  （`127.0.0.1` / `owrx.example.com` / 「地址已略」），避免公开仓库泄露第三方服务地址。
- 仓库历史中的同一地址属于**发布前待办**（用 `git filter-repo`/`filter-branch` 重写历史并
  force push，删除仓库外含旧历史的 bundle）；**GitHub 可能短期缓存旧对象**，建议该 OWRX
  服务轮换访问凭据或限制来源。本条目只说明工作区清理已完成，历史重写以发布记录为准。
- 底图全部改为免 Key 直连（天地图 tk 由用户自备并只存本地配置），不再有内置 Key/
  签名等敏感凭据。

---

## v3.0.0 · 2026-11-26

### 一、仓库与工程统一（结构性变更）

- **安卓工程真正并入仓库**：`android/` 从原来的 junction（物理在 `C:\lbj_src`）改为
  **仓库内实体目录**，桌面端、安卓端、共享资源在同一个 Git 仓库里，一次提交两端同步。
  原"中文路径会让 CMake/Ninja 静默崩溃"的结论经实测**不成立**——真实原因是本机
  Android SDK 自带的 CMake 3.22.1/3.31.6 二进制在 Windows 10.0.26300 上配置阶段必然崩溃
  （`STATUS_STACK_BUFFER_OVERRUN`），改用 pip 版 CMake 4.4.5 并把 SDK 自带版本从
  `externalNativeBuild` 里移除后，中文路径下 `assembleDebug` 正常通过。
- 新增 **`shared/` 共享层**（桌面与安卓唯一数据来源）：
  - `shared/web/railmap.html`（Leaflet 地图页，两端共用同一份代码）
  - `shared/web/vendor/leaflet/`（Leaflet 1.9.4 本地化，离线可用，BSD-2-Clause）
  - `shared/data/loco_roster.csv`（机车配属号段表，16622 行，来自 LBJ_Console，GPL-3.0）
  - `shared/data/loco_types.csv`（176 个机车代号 → 短型号/中文名）
  - `shared/data/loco_specs.json`（45 个车型技术参数）
  - `shared/data/places.csv`（49 个预设中心）
  - `docs/NOTICE.md`（第三方授权与条款说明）
- 新增 `tools/gen_shared_data.py`（生成/校验共享数据）、`cr_lbj/data/paths.py`
  （数据目录分层：可写覆盖层 → 内置快照）、`tests/`（51 个用例）。

### 二、车次 / 机车配属查询（两端新增）

- **车次查询**：接 RailGo 公开接口（等级/担当局/客运段/配属段/车型/时刻表/开行日/交路），
  失败自动退回 12306 官方时刻表；统一结果结构，两端字段语义逐字一致。
- **机车配属查询**：新增号段表匹配（型号 + 号段闭区间），支持 `HXD1D-0123` / `韶山4-0123`
  等写法，带别名（DF4B/DF4R→DF4）、相近型号提示、歧义候选、数据来源与更新日期。
- **车型参数**：随配属结果一并展示（轴式/功率/构造速度/简介）。
- 桌面端入口：`工具 → 车次查询…`、`工具 → 机车配属查询…`，机车信息卡与记录详情直接显示配属。
- 安卓端入口：新增「查询」页（车次 / 机车配属两个页签）。

### 三、地图：铁路图源改 OpenRailwayMap，底图可选

- 铁路图层改为 **OpenRailwayMap**（standard / maxspeed / signals / electrified / gauge 五种样式）。
- 底图可选 **11 种**：OSM、CARTO（浅色/深色/路由）、Esri（卫星/街道）、OpenTopoMap、
  天地图（矢量/影像，需 tk）、高德（街道/卫星）。
- **坐标系按底图区分**：WGS-84 系底图可与 ORM 叠加（零偏移）；切到高德（GCJ-02）时
  自动关闭铁路图层（栅格无法逐块纠偏，混叠会整体错 300–500 m），并对列车点自动加偏。
- 默认中心改为「预设城市 + 经纬度」双通道（离线也能用，不再依赖高德地理编码）。
- 高德 JS API 下线：`amapKey`/`amapSecurity` **配置项整个移除**（老配置里的键加载时被忽略），
  底图全部免 Key，配置页不再有这两行。
- 地图页图层切换面板（底图/铁路样式/透明度）内嵌在页面右上角，两端一致。

### 四、安卓端界面改版

- 参考 LBJ_Console（Flutter 版）的视觉骨架重做：**悬浮玻璃胶囊 Dock**（6 页签）、
  无重顶栏（大标题 + 右侧状态胶囊）、中性灰阶 + CR 红/蓝强调色、卡片化分组、
  详情走 `ModalBottomSheet`、等宽数字。
- 六页：地图 / 解码 / 历史 / 状态 / 查询 / 设置。
- 地图页改为加载 `shared/web/railmap.html`（不再用高德 JS API），支持底图/铁路图层切换。
- 历史页支持分组（按车次号 / 按机车号）与多选删除。

### 五、第三方数据自动更新

- 配属号段表支持**自动检查更新**（默认 7 天一次，可关闭）：GitCode 镜像拉取 → 严格校验
  （行数/型号数/中文配属/畸形率）→ 原子写入用户目录 → 内置快照保留可回退。
- 桌面端：`工具 → 检查数据更新（机车配属表）`，设置里显示当前行数/更新日期/来源。
- 安卓端：设置页「数据」组显示当前数据来源与日期，可手动检查。
- 支持环境变量 `CRLBJ_DATA_DIR`（便携部署）与 `CRLBJ_DATA_SOURCE_URL`（自建镜像）。

### 六、修复的潜在问题

- 安卓 map_panel/MapPage 坐标链路：之前 Python/Kotlin 侧统一把 WGS-84 转 GCJ-02 再画，
  一旦换底图就全错；现在**坐标统一传 WGS-84**，由地图页按底图基准决定是否纠偏。
- 地图页去掉了对高德私有 API（`Marker.getZIndex` 等不存在的方法）的依赖，
  标记层改为自管 DOM 与 zIndex，避免"来车后地图不再跟随"的同类问题。
- 安卓端 `android/` 目录不再依赖 `C:\lbj_src`，换机器 clone 即可构建（`local.properties`
  需要按 `docs/安卓构建与环境.md` 生成）。
- 车次/配属查询的所有网络调用都有超时与中文错误文案，不会卡死 UI 或抛栈。
- 数据更新失败不会破坏现有数据（校验不过即丢弃 + `.bak` 回退）。
- 修复 `lbj_config.json` 模板里历史遗留的重复数据源条目说明（见架构文档）。

### 七、文档

- 新增：`docs/地图与图源.md`、`docs/车次与配属查询.md`、`docs/安卓版说明.md`、
  `docs/安卓构建与环境.md`、`docs/CHANGELOG.md`（本文件）。
- 更新：`README.md`、`docs/用户手册.md`、`docs/技术参考.md`、`docs/架构说明.md`。
- 下线：`docs/高德地图配置手册.md`（高德 JS API 已不在使用路径上）。

### 八、测试

- `python -m pytest tests -q` → 51 passed（共享数据完整性、号段匹配、别名/歧义、
  车次查询离线逻辑 + 联网用例自动跳过、地图页结构与 JS 语法、自动更新全流程、路径分层）。
- 桌面端离屏冒烟（`QT_QPA_PLATFORM=offscreen`）：主窗口构造、地图页加载与标记推送、
  查询对话框两个页签、主题切换、多档分辨率无溢出。
- 安卓：`assembleDebug` 通过 + 模拟器安装启动验收（详见 `docs/安卓版说明.md` 的验收记录）。

---

## 历史版本（v2.x 桌面端 / v3.0 安卓 M0–M3）

| 版本 | 要点 |
|---|---|
| v2.6.1 | 顶栏重排（菜单栏即顶栏）、记录详情窗口收窄、USB 直连隐藏主机端口 |
| v2.6 | 本机 USB 改 librtlsdr 直连（ctypes，零新依赖）、设备自适应参数、失败自动回退 rtl_tcp |
| v2.5 | 双屏混合 DPI 修复、源码按职责分层（`cr_lbj/` 包）、移除机车图片区域 |
| v2.4 | 迁移 Fluent Design（qfluentwidgets）、底栏重做、列统一、地图日夜联动 |
| v2.3 | 三段全景布局、即时换肤（无需重启）、运行状态仪表板分块标色 |
| v2.3.1 | 地图三项修复（跟随失效、定位点偏移、默认中心支持地名） |
| v2.2 | CR 红/蓝双主题、下段改页签、配置窗口六页惰性建页、轨迹抽稀与避让 |
| v2.1 | 布局重构、重复报文合并去重（2.5s 窗口 + 质量打分）、一站式启动、日志总线 |
| v2.0 | 经纬度解析、高德地图、多数据源、2026 车次规则 |
| 安卓 M0–M3 | 工程骨架与 JNI、C++ DSP 与对拍 0 差异、Kotlin 业务层、Room 历史库/CSV/前台服务/IQ 录制/地图页 |
