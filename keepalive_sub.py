# -*- coding: utf-8 -*-
"""9099 手机订阅服务保活：端口在跑就静默退出，不在跑就无窗口拉起 sub_server.py"""
import os
import socket
import subprocess
import sys

PORT = 9099
HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "sub_server.py")


def port_busy(p):
    s = socket.socket()
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", p))
        return True
    except OSError:
        return False
    finally:
        s.close()


def main():
    if port_busy(PORT):
        return 0  # 已在运行，无需操作
    # DETACHED_PROCESS: 脱离父进程，不随调用者退出而被杀
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [sys.executable, TARGET],
        cwd=HERE,
        creationflags=flags,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
