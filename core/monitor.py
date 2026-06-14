from time import sleep
from datetime import datetime
from public import shared_data
from public.print_context import print_context
from sendmsg.weichat_push import send_msg
from public.jiaoyisuo import get_future_info
from public.shared_data import click_position, is_trade_statue
from log.trade_log import setup_trade_loggers
logger = setup_trade_loggers()
UI_DELAY_SHORT = 0.2
MONITOR_INTERVAL = 0.5
NO_HOLD_PRINT_INTERVAL = 60  # 无持仓每60秒打印一次，不刷屏

def auto_trade():
    """负责点击买多或卖空进行期货品种下单"""

    shared_data.trade_window.maximize()
    shared_data.trade_window.set_focus()
    controls = shared_data.ths_common_control
    order_params = shared_data.trade_menu_dict  # 获取定单参数表
    sleep(0.5)
    current_time = datetime.now().time()
    # 买多 / 卖空
    if order_params.get('交易方向') == "Rise":
        click_position(controls["买多"][1])
    else:
        click_position(controls["卖空"][1])

    print_context(f"程序已成功下单，正在交易中......[{order_params['交易方向']}]")


def monitor_profit_loss():
    # ============== 执行平仓 ==============
    def _trade(msg):
        try:
            with shared_data.ths_lock:
                shared_data.trade_window.maximize()
                shared_data.trade_window.set_focus()
                sleep(0.2)
                click_position(close_ctrl_position)

            send_msg(f"自动平仓成功 - 品种：{ts_code}\n{msg}")
            # break  # 如果是只有单交易退出监控线程，若有多各种交易如手动下单后则不会再次自动平仓

        except Exception as e:
            send_msg(f"平仓失败错误：{str(e)}")
            print_context(f"平仓失败：{str(e)}")

    """监视动态价格变化，完成自动平仓"""
    print_context(f'交易状态动态监控中 ......')
    if shared_data.order_param_dict:
        logger.info(f"[{shared_data.ts_code}]下单参数：\n{shared_data.order_param_dict}")

    if shared_data.history_data_analysis:
        logger.info(f"[{shared_data.ts_code}]新浪历史交易数据分析：\n{shared_data.history_data_analysis}")
    if shared_data.open_price:
        logger.info(f"[{shared_data.ts_code}]今日开盘信息[东财网]:\n{shared_data.open_price}")

    if shared_data.trade_menu_dict:
        logger.info(f"程序已自动下单，成交参数：{shared_data.trade_menu_dict}\n{'=^=' * 40}")

    no_print = True  # 只打印一次防止刷屏

    while True:
        # ============== 无持仓直接跳过 ==============
        if not is_trade_statue():
            if no_print:
                print(f">>> 无期货交易中，等待开仓！")
                no_print = False
            sleep(0.5)
            continue

        # ============== 加锁读取交易参数 ==============
        with shared_data.dict_lock:
            direction = shared_data.trade_menu_dict.get("交易方向")
            pre_profit = shared_data.pre_profit  # 固定止盈
            pre_loss = shared_data.pre_loss  # 固定止损
            profit_price = shared_data.trade_menu_dict.get("止盈价", 0.0)
            loss_price = shared_data.trade_menu_dict.get("止损价", 0.0)
            ts_code = shared_data.trade_menu_dict.get("产品代码", shared_data.ts_code)

        # ============== 加锁读取 盈亏 + 当前价格 ==============
        profit = 0
        current_price = 0.0

        try:
            with shared_data.ths_lock:
                close_ctrl_position = shared_data.ths_common_control['平仓'][1]
                profit_loss_ctrl = shared_data.ths_common_control['盈亏'][0]
                price_ctrl = shared_data.ths_common_control['即时价格'][0]

                # 读取盈亏
                profit_text = profit_loss_ctrl.window_text().strip()
                profit = float(profit_text.strip().split()[-1])

                # 读取当前实时价格
                current_price = float(price_ctrl.window_text())
                # 日志记录即时价位和即时盈亏
                logger.info(f"current price: {current_price}\nprofit: {profit}")

        except (ValueError, Exception):
            sleep(0.5)
            continue


        # ---------------- 止盈：盈利达到设置值  或  价格达到止盈价 ----------------
        if all((profit >= pre_profit, pre_profit>0)):  # pre_profit>0表示已手动设置固定止盈值
            close_reason = f"[{ts_code}]止盈平仓\n盈利：{profit}元(手动设置固定预盈利值)"
            _trade(msg=close_reason)  # 模拟点击平仓控件按钮完成平仓操作
            break
        # 买多止盈：当前价 >= 止盈价
        elif direction == "Rise" and current_price >= profit_price:
            close_reason = f"[{ts_code}]止盈平仓\n价格触发止盈价 {profit_price}\n盈利：{profit}"
            _trade(msg=close_reason)
            break
        # 卖空止盈：当前价 <= 止盈价
        elif direction == "Fall" and current_price <= profit_price:
            close_reason = f"[{ts_code}]止盈平仓\n价格触发止盈价 {profit_price}\n盈利：{profit}"
            _trade(close_reason)
            break
        # ---------------- 止损：亏损 <=-400  或  价格达到止损价 ----------------
        elif all((profit <= pre_loss, pre_loss < 0)):
            close_reason = f"[{ts_code}]止损平仓\n亏损：{profit}元(手动设置固定预亏损值)"
            _trade(msg=close_reason)
            break
        # 买多止损：当前价 <= 止损价
        elif direction == "Rise" and current_price <= loss_price:
            close_reason = f"[{ts_code}]止损平仓\n价格触发止损价 {loss_price}\n亏损：{profit}"
            _trade(msg=close_reason)
            break
        # 卖空止损：当前价 >= 止损价
        elif direction == "Fall" and current_price >= loss_price:
            close_reason = f"[{ts_code}]止损平仓\n价格触发止损价 {loss_price}\n亏损：{profit}"
            _trade(msg=close_reason)
            break
        sleep(0.5)  # 设置监控时间间隔为0.5秒


