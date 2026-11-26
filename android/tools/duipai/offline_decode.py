#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""offline_decode.py — 桌面版 Python 离线解码（对拍基准）

复用桌面版 cr_lbj 的真实实现（FrontendChain + LbjDecoder），按块处理 u8 IQ
录制文件，输出 JSONL（每行一条解码结果）。字段经 _COMPARABLE 过滤后与
C++ lbj_cli 的输出逐字段比对（compare.py）。

用法:
    python offline_decode.py capture.iq capture.params.json --out py.jsonl \
        --src E:/预警器/CR_LBJ_Receiver
"""
import argparse
import json
import os
import sys

import numpy as np


def main():
    ap = argparse.ArgumentParser(description='桌面版 Python 离线解码')
    ap.add_argument('iq', help='u8 交错 IQ 文件')
    ap.add_argument('params', help='params.json（capture_iq.py 生成）')
    ap.add_argument('--out', default='py.jsonl')
    ap.add_argument('--src', required=True, help='桌面版 CR_LBJ_Receiver 仓库根目录')
    a = ap.parse_args()

    sys.path.insert(0, os.path.join(a.src, 'desktop'))   # cr_lbj 包在 desktop/ 下
    from cr_lbj.core.decoder import (ArrivalEstimator, FrontendChain, LbjDecoder,
                                     RssiGate, BAUD_RATE)

    with open(a.params, encoding='utf-8') as f:
        p = json.load(f)

    fs = int(p['sampleRate'])
    frontend = FrontendChain(
        fs, dcOffsetHz=p.get('dcOffsetHz', 0.0), bwHz=p.get('bwKhz', 35.0) * 1000.0,
        afcEnable=p.get('afcEnable', True), afcMaxHz=p.get('afcMaxHz', 8000.0),
        afcGain=p.get('afcGain', 0.45))
    estimator = ArrivalEstimator(userKm=None, maxSeconds=360.0 * 60.0, routeKmMap={})
    decoder = LbjDecoder(frontend.actualOut, BAUD_RATE,
                         arrivalEstimator=estimator)
    gate = RssiGate(onDb=p.get('rssiThresholdDb', -55.0),
                    hysteresisDb=p.get('rssiHystDb', 3.0),
                    holdMs=p.get('rssiHoldMs', 700.0), enabled=True)
    keepAfc = p.get('keepAfcAfterPacket', False)
    block = int(p.get('blockSize', 65536))

    results = []

    def on_decode(result):
        # 与 LbjCore._onDecode 一致：补信号质量（不做去重，保持与 C++ CLI 口径一致）
        result.rssi = cur['rssi']
        result.afcHz = frontend.afc.afcHz
        result.afcErrHz = frontend.afc.lastErrHz
        result.afcScore = frontend.afc.lastScore
        results.append(result)

    decoder.onDecode = on_decode

    cur = {'rssi': -140.0}
    n_blocks = 0
    with open(a.iq, 'rb') as f:
        while True:
            raw = f.read(block * 2)
            if len(raw) < 2:
                break
            if len(raw) < block * 2:
                pad = bytes([0x7f]) * (block * 2 - len(raw))
                raw += pad
            n_blocks += 1
            x = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
            iq = ((x[0::2] - 127.5) / 128.0 + 1j * (x[1::2] - 127.5) / 128.0
                  ).astype(np.complex64)

            pcm, rssi, rxActive = frontend.process(iq, gate)
            cur['rssi'] = rssi
            if os.environ.get('LBJ_DEBUG') and n_blocks <= 3:
                print(f'[dbg] block {n_blocks} rssi={rssi:.6f} '
                      f'y[0..7]={" ".join(f"{v:.9g}" for v in pcm[:8])}', file=sys.stderr)

            if frontend.consumeAfcUpdated():
                decoder.resetDpllSoft()

            if rxActive:
                decoder.processChunk(pcm)
            elif gate.justDeactivated:
                decoder.resetReceiverState()
                if not keepAfc and frontend.afc.enabled:
                    frontend.resetAfc()

    with open(a.out, 'w', encoding='utf-8') as f:
        for r in results:
            f.write(json.dumps(r.toDict(), ensure_ascii=False, default=str) + '\n')
    print(f'[{os.path.basename(sys.argv[0])}] 处理 {n_blocks} 块，'
          f'输出 {len(results)} 条 → {a.out}')


if __name__ == '__main__':
    main()
