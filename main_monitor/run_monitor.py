from public import shared_data
from public.shared_data import trade_flag, is_trade_status
import threading
from core.monitor import monitor_profit_loss
from time import sleep
from datetime import datetime
from public.print_context import print_context

# 修改为可重入锁，防止后续嵌套死锁
monitor_lock = threading.RLock()
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
            print_context(f"[{datetime.now().strftime('%H:%M:%S')}] 自动平仓监控线程已退出")

def run_monitor():
    global monitor_thread
    print_context("自动监控管理循环已启动")
    while True:
        sleep(1)
        # ========== 修复：必须调用 is_trade_status() ==========
        try:
            if is_trade_status():
                with shared_data.analyze_interval_lock:
                    shared_data.analyze_interval = 60
            else:
                with shared_data.analyze_interval_lock:
                    if shared_data.analyze_interval != 600:
                        shared_data.analyze_interval = 600
        except Exception as e:
            print_context(f"监控模块检测交易状态异常：{str(e)}")
            continue

        in_trade_time = trade_flag()
        run_allow = in_trade_time and shared_data.trade_flag

        with monitor_lock:
            thread_alive = (monitor_thread is not None) and monitor_thread.is_alive()

        # ========== 分支拆分：启动逻辑、停止逻辑分离，不再嵌套 ==========
        if run_allow:
            # 允许运行，无线程则启动
            if not thread_alive:
                with monitor_lock:
                    shared_data.threading_monitor_profit_loss = True
                    now = datetime.now().strftime('%H:%M:%S')
                    print_context(f"[{now}] 已开启/重启自动平仓监控程序！")
                    monitor_thread = threading.Thread(
                        target=monitor_wrapper,
                        name="MonitorThread",
                        daemon=True
                    )
                    monitor_thread.start()
        else:
            # 不允许运行，存在活跃线程则关闭【重点：挪到独立分支！】
            if thread_alive:
                with monitor_lock:
                    now = datetime.now().strftime('%H:%M:%S')
                    print_context(f"[{now}] 非交易时段/总开关关闭，停止自动平仓监控！")
                    shared_data.threading_monitor_profit_loss = False
                    monitor_thread.join(timeout=3)
                    monitor_thread = None

        # 调试用：定期打印状态（正式运行可以注释）
        # with monitor_lock:
        #     alive = monitor_thread.is_alive() if monitor_thread else False
        #     print_context(f"监控线程状态 alive={alive}, run_allow={run_allow}")

if __name__ == '__main__':
    pass