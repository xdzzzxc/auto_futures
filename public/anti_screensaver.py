import psutil
import win32gui
import win32process
from time import sleep

# 白名单：系统保护进程 + 常驻软件
WHITE_PROC_NAMES = {
    "system", "svchost.exe", "explorer.exe", "ntoskrnl.exe", "winlogon.exe",
    "csrss.exe", "smss.exe", "services.exe", "dwm.exe", "taskmgr.exe",
    "conhost.exe", "wlanext.exe", "spoolsv.exe", "lsass.exe", "fontdrvhost.exe",
    "rundll32.exe", "mmc.exe", "wininit.exe", "textinputhost.exe",
    "pycharm64.exe", "360se.exe", "360tray.exe", "wechat.exe", "doubao.exe", "pycharm.exe",
    "hexinlauncher.exe", "happ.exe"
}
# 唯一允许关闭的系统类进程：屏保
SCREEN_SAVER = "scrnsave.scr"


def get_all_visible_window_info():
    """函数1：获取全部可视窗口 pid、进程名、标题"""
    window_list = []

    def enum_callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd).strip()
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        proc_name = "未知进程"
        try:
            proc = psutil.Process(pid)
            proc_name = proc.name().lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        window_list.append({"pid": pid, "proc_name": proc_name, "title": title})
        return True

    win32gui.EnumWindows(enum_callback, 0)
    return window_list


def kill_unprotected_process():
    """函数2：常驻循环查杀，单独开线程执行，无需传入window_data"""

    # 关键：每一轮都重新采集最新窗口列表
    window_data = get_all_visible_window_info()
    for item in window_data:
        pid = item["pid"]
        p_name = item["proc_name"]
        title = item["title"]

        # 白名单进程跳过，屏保强制关闭
        if p_name in WHITE_PROC_NAMES and p_name != SCREEN_SAVER:
            continue

        try:
            psutil.Process(pid).terminate()
            print(f"已关闭 >>> PID:{pid} | 进程名:{p_name} | 窗口标题:{title}")
        except psutil.NoSuchProcess:
            continue
        except Exception as e:
            print(f"PID {pid} 关闭失败: {e}")


if __name__ == "__main__":
    # 调试入口，仅调用两个函数
    kill_unprotected_process()