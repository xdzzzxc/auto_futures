from public import shared_data
# 导入：trade_flag 是【判断交易时段的函数】
from public.shared_data import trade_flag, is_trade_status
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
        # 增加是否在交易状态中来设置写入数据库的相关设置
        try:
            if is_trade_status:
                with shared_data.analyze_interval_lock:
                    shared_data.analyze_interval = 60
            else:
                with shared_data.analyze_interval_lock:  # 加锁读取analyze_interval的值或赋值
                    if shared_data.analyze_interval != 600:
                        shared_data.analyze_interval = 600
        except Exception as e:
            print("监控模块检测不到交易状态，可能是is_trade_status模块出问题！")
            continue
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
                elif not run_allow and monitor_thread is not None and monitor_thread.is_alive():
                    print(
                        f"\r[{datetime.now().strftime('%H:%M:%S')}] 非交易时段/已关闭手动开关，正在停止自动平仓监控程序！",
                        flush=True)
                    shared_data.threading_monitor_profit_loss = False                    # 等待监控线程最多3秒，优雅回收资源​
                    monitor_thread.join(timeout=3)
                    monitor_thread = None
        else:
            # 不在交易时段 / 手动开关关闭，打印提示
            if not in_trade_time:
                print(f"\r[{datetime.now().strftime('%H:%M:%S')}] 当前不在交易时段，自动平仓监控已关闭", flush=True, end='')
            # else:
            #     print("\r已关闭(或未开启)自动平仓监控程序！", flush=True, end="")

if __name__ == '__main__':
    pass