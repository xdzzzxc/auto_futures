from datetime import datetime
from public import shared_data
from public.print_context import print_context
from public.shared_data import ths_lock
from data.db_price import batch_write_price
import re, time
from time import sleep

# 取消时间间隔判断，固定满100条入库
BUFFER_MAX_NUM = 100

def get_current_price(ts_code=None):
    from public.shared_data import simulate_input
    price_patten = re.compile(r"^\d+\.\d+$|^\d+$")
    is_printed = False

    # 锁定读取控件句柄
    with ths_lock:
        code_ctrl = shared_data.ths_common_control['期货代码'][0]
        lock_ctrl = shared_data.ths_common_control["商品锁"][0]
    window = shared_data.trade_window

    # 内部工具函数：实时获取界面当前合约
    def get_ui_contract():
        with ths_lock:
            new_ts_code = code_ctrl.window_text().strip()
            shared_data.ts_code = new_ts_code if new_ts_code else ts_code
            return new_ts_code

    # 初始化界面合约
    current_ui_code = get_ui_contract()
    if not current_ui_code:
        default_code = ts_code if ts_code else shared_data.ts_code if shared_data.ts_code else "m2609"
        if lock_ctrl.is_enabled():
            simulate_input(code_ctrl, window, default_code)
            lock_ctrl.click_input()
        else:
            lock_ctrl.click_input()
            simulate_input(code_ctrl, window, default_code)
            lock_ctrl.click_input()
        current_ui_code = get_ui_contract()

    # 主采集循环，每 get_price_interval(5秒) 读取一次价格
    while True:
        new_ui_code = get_ui_contract()
        # 检测合约切换：强制落库所有缓存数据
        if new_ui_code and new_ui_code != current_ui_code:
            with shared_data.buffer_lock:
                cache_data = shared_data.price_buffer.copy()
                shared_data.price_buffer.clear()
            if cache_data:
                batch_write_price(cache_data)
                print_context(f"[{datetime.now()}] 合约切换 {current_ui_code} → {new_ui_code}，强制入库{len(cache_data)}条")
            current_ui_code = new_ui_code

        # 非交易时间仅打印日志
        if not shared_data.trade_flag():
            if not is_printed:
                print_context(f"[{datetime.now()}] 非交易时段，当前界面合约：{current_ui_code}")
                is_printed = True
            sleep(0.5)
            continue
        is_printed = False

        date_str = datetime.now().strftime("%Y%m%d%H%M%S")
        write_batch = None
        try:
            # 读取价格控件
            with shared_data.ths_lock:
                price_ctrl = shared_data.ths_common_control['即时价格'][0]
                price_text = price_ctrl.window_text().strip()
            # 价格格式校验
            if not price_text or not price_patten.match(price_text):
                sleep(0.2)
                continue
            # 记录：时间、价格、界面实时合约
            row = [date_str, price_text, current_ui_code]
            # 写入内存缓冲区
            with shared_data.buffer_lock:
                shared_data.price_buffer.append(row)
                # 唯一入库条件：缓存条数达到100条
                if len(shared_data.price_buffer) >= BUFFER_MAX_NUM:
                    write_batch = shared_data.price_buffer.copy()
                    shared_data.price_buffer.clear()
            # 执行批量写入
            if write_batch:
                batch_write_price(write_batch)
                print_context(f"[{datetime.now()}] 缓存满{BUFFER_MAX_NUM}条，批量入库，共{len(write_batch)}条")
        except Exception:
            sleep(0.2)
            continue
        # 严格5秒读取一次价格
        sleep(shared_data.get_price_interval)

if __name__ == "__main__":
    print("交易状态：", shared_data.trade_flag())
    # get_current_price("jd2609")