def calculate_profit_loss(future_code: str, direction: str,
                          trade_price: float | int,
                          profit_price: float | int):
    """计算盈亏与止损价 —— 已修复止损价异常问题"""
    future_info = get_future_info(future_code) or {}
    try:
        commission = future_info["commission"]
    except KeyError:
        commission = future_info.get('commission_rate', 0)

    commission_value = commission * 2 if commission > 0 else (profit_price + trade_price) * commission
    min_price_change = future_info.get('min_price_change', 1)
    on_tick_profit = future_info['one_tick_profit']

    profit = 0
    loss_price = 0

    if direction == "Rise":
        profit = (profit_price - trade_price) / min_price_change * on_tick_profit - commission_value
        profit_diff = profit_price - trade_price
        # ===================== 修复：买多止损价应该在交易价下方，不会出现负数 =====================
        loss_price = trade_price - abs(profit_diff) * 1.5

    elif direction == "Fall":
        profit = (trade_price - profit_price) / min_price_change * on_tick_profit - commission_value
        profit_diff = trade_price - profit_price
        # ===================== 修复：卖空止损价应该在交易价上方，不会飞上天 =====================
        loss_price = trade_price + abs(profit_diff) * 1.5

    elif direction == "Sideways":
        if trade_price > profit_price:
            profit = (trade_price - profit_price) / min_price_change * on_tick_profit - commission_value
            profit_diff = trade_price - profit_price
            loss_price = trade_price + abs(profit_diff) * 1.5
        else:
            profit = (profit_price - trade_price) / min_price_change * on_tick_profit - commission_value
            profit_diff = profit_price - trade_price
            loss_price = trade_price - abs(profit_diff) * 1.5

    # ===================== 安全保护：止损价永远 > 0 =====================
    loss_price = max(loss_price, 1.0)
    return profit, loss_price



# ===================== 启动 =====================
if __name__ == "__main__":
    pass