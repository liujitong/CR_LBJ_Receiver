#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_classifier_vectors.py — 车次分类双端 1:1 测试向量生成器（任务11）

以桌面 Python classifyTrainCategory 为基准，对覆盖性向量组（各前缀 × 速度档 ×
日期档，≥60 条）生成期望输出，写出：
  1. android/app/src/test/java/xyz/mlxkj/crlbj/engine/TrainClassifierTest.kt
     （向量+期望值内联；本阶段不运行，lead 集成时用 tools/test.ps1 跑）
  2. classifier_vectors.json（本目录；tests/test_decoder_scheme.py 消费同一组向量）

日期档取 UTC+8 正午时刻（远离午夜切换边界），故向量不随测试机时区漂移；
nowMs 为该时刻的 epoch 毫秒，安卓 TrainClassifier.classify 第 4 参注入。

用法:
    python gen_classifier_vectors.py --src E:/预警器/CR_LBJ_Receiver
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

TZ8 = timezone(timedelta(hours=8))

# 日期档（UTC+8 墙上时间，naive 语义与桌面一致）
BEFORE = datetime(2026, 11, 26, 12, 0, 0)   # 过渡期
MID = datetime(2026, 12, 26, 12, 0, 0)      # 旧切换日(2026-12-25)之后、新切换日之前
AFTER = datetime(2027, 1, 2, 12, 0, 0)      # 2027-01-01 之后


def build_vectors():
    """返回 [(train, isDetailed, speed, now_naive)]，speed 为 None 或字符串。"""
    vs = []
    # T/K/X：新旧含义冲突前缀 × 速度档（含缺失/无效/边界 199/200/后缀）× 日期档
    tkx_speeds = [None, '0', '80', '140', '199', '200', '250', '300',
                  '350', '500', '501', '---', '80km/h']
    for train in ('T398', 'K19533', 'X101'):
        for spd in tkx_speeds:
            for now in (BEFORE, AFTER):
                vs.append((train, False, spd, now))
        vs.append((train, False, None, MID))   # 速度缺失回退日期已统一 2027-01-01
    # 含义稳定前缀：与速度/日期无关，一律新版
    for train in ('G1234', 'D123', 'C12', 'S1', 'Z123', 'N123'):
        for now in (BEFORE, AFTER):
            vs.append((train, False, None, now))
    vs.append(('G1234', False, '80', BEFORE))  # 低速也不影响稳定前缀
    vs.append(('G1234', False, '80', AFTER))
    # V/Y/B/DH/DJ 数字区段
    for train in ('V6001', 'V7001', 'V3000', 'Y500', 'Y1500',
                  'B100', 'B2001', 'B9001', 'B5000',
                  'DH500', 'DH1500', 'DJ1'):
        for now in (BEFORE, AFTER):
            vs.append((train, False, None, now))
    # 纯数字：货运区段（含新旧表差异段 71001/73001/75001）、回送、客车兜底
    for train in ('50001', '71001', '73001', '75001', '00123', '00050', '00500'):
        for now in (BEFORE, AFTER):
            vs.append((train, False, None, now))
    for detailed in (False, True):
        for now in (BEFORE, AFTER):
            vs.append(('1234', detailed, None, now))
    # 未知字母前缀 → 数字兜底
    for now in (BEFORE, AFTER):
        vs.append(('Q123', False, None, now))
    # 规范化：小写 / 空格
    vs.append(('g7', False, None, BEFORE))
    vs.append(('g7', False, None, AFTER))
    vs.append((' T 398 ', False, None, BEFORE))
    vs.append((' T 398 ', False, None, AFTER))
    # 占位车次
    for train in ('', '----', '等待信号...'):
        vs.append((train, False, None, BEFORE))
    return vs


def kt_str(s):
    assert '"' not in s and '\\' not in s, f'需要转义: {s!r}'
    return '"' + s + '"'


