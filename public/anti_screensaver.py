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

from public import shared_data, print_context

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


# atexit不再依赖线程绑定的电源调用，注释掉
# atexit.register(restore_system_power)


def keep_system_active():
    """维持系统不休眠、不关闭显示器，放在循环内反复调用，规避线程销毁失效"""
    kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)


def prevent_screensaver():
    """防屏保微动鼠标；注意：调用前必须判断 not shared_data.ui_busy"""
    # with shared_data.variables_rlock:
    user32.GetCursorPos(ctypes.byref(pt))
    dx = random.randint(-4, 4)
    dy = random.randint(-4, 4)
    new_x = pt.x + dx
    new_y = pt.y + dy
    user32.SetCursorPos(new_x, new_y)
    sleep(0.02)
    user32.SetCursorPos(pt.x, pt.y)


def is_target_popup(hwnd: int) -> bool:
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
        win_title = win32gui.GetWindowText(hwnd).strip()
        # 系统窗口标题白名单
        SYSTEM_TITLE_WHITE = {"运行", "Run"}
        if win_title in SYSTEM_TITLE_WHITE:
            return True

        if not is_target_popup(hwnd):
            return True

        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        proc_name = "未知进程"
        try:
            proc = psutil.Process(pid)
            proc_name = proc.name().lower()
            # explorer.exe 系统资源管理器弹窗全部放行，不关闭
            if proc_name == "explorer.exe":
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        try:
            # 优先优雅关闭
            win32gui.PostMessage(hwnd, 0x0010, 0, 0)
            sleep(0.05)
            # 如果窗口还存在，再强制销毁
            if win32gui.IsWindow(hwnd):
                win32gui.DestroyWindow(hwnd)
            print(f"【遮挡期货控件弹窗已关闭】进程:{proc_name} | 标题:{win_title if win_title else '无'}")
        except pywintypes.error as e:
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
            p_name = proc.info["name"].lower()
            if p_name not in KILL_PROC_BLACKLIST:
                continue
            pid = proc.info["pid"]
            if p_name in killed_names:
                continue

            p = psutil.Process(pid)
            p.terminate()
            try:
                p.wait(timeout=1.2)
            except psutil.TimeoutExpired:
                p.kill()

            killed_names.add(p_name)
            print(f"\r后台查杀黑名单进程 | 进程:{p_name}", flush=True, end="")
            sleep(0.2)
            print(f"\r{' ' * 80}", flush=True, end="\n")

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        except Exception:
            continue


last_mouse = datetime.now()
MOUSE_INTERVAL = 16.5  # 鼠标微动间隔秒

def main_daemon():
    from public.shared_data import print_thread_status
    global last_mouse
    while True:
        try:
            # 循环内刷新电源抑制，避免线程绑定失效
            keep_system_active()

            # 鼠标微动：UI忙时直接跳过，不碰鼠标，保护pywinauto右键菜单
            delta = (datetime.now() - last_mouse).total_seconds()
            if delta >= MOUSE_INTERVAL:
                if not getattr(shared_data, "ui_busy", False):
                    prevent_screensaver()
                last_mouse = datetime.now()

            # 扫描关闭目标弹窗
            close_only_target_popup()

            # 查杀黑名单壁纸广告进程
            kill_blacklist_process()
            # print_thread_status()  # 打印线程状态
            sleep(random.randint(5, 10))

        except Exception as e:
            # 守护线程绝不崩溃，打印异常继续循环
            err_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"[守护daemon异常] {err_time} | error:{str(e)}")
            sleep(2)


if __name__ == "__main__":
    main_daemon()
