from time import sleep
from datetime import datetime
from public import shared_data
from public.print_context import print_context
import random
from pywinauto.timings import wait_until
from public.shared_data import ths_lock
from data.db_price import write_price

def get_current_price(ts_code=None):
    from public.shared_data import simulate_input
    is_printed = False
    if ts_code is None:
        ts_code = shared_data.ts_code if shared_data.ts_code is not None else "m2609"

    with ths_lock:
        code_ctrl = shared_data.ths_common_control['期货代码'][0]
        lock_ctrl = shared_data.ths_common_control["商品锁"][0]
    # 在期货代码控件内锁定交易品种以获取即时行情价格
    window = shared_data.trade_window
    if code_ctrl.window_text() != ts_code:
        if lock_ctrl.is_enabled():
            simulate_input(ctrl=code_ctrl, window=window, value=ts_code)
            lock_ctrl.click_input()
        else:
            lock_ctrl.click_input()
            simulate_input(ctrl=code_ctrl, window=window, value=ts_code)
            lock_ctrl.click_input()

    # 主循环
    while True:
        # 非交易时间
        if not shared_data.trade_flag():
            if not is_printed:
                print_context(f"[{datetime.now()}] 非交易时间，等待开市...")
                # print_context(f'已缓存价格条数：{len(shared_data.cur_price_deque)}')
                is_printed = True
            sleep(0.5)
            continue
        # 交易时间
        is_printed = False
        date_inner = datetime.now().strftime("%Y%m%d%H%M%S")
        # ====================== 【核心修复：安全读取价格】 ======================
        try:
            # 加锁读取界面控件（防止多线程崩溃）
            with shared_data.ths_lock:
                price_ctrl = shared_data.ths_common_control['即时价格'][0]
                price_text = price_ctrl.window_text().strip()

            # 价格为空直接跳过
            if not price_text:
                sleep(1)
                continue
            write_price([date_inner, price_text, ts_code])  # 将数据写入品种数据库
            # 存入队列（安全写法）
            with shared_data.deque_lock:
                shared_data.cur_price_deque.append((date_inner, price_text))
        except Exception as e:  # noqa
            # 读取失败不崩溃，跳过即可
            # print_context(f"价格读取异常：{str(e)}")
            sleep(1)
            continue
        # ====================== 【安全打印最近10条价格】 ======================
        try:
            with shared_data.dict_lock:
                dq_list = list(shared_data.cur_price_deque)
                latest_10 = []
                for item in dq_list[-10:]:
                    try:
                        latest_10.append(float(item[1].strip()))
                    except:
                        continue
        except:
            pass

        sleep(shared_data.interval)  # 获取即时品种市场价格的时间间隔设置

if __name__ == "__main__":
    print(shared_data.trade_flag())
    # get_current_price(ts_code="lu2604")
