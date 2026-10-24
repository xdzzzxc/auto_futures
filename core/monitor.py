from time import sleep
from datetime import datetime, timedelta
from pywinauto import mouse, ElementNotFoundError
from backtrader import strategy
import time
from public import shared_data
from public.anti_screensaver import kill_blacklist_process
from public.print_context import print_context
from sendmsg.pushplus import send_msg
from public.shared_data import click_position, is_trade_status, trade_flag, get_data_cache_dir, click_control, set_lots
from log.trade_log import setup_trade_loggers
import os, json
# 导入计数写入函数
from core.private import append_close_record
from core.connect_ths import set_loss_profit


logger = setup_trade_loggers()

UI_DELAY_SHORT = 0.2
MONITOR_INTERVAL = 0.5
NO_HOLD_PRINT_INTERVAL = 6000  # 无持仓每60秒打印一次，不刷屏
TRADE_INTERVAL = shared_data.valid_trade_interval if shared_data.valid_trade_interval else 300

# def find_target_contract_ctrl(ths_window, fut_code: str, screen_top_limit=900):
#     """
#     在持仓窗口查找目标合约Text控件
#     return: 找到返回控件对象，找不到返回None
#     """
#     fut_code_ctrl = None
#     try:
#         tmp_ctrl = ths_window.child_window(control_type="Text", title=fut_code)
#         tmp_ctrl.wait("visible", timeout=0.8)
#         rect = tmp_ctrl.rectangle()
#         rect_valid = (rect.right > rect.left) and (rect.bottom > rect.top)
#         if rect_valid and tmp_ctrl.is_visible() and tmp_ctrl.is_enabled() and rect.top < screen_top_limit:
#             fut_code_ctrl = tmp_ctrl
#     except (TimeoutError, ElementNotFoundError):
#         fut_code_ctrl = None
#     return fut_code
#
# def cancel_trade(rect = (539, 948, 20, 18)):
#     """撤单：点击撤单控件，增加异常捕获"""
#     try:
#         x, y, w, h = rect
#         center_x = x + w // 2
#         center_y = y + h // 2
#         mouse.click(button="left", coords=(center_x, center_y))
#         print_context("👉 执行撤单点击")
#         sleep(0.3)
#         return True
#     except Exception as e:
#         print_context(f"❌撤单点击失败: {str(e)}")
#         return False

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
    return {"sim_user": [sim_count, sim_pnl], "real_user": [real_count, real_pnl]}


def auto_trade(trade_dir=None):
    """负责点击买多或卖空进行期货品种下单，等待成交确认"""
    if trade_dir is None:
        print_context("没有明确的交易方向！")
        return None
    shared_data.trade_window.maximize()
    shared_data.trade_window.set_focus()
    controls = shared_data.ths_common_control
    sleep(0.5)
    current_time = datetime.now()
    click_ok = False
    # 买多 / 卖空
    if trade_dir == "rise":
        try:
            click_position(controls["买多"][1])
            click_ok = True
        except Exception as e:
            # click_control(text="买多", control_type="Text", click_btn=0)
            print_context(f"买多坐标点击失败，尝试文本查找方式：{str(e)}")
        if not click_ok:
            click_control(text="买多", control_type="Text", click_btn=0)
    else:
        try:
            click_position(controls["卖空"][1])
            click_ok = True
        except Exception as e:
            print_context(f"卖空坐标点击失败，尝试文本查找方式：{str(e)}")
        if not click_ok:
            click_control(text="卖空", control_type="Text", click_btn=0)
    cur_price = float(controls["即时价格"][0].window_text().strip())
    print_context(f"[{current_time.strftime('%H:%M:%S')}]程序已发送交易请求，正在等待市场撮合中......")

    # ========== 新增：等待成交确认 ==========
    max_wait_sec = 30
    poll_interval = 0.5
    start_ts = time.time()
    filled = False
    # target_contract_ctrl = None
    while time.time() - start_ts < max_wait_sec:
        sleep(poll_interval)
        status_ok = is_trade_status()
        # target_contract_ctrl = find_target_contract_ctrl(shared_data.trade_window, fut_code=fut_code)
        if status_ok:
            filled = True
            break

    if filled:
        print_context(f"✅[{datetime.now().strftime('%H:%M:%S')}]开仓成交确认，持仓已出现!")
        print_context(f"今日交易明细 - {get_today_trade_stat()}")
        with shared_data.variables_rlock:
            shared_data.valid_time = None
        # 自动设置云止损单
        set_loss_profit()

    else:
        print_context(f"❌[{datetime.now().strftime('%H:%M:%S')}]开仓等待{max_wait_sec}秒未检测到持仓，请检查委托是否成交")
        # 未成交不清除冷却标记，保持现状
    return cur_price



