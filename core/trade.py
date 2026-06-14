from time import sleep
from datetime import datetime
from public.jiaoyisuo import get_future_info
from public import shared_data
from public.print_context import print_context
from sendmsg.weichat_push import send_msg
from public.shared_data import click_position, is_trade_statue
from log.trade_log import setup_trade_loggers
from data.get_quote import get_open_price
from data.data_from_sina import fetch_future_data
logger = setup_trade_loggers()

def opening_session_trade(ts_code=None):
    ts_code = shared_data.ts_code if ts_code is None else ts_code
    logger.info(f'交易品种属性：{shared_data.open_price}')
    logger.info(f"交易品种[{ts_code}]的历史交易数据汇总：\n{shared_data.history_data_analysis}")
    logger.info(f"交易品种基本属性：{shared_data.ts_code_attribute_dict}")
    while True:

        break


def normal_session_trade():
    # while True:
    """下单代码"""


def order(ts_code=None):
    # 提前将ts_code期货的相关交易数据获取并存储到公共模块shared_data.py以便阶段下单函数调用

    ts_code = ts_code if ts_code is not None else shared_data.ts_code
    ts_info = get_future_info(ts_code)
    if ts_info is None:
        print_context(f"未检测到品种信息 - {ts_code}")
        return
    else:
        shared_data.ts_code_attribute_dict = ts_info  # 加入交易品种的属性到公共模块
    is_night = ts_info.get("night_trading", False)
    print_context(f"本次期货交易品种：{ts_info['exchange']} - {ts_code} - {ts_info['name']}")
    # ===========交易品种的历史交易数据分析,结果传入公共模块============
    fetch_future_data(ts_code)  # data.data_from_sina.fetch_future_data()
    # ========获取交易品种开盘信息，结果传入公共模块open_price=========
    get_open_price(ts_code)  # data.get_quote.get_open_price()
    # return
    if not ts_code:
        print_context("请输入期货品种代码，如：au2609")
        return
    # 兜底超时
    max_loop = 3600*15
    loop_count = 0
    while loop_count < max_loop:
        loop_count += 1
        # 先判断夜场和时间节点（日场必须在9：30分以前，夜场必须在21：30分以前

        current_time = datetime.now()
        h, m = current_time.hour, current_time.minute
        if is_night and h == 21 and m < 30 and not is_trade_statue():
            opening_session_trade()
            break
        elif not is_night and h == 9 and m < 30 and not is_trade_statue():
            normal_session_trade()
            break
        else:
            print(f"\r未达到期货品种[{ts_code}]的交易条件，请等待下单！ - {current_time.strftime('%H:%M:%S')}", flush=True, end="")
        sleep(1)  # 轮询间隔为1秒
    else:
        print_context("本次交易时间结束，等待下一个交易日的开盘！")
    exit()
    """根据条件自动下单"""
    ts_code = ts_code if ts_code is not None else shared_data.ts_code  #  or "c2607"
    ts_code_dict = get_info(ts_code)
    is_night = ts_code_dict.get("night_trading", False) if ts_code_dict else False
    # history_data = fetch_future_data(ts_code=shared_data.ts_code)
    history_data = shared_data.history_data_analysis
    # print(f'history_data: {history_data}')
    # print(f'shared_data.open_price:{shared_data.open_price}')
    logger.info(f"预计开市第一单交易区域价：{shared_data.open_price[ts_code]['open'] + history_data['最小高开差']} | "
                                f"{shared_data.open_price[ts_code]['open'] - history_data['最小低开差']}")

    # 时段设置
    if is_night:
        start_time = datetime.strptime("21:00:00", "%H:%M:%S").time()
        end_time = datetime.strptime("21:30:00", "%H:%M:%S").time()
    else:
        start_time = datetime.strptime("9:00:00", "%H:%M:%S").time()
        end_time = datetime.strptime("10:15:00", "%H:%M:%S").time()

    logger.info(f"[{ts_code}][夜场：{is_night}] 第一单下单交易时间段：{start_time} ~ {end_time}")

    # ========== 第一阶段交易循环 ==========
    no_print = True
    while True:
        current_time = datetime.now().time()
        if current_time >= end_time:
            print_context.print_context("已过第一阶段的交易时间，程序自动切换到第二阶段交易市场。")
            break

        # 未到开始时间
        if current_time < start_time:
            if no_print:
                print(f"\r现在不是第一阶段的合法交易时间：{datetime.now().strftime('%H:%M:%S %A')},"
                      f"正常交易时间段：{start_time}-{end_time}", flush=True, end="")

                sleep(0.5)
                no_print = False
            continue

        # print(f"\r正在等待条件成立后下单 ······ ", flush=True, end='')

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
            # ===================== 修复：%s → %S 时间格式化错误 =====================
            print_context.print_context(f"成功下单交易[{datetime.now().strftime('%Y%m%d %H:%M:%S')}]，具体参数如下：\n"
                                        f"{shared_data.trade_menu_dict}")
            print('期货开市第一阶段交易结束！')
            break  # 第一阶段只下一个订单，一旦成功就跳出第一阶段进入第二阶段市场交易

    print_context.print_context(f"目前已过第一阶段交易时间，正在进入第二阶段交易市场，请注意下单交易！"
                                f"[{datetime.now().strftime('%H:%M:%S')}]")

    # ========== 第二阶段（预留） ==========
    while True:
        with shared_data.deque_lock:  # 通过进程锁deque_lock读取期货品种的即时价格deque_price
            deque = shared_data.cur_price_deque
            print(f'\r{deque}', flush=True, end="")
        # 这里你以后写逻辑
        sleep(5)


# ===================== 启动 =====================
if __name__ == "__main__":
    order(ts_code="m2609")
    opening_session_trade(ts_code="m2609")