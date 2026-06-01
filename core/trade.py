from time import sleep
from datetime import datetime, timedelta
from collections import deque
from public.jiaoyisuo import get_future_info as get_info  # ===================
from public import shared_data, print_context
from sendmsg.weichat_push import send_msg
from public.jiaoyisuo import get_future_info
from public.screen_save import press_esc
from public.shared_data import click_position, is_trade_statue
from data.data_from_sina import fetch_future_data


def auto_trade():
    """负责点击买多或卖空进行期货品种下单"""
    press_esc()
    shared_data.trade_window.maximize()
    shared_data.trade_window.set_focus()
    controls = shared_data.ths_common_control
    order_params = shared_data.trade_menu_dict  # 获取定单参数表
    sleep(0.5)

    # 买多 / 卖空
    if order_params.get('交易方向') == "Rise":
        click_position(controls["买多"][1])
    else:
        click_position(controls["卖空"][1])

    print_context.print_context(f"程序已成功下单，正在交易中......[{order_params['交易方向']}]")


def monitor_profit_loss():
    """监视动态价格变化，完成自动平仓"""
    print_context.print_context(f'交易状态动态监控中 ......')
    print(f"order_param_dict:{shared_data.order_param_dict}\nhistory_data_analysis:{shared_data.history_data_analysis}"
          f"\ntrade_menu_dict:{shared_data.trade_menu_dict}")
    no_print = True  # 只打印一次防止刷屏
    while True:
        # ============== 无持仓直接跳过 ==============
        if not is_trade_statue():
            if no_print:
               print(f"\r无期货交易中，等待开仓！", flush=True, end="")
               no_print = False
            sleep(0.5)
            continue

        # ============== 加锁读取交易参数 ==============
        with shared_data.dict_lock:
            direction = shared_data.trade_menu_dict.get("交易方向")
            pre_profit = shared_data.trade_menu_dict.get("预盈利", 100)
            pre_loss = shared_data.trade_menu_dict.get("预亏损", -150)
            profit_price = shared_data.trade_menu_dict.get("止盈价")
            loss_price = shared_data.trade_menu_dict.get("止损价")
            ts_code = shared_data.trade_menu_dict.get("产品代码", shared_data.ts_code)

        # ============== 加锁读取盈亏 ==============
        profit = 0
        try:
            with shared_data.ths_lock:
                close_ctrl_position = shared_data.ths_common_control['平仓'][1]
                profit_loss_ctrl = shared_data.ths_common_control['盈亏'][0]
                profit_text = profit_loss_ctrl.window_text().strip()
                profit = float(profit_text.strip().split()[-1])
        except (ValueError, Exception):
            sleep(0.5)
            continue

        # ============== 平仓条件 ==============
        need_close = False
        close_reason = ""

        if profit >= pre_profit:
            need_close = True
            close_reason = f"止盈平仓 | 盈利：{profit}元"
        elif profit <= pre_loss:
            need_close = True
            close_reason = f"止损平仓 | 亏损：{profit}元"

        # ============== 执行平仓 ==============
        if need_close:
            try:
                with shared_data.ths_lock:
                    shared_data.trade_window.maximize()
                    shared_data.trade_window.set_focus()
                    sleep(0.1)
                    click_position(close_ctrl_position)
                    sleep(0.2)

                send_msg(f"自动平仓成功\n品种：{ts_code}\n{close_reason}")
                break  # 退出监控线程

            except Exception as e:
                send_msg(f"平仓失败错误：{str(e)}")

        sleep(0.5)


def calculate_profit_loss(future_code: str, direction: str,
                          trade_price: float | int,
                          profit_price: float | int):
    """计算盈亏与止损价"""
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
        loss_price = trade_price - profit_diff * 1.5

    elif direction == "Fall":
        profit = (trade_price - profit_price) / min_price_change * on_tick_profit - commission_value
        profit_diff = trade_price - profit_price
        loss_price = trade_price + profit_diff * 1.5

    elif direction == "Sideways":
        if trade_price > profit_price:
            profit = (trade_price - profit_price) / min_price_change * on_tick_profit - commission_value
            profit_diff = trade_price - profit_price
            loss_price = trade_price + profit_diff * 1.5
        else:
            profit = (profit_price - trade_price) / min_price_change * on_tick_profit - commission_value
            profit_diff = profit_price - trade_price
            loss_price = trade_price - profit_diff * 1.5

    return profit, loss_price


