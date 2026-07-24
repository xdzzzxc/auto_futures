import psutil
import win32gui
import win32process
from time import sleep
import ctypes
import random
from datetime import datetime
from ctypes import wintypes
import atexit

from public import shared_data

# ====================== 配置区 ======================
# 1. 进程白名单：以下进程完全放行，不杀进程、不关窗口
WHITE_PROCESS_LIST = {
    # 交易软件 同花顺期货通
    "happ.exe",
    # WPS全家桶
    "wps.exe",
    "et.exe",
    "wpspdf.exe",
    # Office Word Excel
    "winword.exe",
    "excel.exe",
    # 360浏览器
    "360se.exe",
    # 系统记事本
    "notepad.exe",
    # PyCharm开发工具
    "pycharm64.exe",
    "pycharm.exe",
    # 豆包客户端
    "doubao.exe",
    # 系统核心基础进程（防止误关资源管理器、桌面）
    "explorer.exe",
    "dwm.exe",
    "ctfmon.exe"
}

# 2. 进程黑名单：后台壁纸、屏保、广告后台，直接杀死进程
KILL_PROC_BLACKLIST = {
    "scrnsave.scr",        # Windows系统屏保
    "360huabao.exe",       # 360壁纸
    "360wallpaper.exe",
    "360desktop.exe",
    "sesvcr.exe",          # 360守护复活进程
    "lively.exe",
    "wallpaperengine.exe",
    "xzwallpaper.exe",     # 小智桌面壁纸
    "hexinlauncher.exe",   # 同花顺广告启动器
    "stickynotes.exe"      # 系统便笺
}

# Windows 电源API常量
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

# 全局缓存DLL与结构体，减少循环开销
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.windll.kernel32

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
pt = POINT()

# 程序退出恢复系统息屏策略
def restore_system_power():
    kernel32.SetThreadExecutionState(ES_CONTINUOUS)
atexit.register(restore_system_power)

def keep_system_active():
    """阻止系统息屏、系统屏保"""
    kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)

def prevent_screensaver():
    """极小幅度鼠标微动，不干扰操作"""
    with shared_data.mouse_lock:
        user32.GetCursorPos(ctypes.byref(pt))
        dx = random.randint(-5, 5)
        dy = random.randint(-5, 5)
        user32.SetCursorPos(pt.x + dx, pt.y + dy)
        user32.SetCursorPos(pt.x, pt.y)

def is_window_bottom_right(hwnd):
    """判断窗口是否在屏幕右下角（广告弹窗特征）"""
    screen_w = user32.GetSystemMetrics(0)
    screen_h = user32.GetSystemMetrics(1)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    win_w = rect.right - rect.left
    win_h = rect.bottom - rect.top
    # 右下角区域判定：窗口右下角落在屏幕右下1/4区域内，且窗口尺寸偏小（广告）
    return rect.right > screen_w * 0.75 and rect.bottom > screen_h * 0.75 and win_w < 600 and win_h < 400

def close_unallowed_windows():
    """遍历所有可见窗口，关闭非白名单窗口、右下角广告弹窗"""
    def enum_window_callback(hwnd, _):
        # 只处理可见窗口
        if not win32gui.IsWindowVisible(hwnd):
            return True
        win_title = win32gui.GetWindowText(hwnd).strip()
        if not win_title and not is_window_bottom_right(hwnd):
            return True
        # 获取窗口所属进程
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            proc = psutil.Process(pid)
            proc_name = proc.name().lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return True
        # 白名单进程放行，不关闭
        if proc_name in WHITE_PROCESS_LIST:
            return True
        # 满足：非白名单 或 右下角广告弹窗 → 关闭窗口
        is_bottom_ad = is_window_bottom_right(hwnd)
        if is_bottom_ad or proc_name not in WHITE_PROCESS_LIST:
            win32gui.PostMessage(hwnd, 0x0010, 0, 0)  # WM_CLOSE 关闭窗口
            pos_desc = "【右下角广告】" if is_bottom_ad else "【非白名单窗口】"
            print(f"{pos_desc}已关闭 | 进程:{proc_name} | 标题:{win_title}")
        return True
    win32gui.EnumWindows(enum_window_callback, 0)

def kill_blacklist_process():
    """查杀黑名单壁纸/屏保后台进程"""
    killed_pids = set()
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            pid = proc.info["pid"]
            p_name = proc.info["name"].lower()
            if p_name not in KILL_PROC_BLACKLIST or pid in killed_pids:
                continue
            win_title = ""
            def enum_cb(h, _):
                nonlocal win_title
                if win32gui.IsWindowVisible(h):
                    _, wp = win32process.GetWindowThreadProcessId(h)
                    if wp == pid:
                        win_title = win32gui.GetWindowText(h).strip()
                return True
            win32gui.EnumWindows(enum_cb, 0)
            p = psutil.Process(pid)
            p.terminate()
            try:
                p.wait(timeout=1.2)
            except psutil.TimeoutExpired:
                p.kill()
            killed_pids.add(pid)
            print(f"\n后台进程查杀 | PID:{pid} | 进程:{p_name} | 窗口标题:{win_title if win_title else '无窗口'}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        except Exception:
            continue
last_mouse = datetime.now()
def main_daemon():
    global last_mouse
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"===== 启动白名单守护&广告弹窗查杀程序[{now}] =====")
    keep_system_active()
    while True:
        # 微动单独控间隔15~20s，窗口查杀保持5~10s高频
        if (datetime.now() - last_mouse).total_seconds() >= 18:
            prevent_screensaver()
            last_mouse = datetime.now()
        close_unallowed_windows()
        kill_blacklist_process()
        # 窗口查杀依旧5~10秒扫一轮，广告立刻处理
        sleep(random.randint(5, 10))

if __name__ == "__main__":
    # 必须管理员运行，否则无法关闭部分弹窗进程
    # main_daemon()
    kill_blacklist_process()