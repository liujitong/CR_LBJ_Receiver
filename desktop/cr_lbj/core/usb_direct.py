#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""librtlsdr 直连数据源：ctypes 薄绑定，不经 rtl_tcp、不经 TCP。

背景
----
``rtl_tcp.exe`` 只是 librtlsdr 的一个网络前端；librtlsdr 本身通过 libusb
直接访问 RTL2832U。也就是说「用 USB 棒」并不等于「必须有 TCP」——旧版
``RtlUsbSource`` 实际是「自动拉起 rtl_tcp.exe 子进程 + 连 127.0.0.1」，
多出一层本地回环 TCP、一个后台进程和一次协议握手。

本模块用 ctypes 直接调用 ``tools/rtl/rtlsdr.dll`` 的十余个导出函数：

    rtlsdr_open / close / set_sample_rate / set_center_freq
    rtlsdr_set_freq_correction / set_tuner_gain_mode / set_tuner_gain
    rtlsdr_set_agc_mode / get_tuner_gains / get_tuner_type
    rtlsdr_reset_buffer / read_async / cancel_async

不引入新依赖（不用 pyrtlsdr：0.5.x 需要随包 dll 里没有的
``rtlsdr_set_dithering``，0.2.x 又依赖 Python 3.14 已移除的 pkg_resources）。