def monitor_profit_loss():
    from core.trade import reset_temp_params_in_yaml
    # ========== 启动监控时一次性读取平仓控件坐标 ==========
    try:
        close_ctrl_position = shared_data.ths_common_control['平仓'][1]
    except Exception as e:
        print_context(f"monitor_profit_loss 获取平仓控件失败:{str(e)}")
        return

    # ============== 自动平仓执行函数，签名不变 ==============
    def _trade(msg, ts_code_arg: str, profit_arg: float,
               strategy_id: str, trade_period: str,
               original_pre_profit=None, original_pre_loss=None,
               ):
        try:
            with shared_data.ctrl_rlock:
                shared_data.trade_window.maximize()
                shared_data.trade_window.set_focus()
                sleep(0.5)
                result = click_position(close_ctrl_position)

            if result:
                print_context("_trade: 程序已根据止损止盈设置值完成自动平仓！")
                with shared_data.variables_rlock:
                    shared_data.valid_time = datetime.now() + timedelta(minutes=shared_data.valid_trade_interval)
                    print_context(f"【平仓点击成功，设置冷却】下次交易有效时间起点：{shared_data.valid_time}")

                # 仅平仓点击成功才写入记录、统计、推送成功消息、重置参数
                ut = getattr(shared_data, "user_type", 0)
                append_close_record(user_type=ut, pnl=profit_arg, ts_code=ts_code_arg,
                                    strategy_id=strategy_id, trade_period=trade_period)
                stat = get_today_trade_stat()
                sim_cnt, sim_pnl = stat["sim_user"]
                real_cnt, real_pnl = stat["real_user"]
                full_msg = (
                    f"{msg}\n"
                    f"------------ 今日平仓汇总 ------------\n"
                    f"【模拟账户】平仓次数：{sim_cnt}，累计盈亏：{sim_pnl:.2f}元\n"
                    f"【实盘账户】平仓次数：{real_cnt}，累计盈亏：{real_pnl:.2f}元"
                )
                send_msg(f"自动平仓成功 - 品种：{ts_code_arg}\n{full_msg}")
                print_context(f"自动平仓 [{datetime.now().strftime('%H:%M:%S')}]")
                reset_temp_params_in_yaml()
            else:
                print_context("_trade: 平仓按钮点击返回False")
                # 平仓点击失败：推送失败告警，不写成交记录、不设置冷却、不重置yaml
                fail_msg = f"【平仓失败告警】品种：{ts_code_arg}，触发条件：{msg}"
                send_msg(fail_msg)

        except Exception as e:
            send_msg(f"平仓异常错误：{str(e)}")
            print_context(f"平仓失败：{str(e)}")
            # 平仓异常，回滚止盈止损阈值
            with shared_data.dict_rlock:
                if original_pre_profit is not None:
                    shared_data.pre_profit = original_pre_profit
                if original_pre_loss is not None:
                    shared_data.pre_loss = original_pre_loss

    no_print = True
    print_context("MonitorThread 盈亏监控线程已启动，永久常驻运行")

    while True:
        try:
            # 判断是否是在交易时段内，否则跳过循环，仅首次打印
            if not trade_flag():
                if no_print:
                    print_context(f"[{datetime.now().strftime('%H:%M:%S')}] 请等待期市开市！- 日市：9:00:00 | 夜市：21:00:00")
                    no_print = False
                sleep(1)
                continue

            # 判断是否存在持仓
            if not is_trade_status():
                # print(f"\r>>> 无期货交易中，等待开仓！", flush=True, end="")
                if no_print:
                    print_context(f">>> 无期货交易中，等待开仓！")
                    no_print = False
                sleep(0.5)
                continue
            no_print = True

            # 读取配置参数
            with shared_data.dict_rlock:
                pre_profit = shared_data.pre_profit
                original_pre_profit = pre_profit
                pre_loss = shared_data.pre_loss
                original_pre_loss = pre_loss
                ts_code = shared_data.trade_menu_dict.get("产品代码", shared_data.ts_code)

            profit = 0.0
            try:
                with shared_data.ctrl_rlock:
                    profit_loss_ctrl = shared_data.ths_common_control['盈亏'][0]
                    profit_text = profit_loss_ctrl.window_text().strip()
                    profit = float(profit_text.strip().split()[-1])
                    if "手多仓" in profit_text:
                        shared_data.direction = "rise"
                    elif "手空仓" in profit_text:
                        shared_data.direction = "fall"

                print(f"\r【监控信息[{datetime.now().strftime('%H:%M:%S')}]】 >>> 交易品种：{ts_code} {shared_data.tscode_lots_dict.get(ts_code)}手。 交易策略："
                      f"{shared_data.trade_menu_dict.get('rule_id', 'unknow')} "
                      f"多空：{shared_data.direction} 止盈阈值={pre_profit} 止损阈值={pre_loss} "
                      f"云单（区分老仓信息）：{shared_data.trade_menu_dict}\033[K 浮动盈亏={profit:.2f}", flush=True, end="")

            except (ValueError, Exception) as e:
                # 修改文案：区分读取控件异常，不再误导平仓完成
                print(
                    f"\r读取盈亏控件异常，等待重试 - [{datetime.now().strftime('%H:%M:%S')} VS {shared_data.valid_time}] \033[K",
                    flush=True, end="")
                continue

            # ========== 止盈止损判断 ==========
            strategy_id = shared_data.trade_menu_dict.get("rule_id", "unknow")
            trade_period = shared_data.trade_menu_dict.get("trade_period", "")
            if pre_profit > 0 and profit >= pre_profit - 0.02:
                close_reason = f"[{ts_code}]止盈平仓\n盈利：{profit}元(固定金额止盈)"
                with shared_data.dict_rlock:
                    shared_data.pre_profit = 0
                    shared_data.pre_loss = 0
                _trade(msg=close_reason, ts_code_arg=ts_code, profit_arg=profit,
                       original_pre_profit=original_pre_profit, original_pre_loss=original_pre_loss,
                       strategy_id=strategy_id, trade_period=trade_period)
                print("量化程序已触发止盈平仓！")
                # set_lots()

            elif pre_loss < 0 and profit <= pre_loss + 0.02:
                close_reason = f"[{ts_code}]止损平仓\n亏损：{profit}元(固定金额止损)"
                with shared_data.dict_rlock:
                    shared_data.pre_profit = 0
                    shared_data.pre_loss = 0
                _trade(msg=close_reason, ts_code_arg=ts_code, profit_arg=profit,
                       original_pre_profit=original_pre_profit, original_pre_loss=original_pre_loss,
                       strategy_id=strategy_id, trade_period=trade_period)
                print("量化程序已触发止损平仓！")
                # set_lots()

            sleep(MONITOR_INTERVAL)
        except Exception as e:
            # 顶层兜底捕获，防止监控线程直接挂掉
            print_context(f"【monitor顶层捕获】监控循环异常：{str(e)}")
            send_msg(f"盈亏监控线程异常告警：{str(e)}")
            sleep(1)
            continue


if __name__ == '__main__':
    print(get_today_trade_stat())
