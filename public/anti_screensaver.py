import threading
import time
import ctypes
from ctypes import Structure, c_uint, c_long, c_ulong, POINTER
from public.close_ad_window import close_ad_windows

user32 = ctypes.WinDLL('user32', use_last_error=True)

class MOUSEINPUT(Structure):
    _fields_ = [
        ("dx", c_long),
        ("dy", c_long),
        ("mouseData", c_ulong),
        ("dwFlags", c_ulong),
        ("time", c_ulong),
        ("dwExtraInfo", POINTER(c_ulong))
    ]

class INPUT(Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]
    _anonymous_ = ("_input",)
    _fields_ = [("type", c_uint), ("_input", _INPUT)]

INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001

def auto_close_popup():
    while True:
        try:
            close_ad_windows()
            # 新增：专门查杀全屏壁纸/锁屏窗口
            enum_windows_kill_wallpaper()
        except Exception:
            pass
        time.sleep(30)

def anti_screensaver():
    while True:
        move1 = INPUT()
        move1.type = INPUT_MOUSE
        move1.mi.dx = 1
        move1.mi.dy = 0
        move1.mi.dwFlags = MOUSEEVENTF_MOVE

        move2 = INPUT()
        move2.type = INPUT_MOUSE
        move2.mi.dx = -1
        move2.mi.dy = 0
        move2.mi.dwFlags = MOUSEEVENTF_MOVE

        inputs = (INPUT * 2)(move1, move2)
        user32.SendInput(2, inputs, ctypes.sizeof(INPUT))
        time.sleep(15)  # 缩短间隔，更稳重置闲置计时器

# 新增：遍历窗口，关闭全屏壁纸锁屏弹窗
def enum_windows_kill_wallpaper():
    def callback(hwnd, extra):
        if not user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        win_name = buf.value.lower()
        # 匹配常见壁纸/锁屏关键词，按需扩充
        keyword_list = ["壁纸", "锁屏", "杂志", "桌面助手", "sogou", "360wallpaper"]
        for kw in keyword_list:
            if kw in win_name:
                user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE 关闭窗口
                break
        return True

    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(callback)
    user32.EnumWindows(enum_proc, 0)

def anti_screensaver_thread():
    screen_thread = threading.Thread(target=anti_screensaver, daemon=True)
    screen_thread.start()
    close_thread = threading.Thread(target=auto_close_popup, daemon=True)
    close_thread.start()
    print("✅ 程序已在后台启动防锁屏/屏保+自动查杀壁纸弹窗功能")

if __name__ == '__main__':
    anti_screensaver()