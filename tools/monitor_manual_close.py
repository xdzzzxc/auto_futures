""" 本模块主要是监控老仓自动平仓 """
from public import shared_data
from time import sleep
from datetime import datetime, timedelta
import threading
from core.monitor import monitor_profit_loss

def start_monitor():
    monitor_thread = threading.Thread(target=monitor_profit_loss, name="MonitorThread", daemon=True)
    monitor_thread.start()

def monitor_manual_close():
    print("【老仓监控】线程已进入，开始盯盈亏！")
    ths_window = shared_data.trade_window
    interval = shared_data.valid_trade_interval or 5
    profit_loss_ctrl = shared_data.ths_common_control["盈亏"][0]
    close_ctrl = shared_data.ths_common_control["平仓"][0]

    while True:
        try:
            raw_text = profit_loss_ctrl.window_text().strip()
            num_str = raw_text.split()[-1].replace(",", "")
            yk_val = float(num_str)

            pre_profit = shared_data.pre_profit
            pre_loss = shared_data.pre_loss
            print(f"\r[{datetime.now().strftime('%H:%M:%S')}] - 老仓监控线程 >>> 固定止盈值：{pre_profit} 固定止损值：{pre_loss} 实时盈亏：{yk_val}", flush=True, end="")

            if yk_val >= pre_profit:
                ths_window.set_focus()
                ths_window.maximize()
                print(f"\n【老仓监控】触发止盈，当前盈亏：{yk_val}，止盈阈值：{pre_profit}")
                close_ctrl.click_input()
                with shared_data.variables_rlock:
                    shared_data.valid_time = datetime.now() + timedelta(minutes=interval)
                print(f"程序进入交易冷却期，下次交易时间起点：{shared_data.valid_time}")
                start_monitor()
                break

            if pre_loss != 0 and yk_val <= pre_loss:
                ths_window.set_focus()
                ths_window.maximize()
                print(f"\n【老仓监控】触发止损，当前盈亏：{yk_val}，止损阈值：{pre_loss}")
                close_ctrl.click_input()
                with shared_data.variables_rlock:
                    shared_data.valid_time = datetime.now() + timedelta(minutes=interval)
                print(f"程序进入交易冷却期，下次交易时间起点：{shared_data.valid_time}")
                start_monitor()
                break
        except Exception as e:
            print(f"\r【老仓监控】 读取盈亏控件出现异常！{e}", flush=True, end="")
        sleep(1)

if __name__ == '__main__':
    monitor_manual_close()