def order():
    """根据条件自动下单"""
    ts_code = shared_data.ts_code  #  or "c2607"
    ts_code_dict = get_info(ts_code)
    is_night = ts_code_dict.get("night_trading", False) if ts_code_dict else False
    # history_data = fetch_future_data(ts_code=shared_data.ts_code)
    history_data = shared_data.history_data_analysis
    print(f'history_data: {history_data}')
    print(f'shared_data.open_price:{shared_data.open_price}')
    print_context.print_context(f"预计交易价：{shared_data.open_price[ts_code]['open'] + history_data['最小高开差']} - "
                                f"{shared_data.open_price[ts_code]['open'] - history_data['最小低开差']}")
    # 时段设置
    if is_night:
        start_time = datetime.strptime("21:00:00", "%H:%M:%S").time()
        end_time = datetime.strptime("21:30:00", "%H:%M:%S").time()
    else:
        start_time = datetime.strptime("09:00:00", "%H:%M:%S").time()
        end_time = datetime.strptime("09:30:00", "%H:%M:%S").time()

    print_context.print_context(f"[{ts_code}][夜场：{is_night}] 第一单下单交易时间段：{start_time} ~ {end_time}")

    # ========== 第一阶段交易循环 ==========
    while True:
        current_time = datetime.now().time()
        if current_time >= end_time:
            break

        # 未到开始时间
        if current_time < start_time:
            print(f"\r现在是非交易时间：{datetime.now().strftime('%H:%M:%S %A')},本期货品种的第一单交易开始时间是：{start_time}", flush=True, end="")

            sleep(1)
            continue

        print(f"\r正在等待条件成立后下单 ······ ", flush=True, end='')

        # ========== 读取价格（加锁，防崩溃） ==========
        try:
            with shared_data.ths_lock:
                open_price = shared_data.open_price[ts_code]["open"]
                price_ctrl = shared_data.ths_common_control['即时价格'][0]
                current_price = float(price_ctrl.window_text())
        except:
            sleep(0.5)
            continue

        # 条件判断
        condition_met = False
        target_profit = 0.0
        # 根据当前即时价格确定是否下单交易
        if shared_data.direction == "Rise" and not is_trade_statue():
            target = open_price + history_data.get("最小高开差", 0)  # 设置买多时的最高价位
            if current_price <= target:
                condition_met = True
                target_profit = open_price + history_data.get("最大高开差", 0)

        elif shared_data.direction == "Fall" and not is_trade_statue():
            target = open_price - history_data.get("最小低开差", 0)  # 设置卖空时的最小价位
            if current_price >= target:
                condition_met = True
                target_profit = open_price - history_data.get("最大低开差", 0)

        # 执行下单
        if condition_met:
            profit, loss_price = calculate_profit_loss(
                future_code=ts_code,
                direction=shared_data.direction,
                trade_price=current_price,
                profit_price=target_profit
            )

            if profit <= 0:
                print_context.print_context("利润≤0，不执行有损交易！")
                continue

            # 写入交易参数
            with shared_data.dict_lock:
                shared_data.trade_menu_dict.update({
                    "品种": ts_code,
                    "定参时间": datetime.now().strftime("%H:%M:%S"),
                    "交易方向": shared_data.direction,
                    "交易价": current_price,
                    "止盈价": target_profit,
                    "止损价": loss_price,
                    "预盈利": profit,
                    "预亏损": -(profit * 1.5)
                })

            auto_trade()  # 下单交易函数
            send_msg(shared_data.trade_menu_dict)
            print_context.print_context(f"成功下单交易[{datetime.now().strftime('%Y%m%d %H:%M:%s')}]，具体参数如下：\n"
                                        f"{shared_data.trade_menu_dict}")
            continue
    print_context.print_context(f"目前已过第一阶段交易时间，正在进入第二阶段交易时间段，请注意下单交易！"
                                f"[{datetime.now().strftime('%H:%M:%S')}]")

    # ========== 第二阶段（预留） ==========
    while True:
        with shared_data.deque_lock:  # 通过进程锁deque_lock读取期货品种的即时价格deque_price
            deque = shared_data.cur_price_deque
            print(f'\r{deque}', flush=True, end="")
        # 这里你以后写逻辑
        sleep(1)


# ===================== 启动 =====================
if __name__ == "__main__":
    order()