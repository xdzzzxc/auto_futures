from public import shared_data
# 导入：trade_flag 是【判断交易时段的函数】
from public.shared_data import trade_flag
import threading
from core.monitor import monitor_profit_loss
from time import sleep
from datetime import datetime

monitor_lock = threading.Lock()
monitor_thread = None

def monitor_wrapper():
    """线程退出自动重置标记"""
    try:
        monitor_profit_loss()
    finally:
        with monitor_lock:
            shared_data.threading_monitor_profit_loss = False
            global monitor_thread
            monitor_thread = None

def run_monitor():
    global monitor_thread
    while True:
        sleep(1)
        # 1. 调用你封装好的函数，判断当前是否合法交易时间
        in_trade_time = trade_flag()
        # 2. 双重条件：时间合法 + 手动总开关开启
        run_allow = in_trade_time and shared_data.trade_flag

        with monitor_lock:
            # 需要启动：允许运行 且 无线程/线程已死亡
            need_start = run_allow and (monitor_thread is None or not monitor_thread.is_alive())

        if need_start:
            with monitor_lock:
                if run_allow and (monitor_thread is None or not monitor_thread.is_alive()):
                    shared_data.threading_monitor_profit_loss = True
                    print(f"\r[{datetime.now().strftime('%H:%M:%S')}] 已开启或重启自动平仓监控程序！", flush=True)
                    monitor_thread = threading.Thread(
                        target=monitor_wrapper,
                        name="MonitorThread",
                        daemon=True
                    )
                    monitor_thread.start()
        else:
            # 不在交易时段 / 手动开关关闭，打印提示
            if not in_trade_time:
                print(f"\r[{datetime.now().strftime('%H:%M:%S')}] 当前不在交易时段，自动平仓监控已关闭", flush=True, end='')
            else:
                print("\r已关闭(或未开启)自动平仓监控程序！", flush=True, end="")

if __name__ == '__main__':
    pass