import threading
import time
import ctypes

user32 = ctypes.WinDLL('user32', use_last_error=True)


def anti_screensaver():
    while True:
        try:
            # 极微移动：右1像素 → 左1像素（肉眼完全看不见）
            user32.mouse_event(1, 1, 0, 0, 0)
            time.sleep(0.01)
            user32.mouse_event(1, -1, 0, 0, 0)

            time.sleep(1)  # 每秒动一次（你要的间隔）
        except:
            time.sleep(1)


def anti_screensaver_thread():
    # 守护线程：主程序关闭，它自动关闭
    thread = threading.Thread(target=anti_screensaver, daemon=True)
    thread.start()
    print("✅ 程序已在后台启动防锁屏功能")

if __name__ == "__main__":
    anti_screensaver_thread()