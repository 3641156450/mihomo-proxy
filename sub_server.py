#!/usr/bin/env python3
# sub_server.py - 手机订阅服务 (替代 sub_server.ps1)
# 实时读盘 sub.yaml，监听 0.0.0.0:9099（所有网卡都听，换 IP 也能应答）。
# 手机 URL：与电脑同一 WiFi 下填 http://HP-ABC:9099/sub.yaml（或 sub_server 启动时提示的当前 IP）
import http.server
import socketserver
import os
import socket
import sys

PORT = 9099
BASE = os.path.dirname(os.path.abspath(__file__))
SUB = os.path.join(BASE, "sub.yaml")


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/sub.yaml", "/") and os.path.exists(SUB):
            try:
                with open(SUB, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/yaml; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_error(500, str(e))
        else:
            self.send_error(404)

    def log_message(self, *args):
        pass  # 静默日志


class ThreadingHTTPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def lan_ips():
    """返回本机所有非环回 IPv4 地址（用于提示手机该填哪个地址）"""
    ips = []
    try:
        # 用 UDP 探测默认出口 IP（不真正发包）
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    # 再枚举网卡，补全其余网段 IP
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip != "127.0.0.1" and ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    return ips


if __name__ == "__main__":
    # 端口预检：已占用说明已有实例在跑（如保活任务拉起的），直接退出，避免重复绑定报 10048
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("0.0.0.0", PORT))
        probe.close()
    except OSError:
        print(f"端口 {PORT} 已被占用（可能已有 sub_server 实例在运行），退出。")
        sys.exit(0)
    with ThreadingHTTPServer(("0.0.0.0", PORT), Handler) as httpd:
        print(f"sub_server listening on 0.0.0.0:{PORT}  (sub.yaml={SUB})")
        ips = lan_ips()
        if ips:
            print("本机局域网地址（手机填其中与你同网段的那个）:")
            for ip in ips:
                print(f"   http://{ip}:{PORT}/sub.yaml")
        else:
            print("未能探测到局域网地址，请手动确认电脑 IP。")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