对外接口与 ``RtlTcpSource`` 完全一致（``open`` / ``read`` / ``close`` /
``getDiagnostics``），``LbjCore`` 只需在构造数据源时换一个类名。
"""
from __future__ import annotations

import os
import ctypes
import threading
import queue
import time
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from cr_lbj.core.rtl_paths import findRtlsdrDll, find_rtl_tool, runtime_dirs
from cr_lbj.core.source_stats import recordBlock, buildDiagnostics

# librtlsdr 的 tuner 枚举顺序（rtl-sdr.h: enum rtlsdr_tuner）
TUNER_NAMES = {
    0: 'Unknown', 1: 'E4000', 2: 'FC0012', 3: 'FC0013',
    4: 'FC2580', 5: 'R820T', 6: 'R828D',
}

#: libusb 传输块个数：内部环形缓冲。太小会丢块，太大增加延迟。
DEFAULT_BUFFERS = 15

#: 单次 USB 读取回调的字节数 = blockSize * 2（uint8 交错的 I/Q）
_BYTES_PER_SAMPLE = 2


class RtlSdrError(RuntimeError):
    """librtlsdr 调用失败（dll 缺失、设备未插、被占用等）。"""


# ===========================================================================
# DLL 加载与函数签名
# ===========================================================================
_DLL_LOCK = threading.Lock()
_dll: Optional[ctypes.CDLL] = None
_dllHandle = None          # os.add_dll_directory 的句柄，必须保持存活
_readCbType = ctypes.CFUNCTYPE(None, ctypes.POINTER(ctypes.c_ubyte),
                               ctypes.c_uint32, ctypes.c_void_p)


def _bind(dll: ctypes.CDLL) -> ctypes.CDLL:
    """声明导出函数的参数/返回类型。缺函数说明 dll 版本过旧，直接报错。"""
    u32, i32 = ctypes.c_uint32, ctypes.c_int
    pdev = ctypes.c_void_p
    try:
        dll.rtlsdr_get_device_count.restype = u32
        dll.rtlsdr_get_device_count.argtypes = []
        dll.rtlsdr_get_device_name.restype = ctypes.c_char_p
        dll.rtlsdr_get_device_name.argtypes = [u32]
        dll.rtlsdr_get_device_usb_strings.restype = i32
        dll.rtlsdr_get_device_usb_strings.argtypes = [
            u32, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]
        dll.rtlsdr_open.restype = i32
        dll.rtlsdr_open.argtypes = [ctypes.POINTER(pdev), u32]
        dll.rtlsdr_close.restype = i32
        dll.rtlsdr_close.argtypes = [pdev]
        dll.rtlsdr_set_sample_rate.restype = i32
        dll.rtlsdr_set_sample_rate.argtypes = [pdev, u32]
        dll.rtlsdr_get_sample_rate.restype = u32
        dll.rtlsdr_get_sample_rate.argtypes = [pdev]
        dll.rtlsdr_set_center_freq.restype = i32
        dll.rtlsdr_set_center_freq.argtypes = [pdev, u32]
        dll.rtlsdr_get_center_freq.restype = u32
        dll.rtlsdr_get_center_freq.argtypes = [pdev]
        dll.rtlsdr_set_freq_correction.restype = i32
        dll.rtlsdr_set_freq_correction.argtypes = [pdev, i32]
        dll.rtlsdr_get_tuner_type.restype = i32
        dll.rtlsdr_get_tuner_type.argtypes = [pdev]
        dll.rtlsdr_get_tuner_gains.restype = i32
        dll.rtlsdr_get_tuner_gains.argtypes = [pdev, ctypes.POINTER(i32)]
        dll.rtlsdr_set_tuner_gain_mode.restype = i32
        dll.rtlsdr_set_tuner_gain_mode.argtypes = [pdev, i32]
        dll.rtlsdr_set_tuner_gain.restype = i32
        dll.rtlsdr_set_tuner_gain.argtypes = [pdev, i32]
        dll.rtlsdr_set_agc_mode.restype = i32
        dll.rtlsdr_set_agc_mode.argtypes = [pdev, i32]
        dll.rtlsdr_reset_buffer.restype = i32
        dll.rtlsdr_reset_buffer.argtypes = [pdev]
        dll.rtlsdr_read_async.restype = i32
        dll.rtlsdr_read_async.argtypes = [pdev, _readCbType, ctypes.c_void_p, u32, u32]
        dll.rtlsdr_cancel_async.restype = i32
        dll.rtlsdr_cancel_async.argtypes = [pdev]
    except AttributeError as e:
        raise RtlSdrError(f'rtlsdr.dll 版本过旧，缺少导出函数 {e}') from e
    return dll


def loadDll() -> ctypes.CDLL:
    """加载并缓存 librtlsdr 动态库；找不到便抛 RtlSdrError。"""
    global _dll, _dllHandle
    with _DLL_LOCK:
        if _dll is not None:
            return _dll
        path = findRtlsdrDll()
        if not path:
            dirs = '、'.join(runtime_dirs()[:3])
            raise RtlSdrError(
                '未找到 rtlsdr.dll（USB 直连需要它，随程序放在 tools/rtl/）。'
                f'已搜索: {dirs}')
        folder = os.path.dirname(os.path.abspath(path))
        try:
            # dll 依赖同目录的 msvcr100.dll / pthreadVC2.dll，先把目录加入搜索
            if hasattr(os, 'add_dll_directory'):
                _dllHandle = os.add_dll_directory(folder)
            os.environ['PATH'] = folder + os.pathsep + os.environ.get('PATH', '')
            _dll = _bind(ctypes.CDLL(path))
        except OSError as e:
            raise RtlSdrError(f'rtlsdr.dll 加载失败（{e}）。'
                              '常见原因：与 Python 位数不符（需同为 64 位）'
                              '或缺少 VC 运行库。') from e
        return _dll


def dllPath() -> str:
    """当前使用的 rtlsdr.dll 路径（供界面/日志显示）。"""
    return findRtlsdrDll() or ''


def _openHint(rc: int) -> str:
    """把 rtlsdr_open 的返回码翻译成可操作的提示。"""
    if rc == -1:
        return '未找到该序号的设备（检查 USB 连接）'
    if rc == -2:
        return '无法打开设备（驱动缺失：用 Zadig 安装 WinUSB，或被其他程序占用）'
    if rc == -3:
        return '设备已被其他程序占用（先关闭 rtl_tcp / SDR# 等）'
    return '未知错误'


# ===========================================================================
# 设备枚举与参数推荐
# ===========================================================================
def listDevices() -> List[Dict[str, Any]]:
    """枚举已插入的 RTL-SDR（不打开设备，不占用）。

    返回每项: index / name / manufacturer / product / serial。
    """
    dll = loadDll()
    count = int(dll.rtlsdr_get_device_count())
    out: List[Dict[str, Any]] = []
    for i in range(count):
        name = (dll.rtlsdr_get_device_name(i) or b'').decode('utf-8', 'replace')
        man = ctypes.create_string_buffer(256)
        prod = ctypes.create_string_buffer(256)
        ser = ctypes.create_string_buffer(256)
        rc = dll.rtlsdr_get_device_usb_strings(i, man, prod, ser)
        out.append({
            'index': i,
            'name': name or 'Generic RTL2832U',
            'manufacturer': man.value.decode('utf-8', 'replace') if rc == 0 else '',
            'product': prod.value.decode('utf-8', 'replace') if rc == 0 else '',
            'serial': ser.value.decode('utf-8', 'replace') if rc == 0 else '',
        })
    return out


def _readGains(dll: ctypes.CDLL, dev) -> List[float]:
    """读取当前 tuner 支持的增益表（dB）。设备关闭后调用会失败，故在使用中读。"""
    n = int(dll.rtlsdr_get_tuner_gains(dev, None))
    if n <= 0:
        return []
    buf = (ctypes.c_int * n)()
    n = int(dll.rtlsdr_get_tuner_gains(dev, buf))
    if n <= 0:
        return []
    return [round(buf[i] / 10.0, 1) for i in range(n)]


def probeDevice(index: int = 0) -> Dict[str, Any]:
    """打开指定设备读 tuner 型号与可用增益，随后关闭。设备被占用会抛错。"""
    dll = loadDll()
    dev = ctypes.c_void_p()
    rc = int(dll.rtlsdr_open(ctypes.byref(dev), int(index)))
    if rc != 0:
        raise RtlSdrError(f'rtlsdr_open({index}) 失败，返回 {rc}：{_openHint(rc)}')
    try:
        tunerType = int(dll.rtlsdr_get_tuner_type(dev))
        gains = _readGains(dll, dev)
    finally:
        dll.rtlsdr_close(dev)
    name = TUNER_NAMES.get(tunerType, f'未知({tunerType})')
    return {'index': int(index), 'tunerType': tunerType,
            'tuner': name, 'gains': gains}


def recommendProfile(tunerType: int, deviceName: str = '') -> Dict[str, Any]:
    """按 tuner 型号给出射频参数建议。

    依据（三处独立来源互相印证，见 docs/USB直连与设备自适应.md）：
      - 采样率 960 kS/s：本项目 DSP 链路（半带 2 级 → 240 kS/s）的甜点，
        再高只会白烧 USB 带宽；
      - 手动增益、关闭 AGC：LBJ 是突发窄带信号，AGC 会把噪声一起抬起来，
        Sdr-Is-Fun 与 LBJReceiver 都明确关掉 AGC；
      - DC 偏移 50 kHz：避开零频直流与 1/f 噪声，DDC 后再落回目标频点。
    """
    tuner = TUNER_NAMES.get(tunerType, 'Unknown')
    if tuner == 'R828D':
        gain, note = 15.7, ('R828D（多为 RTL-SDR Blog V4）：从 15.7 dB 起调，'
                            '欠载再上调；osmocom 版库可能报 tuner 错误，'
                            '建议换 rtl-sdr-blog 版 librtlsdr')
    elif tuner in ('R820T', 'R820T2'):
        gain, note = 19.7, 'R820T/R820T2：LBJ 实测 19.7 dB 手动增益最稳，务必关 AGC'
    elif tuner == 'E4000':
        gain, note = 19.7, ('E4000：增益表与 R820T 不同，会按设备实际增益表就近取；'
                            '821 MHz 已接近其上限，灵敏度偏低')
    elif tuner in ('FC0012', 'FC0013'):
        gain, note = 19.7, f'{tuner}：廉价 tuner，增益档位粗，按设备增益表就近取'
    else:
        gain, note = 15.7, '未识别 tuner，用保守参数'
    return {
        'sampleRate': 960000,
        'gainDb': gain,
        'dcOffsetHz': 50000.0,
        'blockSize': 65536,
        'agc': False,
        'tunerType': tunerType,
        'tuner': tuner,
        'deviceName': deviceName,
        'note': note,
    }


def probeDevices() -> Dict[str, Any]:
    """一次性检测：枚举设备 + 探测 tuner + 生成推荐参数。

    返回 {'ok', 'devices', 'profiles', 'text'}。设备为空时 ok=False，
    text 里说明原因（未插 / 驱动缺失 / dll 缺失）。
    """
    try:
        devs = listDevices()
    except RtlSdrError as e:
        return {'ok': False, 'devices': [], 'profiles': [], 'text': str(e)}
    if not devs:
        return {
            'ok': False, 'devices': [], 'profiles': [],
            'text': ('librtlsdr 未发现设备（rtlsdr_get_device_count = 0）。\n'
                     '· 确认 USB 棒已插好、指示灯亮；\n'
                     '· Windows 需用 Zadig 给 Bulk-In Interface 装 WinUSB 驱动；\n'
                     '· 设备若被 rtl_tcp / SDR# 占用会连枚举都看不到。'),
        }
    profiles = []
    lines = [f'rtlsdr.dll: {dllPath()}', '']
    for d in devs:
        line = (f"[{d['index']}] {d['name']}"
                + (f"  序列号 {d['serial']}" if d['serial'] else ''))
        try:
            info = probeDevice(d['index'])
            prof = recommendProfile(info['tunerType'], d['name'])
            prof['index'] = d['index']
            prof['gains'] = info['gains']
            profiles.append(prof)
            line += f"\n    tuner: {info['tuner']}   可用增益: {len(info['gains'])} 档"
            line += (f"\n    推荐: {prof['sampleRate'] // 1000} kS/s, "
                     f"{prof['gainDb']} dB 手动, AGC 关, DC 偏移 "
                     f"{int(prof['dcOffsetHz'])} Hz\n    说明: {prof['note']}")
        except RtlSdrError as e:
            line += f'\n    打开失败: {e}'
        lines.append(line)
    return {'ok': True, 'devices': devs, 'profiles': profiles,
            'text': '\n'.join(lines)}


# ===========================================================================
# 数据源
# ===========================================================================
class RtlSdrDirectSource:
    """librtlsdr 直连数据源。

    读取方式：``rtlsdr_read_async`` 在独立线程里阻塞收块，每块由 libusb
    回调转成 complex64 推进队列；``read()`` 从队列取，与 rtl_tcp 源一致。
    断流（拔插、供电不足）时自动 close → 1 秒后重开设备并继续。
    """

    #: 传输方式标识，界面用来区分直连与中转
    transport = 'usb'

    def __init__(self, freqHz: float, sampleRate: int, blockSize: int,
                 dcOffsetHz: float = 0.0, gainDb: float = 15.7, ppm: float = 1,
                 deviceIndex: int = 0, buffers: int = DEFAULT_BUFFERS):
        self.targetFreqHz = float(freqHz)   # 用户目标接收频率
        self.freqHz = float(freqHz)         # 硬件实际调谐频率（扣掉 DC 偏移）
        self.sampleRate = int(sampleRate)
        self.blockSize = int(blockSize)
        self.dcOffsetHz = float(dcOffsetHz)
        self.gainDb = float(gainDb)
        self.ppm = float(ppm)
        self.deviceIndex = int(deviceIndex or 0)
        self.buffers = int(buffers)
        self.actualSampleRate = 0
        self.appliedGainDb = float(gainDb)
        self.tunerName = ''

        self.queue: queue.Queue = queue.Queue(maxsize=60)
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.lastError: Optional[str] = None

        # 与 RtlTcpSource 同口径的统计字段（source_stats 依赖这些名字）
        self.blockCount = 0
        self.bytesRecv = 0
        self.reconnectCount = 0
        self.droppedBlocks = 0
        self.lastBlockTime = 0.0
        self.blockIntervals: List[float] = []
        self.blockSizes: List[int] = []
        self.connectTime = 0.0
        self.lastRtt = 0.0

        self._dll: Optional[ctypes.CDLL] = None
        self._dev = None
        self._cb = None          # 回调对象必须常驻，否则被 GC 后回调野指针
        self.onLog: Optional[Callable[[str], None]] = None

    # ---- 设备生命周期 ----
    def _log(self, msg: str):
        if self.onLog:
            try:
                self.onLog(msg)
            except Exception:
                pass

    def _openDevice(self):
        """打开设备并下发全部射频参数；失败抛 RtlSdrError。"""
        dll = loadDll()
        self._dll = dll
        dev = ctypes.c_void_p()
        rc = int(dll.rtlsdr_open(ctypes.byref(dev), self.deviceIndex))
        if rc != 0:
            raise RtlSdrError(
                f'rtlsdr_open({self.deviceIndex}) 失败，返回 {rc}：{_openHint(rc)}')
        self._dev = dev
        try:
            self._configure()
        except Exception:
            # 配置失败必须把设备还回去，否则上层回退到 rtl_tcp 时会打不开
            self._closeDevice()
            raise

    def _configure(self):
        d = self._dll
        dev = self._dev
        d.rtlsdr_set_sample_rate(dev, self.sampleRate)
        self.actualSampleRate = int(d.rtlsdr_get_sample_rate(dev))
        hwFreq = int(round(self.targetFreqHz - self.dcOffsetHz))
        d.rtlsdr_set_center_freq(dev, hwFreq)
        self.freqHz = float(d.rtlsdr_get_center_freq(dev))
        if self.ppm:
            # 与 rtl_tcp 同序：设完频率再下发 ppm，librtlsdr 会自己重调谐一次。
            # 返回 -2 表示「还没设过频率」，此处已有频率，忽略返回值即可。
            d.rtlsdr_set_freq_correction(dev, int(self.ppm))
        self.tunerName = TUNER_NAMES.get(int(d.rtlsdr_get_tuner_type(dev)), 'Unknown')
        # 手动增益 + 关 AGC：突发窄带信号不能被 AGC 拉平
        d.rtlsdr_set_tuner_gain_mode(dev, 1)
        gains = _readGains(d, dev)
        want = self.gainDb
        if gains:
            want = min(gains, key=lambda x: abs(x - self.gainDb))
        self.appliedGainDb = float(want)
        d.rtlsdr_set_tuner_gain(dev, int(round(want * 10)))
        d.rtlsdr_set_agc_mode(dev, 0)
        d.rtlsdr_reset_buffer(dev)

    def _closeDevice(self):
        if self._dev is not None and self._dll is not None:
            try:
                self._dll.rtlsdr_close(self._dev)
            except Exception:
                pass
        self._dev = None

    # ---- 数据回调 ----
    def _onSamples(self, buf, length, _ctx):
        """libusb 回调：uint8 交错 I/Q → complex64 入队。

        回调跑在 libusb 事件线程，只做必要的转换与入队，绝不做解码。
        """
        if not self.running or not length:
            return
        try:
            n = int(length)
            raw = np.ctypeslib.as_array(buf, shape=(n,)).astype(np.float32)
            iq = ((raw[0::2] - 127.5) / 128.0
                  + 1j * (raw[1::2] - 127.5) / 128.0).astype(np.complex64)
            recordBlock(self, len(iq), n)
            try:
                self.queue.put_nowait(iq)
            except queue.Full:
                self.droppedBlocks += 1   # 队列满就丢，回调里不能阻塞
        except Exception as e:            # 回调里不能抛，否则会打断 libusb
            self.lastError = f'USB 回调异常: {e}'

    def _asyncTask(self):
        """常驻线程：read_async 阻塞收流，断流后重开设备。"""
        while self.running:
            if self._dev is None:            # 首次进入或上次重连失败
                try:
                    self._openDevice()
                    self.connectTime = time.time()
                    self.lastBlockTime = 0.0
                    self.lastError = None
                    if self.reconnectCount:
                        self._log(f'[USB] 设备已重连（第 {self.reconnectCount} 次）')
                except Exception as e:
                    self.lastError = f'USB 重连失败: {e}，1 秒后重试...'
                    time.sleep(1.0)
                    continue
            try:
                self._cb = _readCbType(self._onSamples)
                self._dll.rtlsdr_reset_buffer(self._dev)
                rc = int(self._dll.rtlsdr_read_async(
                    self._dev, self._cb, None, self.buffers,
                    self.blockSize * _BYTES_PER_SAMPLE))
                if not self.running:
                    break
                self.lastError = f'USB 数据流中断（返回 {rc}），1 秒后重连...'
            except Exception as e:
                if not self.running:
                    break
                self.lastError = f'USB 读取异常: {e}，1 秒后重连...'
            self.reconnectCount += 1
            self._closeDevice()
            if not self.running:
                break
            time.sleep(1.0)

    # ---- 与 RtlTcpSource 一致的对外接口 ----
    def open(self):
        """打开设备并启动接收线程。设备打不开会直接抛错（便于上层回退）。"""
        self._openDevice()
        self.running = True
        self.connectTime = time.time()
        self.lastError = None
        self._cb = _readCbType(self._onSamples)
        self.thread = threading.Thread(target=self._asyncTask, daemon=True)
        self.thread.start()
        self._log(f'[USB] {self.tunerName} #{self.deviceIndex} '
                  f'采样率 {self.actualSampleRate // 1000}k '
                  f'增益 {self.appliedGainDb:.1f} dB '
                  f'调谐 {self.freqHz / 1e6:.4f} MHz（直连，无 rtl_tcp）')

    def read(self, timeout: float = 30.0) -> np.ndarray:
        """读取一块 IQ 数据。超时或出错抛 RuntimeError（与 TCP 源一致）。"""
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
        """停止接收并关闭设备。

        顺序不能反：先 cancel_async 让 read_async 返回，再等线程退出，最后
        rtlsdr_close。若线程卡在 libusb 里超过 3 秒（拔棒时偶发），宁可跳过
        close 也不要在 read_async 还在跑时释放设备——那会直接崩溃。
        """
        self.running = False
        if self._dev is not None and self._dll is not None:
            try:
                self._dll.rtlsdr_cancel_async(self._dev)  # 让 read_async 返回
            except Exception:
                pass
        if self.thread:
            self.thread.join(timeout=3)
            if self.thread.is_alive():
                self._log('[USB] 读取线程 3 秒内未退出，跳过关闭设备（进程退出时回收）')
                self.thread = None
                return
            self.thread = None
        self._closeDevice()

    def getDiagnostics(self) -> Dict[str, Any]:
        """诊断数据快照（字段与 RtlTcpSource.getDiagnostics 一致）。"""
        return buildDiagnostics(self, 'usb')
