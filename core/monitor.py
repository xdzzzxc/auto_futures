from time import sleep
from datetime import datetime, timedelta
from public import shared_data
from public.anti_screensaver import kill_blacklist_process
from public.print_context import print_context
from sendmsg.pushplus import send_msg
from public.shared_data import click_position, is_trade_status, trade_flag, get_data_cache_dir
from log.trade_log import setup_trade_loggers
import os, json
# 导入计数写入函数
from core.private import append_close_record

logger = setup_trade_loggers()

UI_DELAY_SHORT = 0.2
MONITOR_INTERVAL = 0.5
NO_HOLD_PRINT_INTERVAL = 6000  # 无持仓每60秒打印一次，不刷屏
TRADE_INTERVAL = shared_data.valid_trade_interval if shared_data.valid_trade_interval else 300
valid_time = None

# 新增：读取trade_log.json获取今日交易次数、累计盈亏
def get_today_trade_stat():
    log_path = os.path.join(get_data_cache_dir(), "trade_log","trade_log.json")
    today_str = datetime.now().strftime("%Y%m%d")
    real_count = 0
    real_pnl = 0.0
    sim_count = 0
    sim_pnl = 0.0
    # print_context(f"【DEBUG】日志完整路径：{log_path}")
    # print_context(f"【DEBUG】今日日期字符串：{today_str}")
    if os.path.exists(log_path):
        # print_context("【DEBUG】文件存在，开始读取")
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            records = data.get("records", {})
            # print_context(f"【DEBUG】读取到总记录条数：{len(records)}")
            for time_key, rec in records.items():
                rec_date = time_key[:8]
                if rec_date == today_str:
                    pnl_val = float(rec.get("pnl", 0.0))
                    ut = int(rec.get("user_type", 0))
                    if ut == 0:
                        sim_count += 1
                        sim_pnl += pnl_val
                    elif ut == 1:
                        real_count += 1
                        real_pnl += pnl_val
            #         print_context(f"【DEBUG】匹配今日记录：{time_key}, user_type={ut}, pnl={pnl_val}")
            # print_context(f"【DEBUG】实盘：count={real_count}, pnl={real_pnl:.2f} | 模拟：count={sim_count}, pnl={sim_pnl:.2f}")
        except Exception as e:
            print_context(f"读取交易日志统计失败:{str(e)}")
    else:
        print_context(f"【DEBUG】文件不存在！")
    return sim_count, sim_pnl, real_count, real_pnl



def auto_trade(trade_dir=None):
    """负责点击买多或卖空进行期货品种下单"""
    if trade_dir is None:
        print_context("没有明确的交易方向！")
        return None
    shared_data.trade_window.maximize()
    shared_data.trade_window.set_focus()
    controls = shared_data.ths_common_control
    sleep(0.5)
    current_time = datetime.now()
    # 买多 / 卖空
    if trade_dir == "rise":
        click_position(controls["买多"][1])
    else:
        click_position(controls["卖空"][1])
    cur_price = float(controls["即时价格"][0].window_text().strip())
    print_context(f"[{current_time.strftime('%H:%M:%S')}]程序已成功下单[{trade_dir} - {cur_price}]，正在交易中......")
    return cur_price

def monitor_profit_loss():
    # ========== 启动监控时一次性读取平仓控件坐标 ==========
    try:
        close_ctrl_position = shared_data.ths_common_control['平仓'][1]
    except Exception as e:
        print_context(f"monitor_profit_loss 获取平仓控件失败:{str(e)}")
        return

    # ============== 自动平仓执行函数，复用原有逻辑 ==============
    def _trade(msg, ts_code_arg: str, profit_arg: float):
        global valid_time
        try:
            kill_blacklist_process()
            with shared_data.ths_lock:
                shared_data.trade_window.maximize()
                shared_data.trade_window.set_focus()
                sleep(0.2)
                click_position(close_ctrl_position)
                sleep(2)

            ut = getattr(shared_data, "user_type", 0)
            append_close_record(user_type=ut, pnl=profit_arg, ts_code=ts_code_arg)
            # 获取今日统计：模拟次数，模拟盈亏，实盘次数，实盘盈亏
            sim_cnt, sim_pnl, real_cnt, real_pnl = get_today_trade_stat()
            # 组装完整推送文本
            full_msg = (
                f"{msg}\n"
                f"------------ 今日平仓汇总 ------------\n"
                f"【模拟账户】平仓次数：{sim_cnt}，累计盈亏：{sim_pnl:.2f}元\n"
                f"【实盘账户】平仓次数：{real_cnt}，累计盈亏：{real_pnl:.2f}元"
            )
            send_msg(f"自动平仓成功 - 品种：{ts_code_arg}\n{full_msg}")

            shared_data.trade_menu_dict.clear()
            # ===== 平仓成功后更新 valid_time：当前时间 + 冷却间隔 =====
            with shared_data.dict_lock:
                valid_time = datetime.now() + timedelta(seconds=shared_data.valid_trade_interval)
                print_context(f"平仓冷却生效，下次可交易时间：{valid_time.strftime('%H:%M:%S')}")
        except Exception as e:
            send_msg(f"平仓失败错误：{str(e)}")
            print_context(f"平仓失败：{str(e)}")

    no_print = True
    while True:
        # 监控总开关
        if not trade_flag():
            break

        # 判断是否存在持仓/冷却期
        if not is_trade_status():
            if no_print:
                print(f">>> 无期货交易中，等待开仓！")
                no_print = False
            sleep(0.5)
            continue
        no_print = True

        # 读取配置参数
        with shared_data.dict_lock:
            pre_profit = shared_data.pre_profit
            pre_loss = shared_data.pre_loss
            ts_code = shared_data.trade_menu_dict.get("产品代码", shared_data.ts_code)

        profit = 0.0
        try:
            with shared_data.ths_lock:
                profit_loss_ctrl = shared_data.ths_common_control['盈亏'][0]
                profit_text = profit_loss_ctrl.window_text().strip()
                profit = float(profit_text.strip().split()[-1])
                print(f"\r【监控】当前浮动盈亏={profit:.2f}, 止盈阈值={pre_profit},止损阈值={pre_loss}", flush=True, end="")
        except (ValueError, Exception) as e:
            print(f"\r读取盈亏值错误，请将持仓合约切换到交易状态：{e}", flush=True, end="")
            sleep(0.2)
            continue

        # ========== 只保留固定金额止盈、止损，不再关心方向，增加浮点容错 ==========
        # 止盈：盈亏 >= pre_profit（pre_profit>0）
        if 0 < pre_profit <= profit + 0.02:
            close_reason = f"[{ts_code}]止盈平仓\n盈利：{profit}元(固定金额止盈)"
            _trade(msg=close_reason, ts_code_arg=ts_code, profit_arg=profit)
            break
        # 止损：盈亏 <= pre_loss（pre_loss<0）
        if 0 > pre_loss >= profit - 0.02:
            close_reason = f"[{ts_code}]止损平仓\n亏损：{profit}元(固定金额止损)"
            _trade(msg=close_reason, ts_code_arg=ts_code, profit_arg=profit)
            break
        print("量化程序已完成自动平仓，暂时关闭自动监控程序！")
        sleep(MONITOR_INTERVAL)


if __name__ == '__main__':
    print(get_today_trade_stat())
