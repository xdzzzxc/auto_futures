from datetime import datetime
from public import shared_data
from public.print_context import print_context
from public.shared_data import ths_lock
from data.db_price import write_price
from data.db_price import batch_write_price
import re, time
from time import sleep

FLUSH_INTERVAL = shared_data.FLUSH_INTERVAL  # 刷新缓冲区时间间隔，其设置值由main.py模块中的_init_()中完成
MAX_BUFFER_COUNT = shared_data.MAX_BUFFER_COUNT

def get_current_price(ts_code=None):
    from public.shared_data import simulate_input
    price_patten = re.compile(r"^\d+\.\d+$|^\d+$")
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

            # 价格为空直接跳过，保留休眠限流UI扫描
            if not price_text or not price_patten.match(price_text):
                sleep(0.2)
                continue

            # 匹配目标合约，写入内存缓冲区，不再直接写DB
            current_ts = time.time()
            if code_ctrl.window_text() == ts_code:
                row = [date_inner, price_text, ts_code]
                # 线程安全追加缓冲区
                with shared_data.buffer_lock:
                    shared_data.price_buffer.append(row)

                # 判断是否满足批量写入条件：超时 或 缓冲区满
                if (current_ts - shared_data.last_flush_ts >= FLUSH_INTERVAL) or len(
                        shared_data.price_buffer) >= MAX_BUFFER_COUNT:
                    # 批量落库
                    with shared_data.buffer_lock:
                        batch_data = shared_data.price_buffer.copy()
                        shared_data.price_buffer.clear()
                        shared_data.last_flush_ts = current_ts
                    # 批量写入，仅一次数据库IO
                    if batch_data:
                        batch_write_price(batch_data)  # 实现批量插入接口

            # 读到有效数据短休眠，平衡实时与CPU
        except Exception as e:
            sleep(0.2)
            continue
        sleep(shared_data.get_price_interval)  # 获取即时品种市场价格的时间间隔设置

if __name__ == "__main__":
    print(shared_data.trade_flag())
    # get_current_price(ts_code="lu2604")