def main():
    ap = argparse.ArgumentParser(description='车次分类双端 1:1 向量生成器')
    ap.add_argument('--src', required=True, help='CR_LBJ_Receiver 仓库根目录')
    a = ap.parse_args()
    sys.path.insert(0, os.path.join(a.src, 'desktop'))
    from cr_lbj.core.decoder import classifyTrainCategory  # noqa: E402

    vectors = build_vectors()
    assert len(vectors) >= 60, f'向量不足 60 条: {len(vectors)}'
    rows = []
    for train, detailed, speed, now in vectors:
        expected = classifyTrainCategory(train, detailed, speed=speed, now=now)
        now_ms = int(now.replace(tzinfo=TZ8).timestamp() * 1000)
        rows.append({'train': train, 'detailed': detailed, 'speed': speed,
                     'nowMs': now_ms, 'expected': expected})

    here = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(here, 'classifier_vectors.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)

    kt_lines = ',\n'.join(
        '            V(%s, %s, %s, %dL, %s)' % (
            kt_str(r['train']), 'true' if r['detailed'] else 'false',
            'null' if r['speed'] is None else kt_str(r['speed']),
            r['nowMs'], kt_str(r['expected']))
        for r in rows)
    kt = '''package xyz.mlxkj.crlbj.engine

import org.junit.Assert.assertEquals
import org.junit.Test
import java.time.LocalDate
import java.time.ZoneId

/**
 * TrainClassifier ↔ 桌面 classifyTrainCategory 双端 1:1 回归（任务11）。
 *
 * 向量与期望值由桌面 Python 基准生成（%d 条，各前缀 × 速度档 × 日期档）：
 *   android/tools/duipai/gen_classifier_vectors.py --src <仓库根>
 * 请勿手改期望值；规则变更后重新生成，并用 tools/test.ps1 运行。
 * nowMs 为对应 UTC+8 墙上时刻的 epoch 毫秒（正午时刻，不随测试机时区漂移）；
 * 在 +08 设备上与桌面 naive 本地 datetime 语义等价。
 */
class TrainClassifierTest {

    private data class V(
        val train: String, val detailed: Boolean, val speed: String?,
        val nowMs: Long, val expected: String,
    )

    /** 覆盖性向量：安卓输出必须与 Python 期望值逐条完全一致 */
    @Test
    fun vectorsMatchPython() {
        for (v in VECTORS) {
            assertEquals(
                "train=${v.train} detailed=${v.detailed} speed=${v.speed} nowMs=${v.nowMs}",
                v.expected,
                TrainClassifier.classify(v.train, v.detailed, v.speed, v.nowMs))
        }
    }

    /** 切换边界：设备本地 2027-01-01 00:00（与实现同表达式，任何时区自洽） */
    @Test
    fun switchBoundary() {
        val boundary = LocalDate.of(2027, 1, 1)
            .atStartOfDay(ZoneId.systemDefault()).toInstant().toEpochMilli()
        // 边界前一毫秒：过渡期，T/K/X 速度缺失按旧版兜底
        assertEquals("特快旅客列车",
            TrainClassifier.classify("T398", false, null, boundary - 1))
        // 边界起（>=）：全量新版，高铁+普速一律不看速度
        assertEquals("特快动车组 (300km/h)",
            TrainClassifier.classify("T398", false, null, boundary))
        assertEquals("快速动车组 (200~250km/h)",
            TrainClassifier.classify("K19533", false, "80", boundary))
        assertEquals("新时速动车组 (350km/h+)",
            TrainClassifier.classify("X101", false, "0", boundary))
    }

    /** 默认时钟参数：省略 nowMs 等价于注入当前时间（稳定前缀与日期无关） */
    @Test
    fun defaultClock() {
        val now = System.currentTimeMillis()
        assertEquals(TrainClassifier.classify("G1234", false, null, now),
            TrainClassifier.classify("G1234", false, null))
    }

    companion object {
        private val VECTORS = arrayOf(
%s
        )
    }
}
''' % (len(rows), kt_lines)
    kt_path = os.path.join(a.src, 'android', 'app', 'src', 'test', 'java',
                           'xyz', 'mlxkj', 'crlbj', 'engine', 'TrainClassifierTest.kt')
    os.makedirs(os.path.dirname(kt_path), exist_ok=True)
    with open(kt_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(kt)
    print(f'向量 {len(rows)} 条 → {kt_path}')
    print(f'同组向量 JSON → {json_path}')


if __name__ == '__main__':
    main()
