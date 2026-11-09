import threading
import time
import pyautogui
from pynput import mouse
from pynput.mouse import Controller
from typing import Optional

# 全局控制器、监听句柄、停止信号（单个实例够用；如果你多线程并发下单，要改成对象实例）
_mouse_listener: Optional[mouse.Listener] = None
_stop_event = threading.Event()
_m_ctrl = Controller()


def lock_mouse_center(duration: float = 3.0, enable: bool = True) -> None:
    """
    移动鼠标到屏幕中心，锁定：人为移动会被拉回；
    支持外部主动调用 unlock_mouse() 提前解锁（给自动化云单操作放行）
    :param duration: 最大锁定时长，超时自动解锁
    :param enable: 总开关
    """
    global _mouse_listener, _stop_event
    if not enable or duration <= 0:
        return

    # 先清理上一次残留
    unlock_mouse()
    _stop_event.clear()

    def _lock_task():
        global _mouse_listener
        w, h = pyautogui.size()
        cx, cy = w // 2, h // 2
        _m_ctrl.position = (cx, cy)
        end_ts = time.time() + duration

        def on_move(x, y):
            # 收到停止信号 或者 超时 → 放行
            if _stop_event.is_set() or time.time() >= end_ts:
                return True
            # 人为移动，拉回中心点
            _m_ctrl.position = (cx, cy)
            return False

        _mouse_listener = mouse.Listener(on_move=on_move)
        _mouse_listener.start()

        # 等待，直到收到停止信号 或者 超时
        while not _stop_event.is_set() and time.time() < end_ts:
            time.sleep(0.01)

        # 结束监听
        if _mouse_listener and _mouse_listener.is_alive():
            _mouse_listener.stop()
        _mouse_listener = None

    t = threading.Thread(target=_lock_task, daemon=True)
    t.start()


def unlock_mouse() -> None:
    """主动解锁鼠标，供自动化云单操作前调用"""
    global _mouse_listener, _stop_event
    _stop_event.set()
    if _mouse_listener and _mouse_listener.is_alive():
        _mouse_listener.stop()
    _mouse_listener = None


if __name__ == '__main__':
    # 自测：锁3秒，2秒的时候主动解锁测试
    lock_mouse_center(duration=10)
    print("锁定开始")
    time.sleep(5)
    unlock_mouse()
    print("主动解锁")
    time.sleep(1)
