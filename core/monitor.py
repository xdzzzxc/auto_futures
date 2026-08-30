from time import sleep
from datetime import datetime
from public import shared_data
from public.anti_screensaver import kill_blacklist_process
from public.print_context import print_context
from sendmsg.weichat_push import send_msg
from public.jiaoyisuo import get_future_info
from public.shared_data import click_position, is_trade_status, trade_flag
from log.trade_log import setup_trade_loggers
logger = setup_trade_loggers()
UI_DELAY_SHORT = 0.2
MONITOR_INTERVAL = 0.5
NO_HOLD_PRINT_INTERVAL = 6000  # 无持仓每60秒打印一次，不刷屏

def auto_trade(trade_dir=None):
    """负责点击买多或卖空进行期货品种下单"""
    if trade_dir is None:
        print_context("没有明确的交易方向！")
        return
    shared_data.trade_window.maximize()
    shared_data.trade_window.set_focus()
    controls = shared_data.ths_common_control
    # order_params = shared_data.trade_menu_dict  # 获取定单参数表
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
    # ============== 自动止损止盈执行平仓 ==============
    def _trade(msg):
        try:
            kill_blacklist_process()  # 点击平仓控件前杀死屏保、壁纸等程序以免遮挡而无效点击
            with shared_data.ths_lock:
                shared_data.trade_window.maximize()
                shared_data.trade_window.set_focus()
                sleep(0.2)
                click_position(close_ctrl_position)
                sleep(2)  # 平仓后等待同花顺成交弹窗刷新，冷却操作！
            send_msg(f"自动平仓成功 - 品种：{ts_code}\n{msg}")
            shared_data.trade_menu_dict.clear()
            # shared_data.order_param_dict.clear()
            # shared_data.pre_profit = 0
            # shared_data.pre_loss = 0
            shared_data.threading_monitor_profit_loss = False

        except Exception as e:
            send_msg(f"平仓失败错误：{str(e)}")
            print_context(f"平仓失败：{str(e)}")
            # 失败也关闭监控，避免无限重试；如需重试可自行加计数限制
            shared_data.threading_monitor_profit_loss = False

    no_print = True  # 只打印一次防止刷屏

    while True:
        # 0720临时增加,判断是不是在交易时段内，否则关闭自动平仓交易线程
        if not trade_flag():
            shared_data.threading_monitor_profit_loss = False
            break
        # ============== 无持仓直接跳过 ==============
        if not is_trade_status():
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
            # print(f"\r监控程序检测到已设置期货品种[{ts_code}]的止盈值是：{pre_profit} 止损值是：{pre_loss}", flush=True, end="")
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
                # logger.info(f"current price: {current_price}\nprofit: {profit}")

        except (ValueError, Exception):
            sleep(0.2)
            continue


        # ---------------- 止盈：盈利达到设置值  或  价格达到止盈价 ----------------
        if all((profit >= pre_profit, pre_profit>0)):  # pre_profit>0表示已手动设置固定止盈值
            close_reason = f"[{ts_code}]止盈平仓\n盈利：{profit}元(手动设置固定预盈利值)"
            _trade(msg=close_reason)  # 模拟点击平仓控件按钮完成平仓操作
            shared_data.threading_monitor_profit_loss = False
            sleep(2)  # 2秒后再去检测监控状态
            print("量化程序已完成自动平仓，暂时关闭自动监控程序！")
            break
        # 买多止盈：当前价 >= 止盈价
        if direction == "Rise" and current_price >= profit_price:
            close_reason = f"[{ts_code}]止盈平仓\n价格触发止盈价 {profit_price}\n盈利：{profit}"
            _trade(msg=close_reason)
            shared_data.threading_monitor_profit_loss = False
            sleep(2)  # 2秒后再去检测监控状态
            break
        # 卖空止盈：当前价 <= 止盈价
        if direction == "Fall" and current_price <= profit_price:
            close_reason = f"[{ts_code}]止盈平仓\n价格触发止盈价 {profit_price}\n盈利：{profit}"
            _trade(close_reason)
            shared_data.threading_monitor_profit_loss = False
            sleep(2)  # 2秒后再去检测监控状态
            break
        # ---------------- 止损：亏损 <=-400  或  价格达到止损价 ----------------
        if all((profit <= pre_loss, pre_loss < 0)):
            close_reason = f"[{ts_code}]止损平仓\n亏损：{profit}元(手动设置固定预亏损值)"
            _trade(msg=close_reason)
            shared_data.threading_monitor_profit_loss = False
            sleep(2)  # 2秒后再去检测监控状态
            break
        # 买多止损：当前价 <= 止损价
        if direction == "Rise" and current_price <= loss_price:
            close_reason = f"[{ts_code}]止损平仓\n价格触发止损价 {loss_price}\n亏损：{profit}"
            _trade(msg=close_reason)
            shared_data.threading_monitor_profit_loss = False
            sleep(2)  # 2秒后再去检测监控状态
            break
        # 卖空止损：当前价 >= 止损价
        if direction == "Fall" and current_price >= loss_price:
            close_reason = f"[{ts_code}]止损平仓\n价格触发止损价 {loss_price}\n亏损：{profit}"
            _trade(msg=close_reason)
            shared_data.threading_monitor_profit_loss = False
            sleep(2)  # 2秒后再去检测监控状态
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