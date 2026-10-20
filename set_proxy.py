# set_proxy.py  on <port> | off
# 设置 / 清除 Windows 用户级系统代理（浏览器、系统应用都会走它）
# 用 Python 直接改注册表 + 广播刷新，绕开 PowerShell 禁脚本限制。
import sys
import winreg
import ctypes

REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"


def _set_dword(name, value):
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE)
    winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)
    winreg.CloseKey(key)


def _set_str(name, value):
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE)
    winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
    winreg.CloseKey(key)


def on_proxy(port):
    _set_dword("ProxyEnable", 1)
    _set_str("ProxyServer", "127.0.0.1:%s" % port)
    # 本地/局域网地址不走代理，避免回环与内网异常
    _set_str("ProxyOverride", "localhost;127.*;192.168.*;10.*;<local>")
    print("系统代理已开启 -> 127.0.0.1:%s" % port)


def off_proxy():
    _set_dword("ProxyEnable", 0)
    print("系统代理已关闭 (ProxyEnable=0)")


def refresh():
    # 双管齐下：WinINet 刷新 + 广播 WM_SETTINGCHANGE，让浏览器/系统立即生效
    try:
        wininet = ctypes.windll.wininet
        wininet.InternetSetOptionW(0, 39, 0, 0)  # INTERNET_OPTION_SETTINGS_CHANGED
        wininet.InternetSetOptionW(0, 37, 0, 0)  # INTERNET_OPTION_REFRESH
    except Exception as e:
        print("  [warn] WinINet 刷新失败(注册表已改):", e)
    try:
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        ctypes.cdll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0,
            "Internet Settings", 0x0002, 1000, None)
    except Exception as e:
        print("  [warn] 广播刷新失败(注册表已改):", e)


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) >= 2 and args[0].lower() == "on":
        on_proxy(args[1])
    else:
        off_proxy()
    refresh()
