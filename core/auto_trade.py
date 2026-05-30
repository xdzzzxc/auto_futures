"""
配合条件单双向操作交易；当即时盈亏达到条件单设置数值时进行自动交易；
当有特殊设置时，依据具体数据值进行自动交易；
"""
from public import shared_data, print_context
from time import sleep
allowed = {'0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '-', '.'}

def auto_trade():

    def get_profit() -> float:
        nonlocal profit
        profit_chars = []
        if not shared_data.ths_common_control:
            print_context.print_context(f'shared_data.ths_common_control is None!')
            return 0.0
        text = shared_data.ths_common_control['盈亏'][0].window_text().rstrip()
        for char in reversed(text):
            if char in allowed:
                profit_chars.append(char)
            else:
                break
        return float("".join(reversed(profit_chars)))
    while True:
        # 核心代码
        sleep(1)

    window = shared_data.trade_window
    profit = window["盈亏"][0]
    if window is None:
        print_context.print_context(f'shared_data.trade_window is None!')
        return
    pass


if __name__ == '__main__':
    auto_trade()