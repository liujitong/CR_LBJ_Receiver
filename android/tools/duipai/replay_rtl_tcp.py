#!/usr/bin/env python3
"""本地 rtl_tcp 回放服务器：把 capture_960k.iq 按 rtl_tcp 协议无限循环播放。

用途：App 级解码事件流验证（模拟器内 10.0.2.2:5678 直连本机回放），
不必依赖 OWRX 实时信号。协议与 capture_iq.py 对应：
  连接 → 发 12 字节头 → 收 5 字节命令（忽略）→ 循环发 IQ 原始字节。
"""
import socket
import socketserver
import sys
import threading
import time

IQ_PATH = r"C:\lbj_src\tools\duipai\capture_960k.iq"
PORT = 5678
CHUNK = 32768

class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        print(f"[replay] client connected: {self.client_address}", flush=True)
        # 12 字节握手头：magic + tuner type + gain count
        self.request.sendall(b"RTL0" + (3).to_bytes(4, "big") + (0).to_bytes(4, "big"))
        # 读命令直到出现数据请求节奏（rtl_tcp 命令为 5 字节）
        self.request.settimeout(0.5)
        try:
            while True:
                self.request.recv(4096)
        except socket.timeout:
            pass

        data = open(IQ_PATH, "rb").read()
        print(f"[replay] loaded {len(data)} bytes, looping", flush=True)
        self.request.settimeout(None)
        try:
            while True:
                for off in range(0, len(data) - CHUNK, CHUNK):
                    self.request.sendall(data[off:off + CHUNK])
                time.sleep(0.5)
        except (BrokenPipeError, ConnectionResetError, OSError):
            print("[replay] client disconnected", flush=True)

class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

if __name__ == "__main__":
    print(f"[replay] listening on 0.0.0.0:{PORT}, IQ={IQ_PATH}", flush=True)
    Server(("0.0.0.0", PORT), Handler).serve_forever()
