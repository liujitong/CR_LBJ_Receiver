#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""capture_iq.py — rtl_tcp/OWRX IQ 抓流器（对拍输入）

连接 rtl_tcp 协议服务（OWRX 转发或本机 rtl_tcp），握手后下发配置命令，
抓取指定秒数的 uint8 交错 IQ 到文件，同时生成 lbj_cli / offline_decode.py
共用的 params.json（与 Android nativeInit 同名字段）。

用法:
    python capture_iq.py --host nc.example.com --port 5678 --seconds 300 \
        --out capture.iq
"""
import argparse
import json
import socket
import struct
import sys
import time

CMD_SET_FREQ = 1
CMD_SET_SAMPLERATE = 2
CMD_SET_GAINMODE = 3
CMD_SET_GAIN = 4
CMD_SET_FREQCORR = 5
CMD_SET_AGC = 8


def main():
    ap = argparse.ArgumentParser(description='rtl_tcp IQ 抓流器')
    ap.add_argument('--host', default='nc.example.com')
    ap.add_argument('--port', type=int, default=5678)
    ap.add_argument('--freq-mhz', type=float, default=821.2375)
    ap.add_argument('--sr', type=int, default=960000, help='采样率 Hz（OWRX 960k / USB 240k）')
    ap.add_argument('--gain', type=float, default=15.7)
    ap.add_argument('--ppm', type=float, default=1.0)
    ap.add_argument('--dc-offset', type=float, default=0.0,
                    help='DDC 偏移 Hz（OWRX=0，USB=50000）')
    ap.add_argument('--bw-khz', type=float, default=35.0)
    ap.add_argument('--block-size', type=int, default=65536)
    ap.add_argument('--seconds', type=float, default=300.0)
    ap.add_argument('--out', default='capture.iq', help='IQ 输出路径（同时写 params.json）')
    a = ap.parse_args()

    print(f'连接 {a.host}:{a.port} ...')
    sock = socket.create_connection((a.host, a.port), timeout=15)
    sock.settimeout(15)

    # 12 字节握手头（RTL0 + tuner 类型 + 增益 + 频率 + 采样率）
    hdr = b''
    while len(hdr) < 12:
        buf = sock.recv(12 - len(hdr))
        if not buf:
            sys.exit('握手阶段连接断开')
        hdr += buf
    print(f'握手头: {hdr[:4]!r} {hdr[4:].hex()}')

    def cmd(cid, param):
        sock.sendall(struct.pack('>BI', cid, param & 0xFFFFFFFF))

    cmd(CMD_SET_FREQ, int(a.freq_mhz * 1e6 - a.dc_offset))
    cmd(CMD_SET_SAMPLERATE, a.sr)
    cmd(CMD_SET_GAINMODE, 1)
    cmd(CMD_SET_GAIN, int(a.gain * 10))
    cmd(CMD_SET_FREQCORR, int(a.ppm))
    cmd(CMD_SET_AGC, 0)

    need_bytes = int(a.sr * 2 * a.seconds)
    chunk = a.block_size * 2
    sock.settimeout(10)
    got = 0
    t0 = time.time()
    with open(a.out, 'wb') as f:
        while got < need_bytes:
            try:
                data = sock.recv(min(chunk, need_bytes - got))
            except socket.timeout:
                print(f'\n[警告] 接收超时，已抓 {got / 2 / a.sr:.1f}s')
                break
            if not data:
                print(f'\n[警告] 服务端断开，已抓 {got / 2 / a.sr:.1f}s')
                break
            f.write(data)
            got += len(data)
            el = time.time() - t0
            print(f'\r{got / 2 / a.sr:7.1f}s / {a.seconds:.0f}s  '
                  f'{got / 1e6:7.1f}MB  实时率 {got / 2 / a.sr / el * 100:5.1f}%',
                  end='', flush=True)
    sock.close()
    print(f'\n已保存 {a.out}（{got} 字节 ≈ {got / 2 / a.sr:.1f}s @ {a.sr} S/s）')

    # 与 nativeInit / lbj_cli / offline_decode.py 共用的参数文件
    params = {
        'freqMhz': a.freq_mhz,
        'sampleRate': a.sr,
        'bwKhz': a.bw_khz,
        'dcOffsetHz': a.dc_offset,
        'userOffsetHz': 0.0,
        'gainDb': a.gain,
        'ppm': a.ppm,
        'blockSize': a.block_size,
        'rssiThresholdDb': -55.0,
        'rssiHystDb': 3.0,
        'rssiHoldMs': 700.0,
        'afcEnable': True,
        'afcMaxHz': 8000.0,
        'afcGain': 0.45,
        'keepAfcAfterPacket': False,
        'baudRate': 1200.0,
        'trainScheme': 'auto',
    }
    params_path = a.out.rsplit('.', 1)[0] + '.params.json'
    with open(params_path, 'w', encoding='utf-8') as f:
        json.dump(params, f, ensure_ascii=False, indent=2)
    print(f'已保存 {params_path}')


if __name__ == '__main__':
    main()
