import psutil
import win32gui
import win32process
from time import sleep
import ctypes
import random
from datetime import datetime
from ctypes import wintypes
import atexit
import pywintypes

from public import shared_data

# ====================== 配置区 ======================
# 进程白名单：仅用于后台进程查杀放行，弹窗规则不受白名单限制
WHITE_PROCESS_LIST = {
    "happ.exe",
    "wps.exe",
    "et.exe",
    "wpspdf.exe",
    "winword.exe",
    "excel.exe",
    "360se.exe",
    "notepad.exe",
    "pycharm64.exe",
    "pycharm.exe",
    "doubao.exe",
    "explorer.exe",
    "dwm.exe",
    "ctfmon.exe",
    "cmd.exe"  # CMD加入白名单
}

# 后台黑名单进程，后台查杀专用
KILL_PROC_BLACKLIST = {
    "scrnsave.scr",
    "360huabao.exe",
    "360wallpaper.exe",
    "360desktop.exe",
    "sesvcr.exe",
    "lively.exe",
    "wallpaperengine.exe",
    "xzwallpaper.exe",
    "hexinlauncher.exe",
    "stickynotes.exe"
}

# Windows电源常量
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.windll.kernel32

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
pt = POINT()

def restore_system_power():
    kernel32.SetThreadExecutionState(ES_CONTINUOUS)
atexit.register(restore_system_power)

def keep_system_active():
    kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)

def prevent_screensaver():
    """防屏保微动鼠标"""
    with shared_data.mouse_lock:
        user32.GetCursorPos(ctypes.byref(pt))
        dx = random.randint(-5, 5)
        dy = random.randint(-5, 5)
        user32.SetCursorPos(pt.x + dx, pt.y + dy)
        user32.SetCursorPos(pt.x, pt.y)

def is_target_popup(hwnd):
    """目标弹窗判定（适配x=1600,y=1000基准，百分比兼容所有分辨率）
    全部满足才关闭：
    1. 窗口高度 < 屏幕总高度50%
    2. 窗口底部bottom > 屏幕总高度92.59% (对应1080p下y=1000)
    3. 窗口宽度 ≤ 屏幕总宽度1/6 ≈16.67%
    4. 窗口左侧left > 屏幕总宽度83.33% (对应1920p下x=1600)
    """
    screen_w = user32.GetSystemMetrics(0)
    screen_h = user32.GetSystemMetrics(1)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))

    win_w = rect.right - rect.left
    win_h = rect.bottom - rect.top

    cond1 = win_h < screen_h * 0.5
    cond2 = rect.bottom > screen_h * 0.9259
    cond3 = win_w <= screen_w / 6
    cond4 = rect.left > screen_w * 0.8333
    return cond1 and cond2 and cond3 and cond4

def close_only_target_popup():
    """仅关闭符合尺寸位置的右下角弹窗，不再关闭其他非白名单窗口"""
    def enum_callback(hwnd, _):
        if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
            return True
        if not is_target_popup(hwnd):
            return True

        # 匹配目标弹窗，直接关闭，无视进程白名单
        win_title = win32gui.GetWindowText(hwnd).strip()
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        proc_name = "未知进程"
        try:
            proc_name = psutil.Process(pid).name().lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        try:
            win32gui.PostMessage(hwnd, 0x0010, 0, 0)
            win32gui.DestroyWindow(hwnd)
            print(f"【遮挡期货控件弹窗已关闭】进程:{proc_name} | 标题:{win_title if win_title else '无'}")
        except pywintypes.error as e:
            # 仅忽略句柄失效、权限不足
            if e.winerror in (2, 5):
                print(f"【弹窗权限不足/已消失】进程:{proc_name} | 标题:{win_title if win_title else '无'}")
            else:
                raise
        return True
    win32gui.EnumWindows(enum_callback, 0)

def kill_blacklist_process():
    """查杀黑名单进程，增加去重打印，解决sesvcr.exe刷屏问题"""
    killed_names = set()
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            pid = proc.info["pid"]
            p_name = proc.info["name"].lower()
            if p_name not in KILL_PROC_BLACKLIST:
                continue
            # 去重：同一个进程名本轮只打印一次日志
            first_print = p_name not in killed_names

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
            killed_names.add(p_name)
            if first_print:
                print(f"\r后台查杀黑名单进程 | 进程:{p_name}", flush=True, end="")
                sleep(1)
                print(f"\r{' ' * 100}", flush=True, end="\n")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        except Exception:
            continue

last_mouse = datetime.now()
def main_daemon():
    global last_mouse
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"===== 守护程序启动[{now}] 功能：防屏保+清除遮挡期货控件弹窗 =====")
    keep_system_active()
    while True:
        # 18秒一次鼠标微动防屏保息屏
        if (datetime.now() - last_mouse).total_seconds() >= 18:
            prevent_screensaver()
            last_mouse = datetime.now()
        # 只扫描关闭遮挡期货窗口的目标弹窗
        close_only_target_popup()
        # 查杀壁纸/广告后台进程（去重打印不刷屏）
        kill_blacklist_process()
        sleep(random.randint(5, 10))

if __name__ == "__main__":
    # 管理员运行
    main_daemon()
    kill_blacklist_process()
    # close_only_target_popup()