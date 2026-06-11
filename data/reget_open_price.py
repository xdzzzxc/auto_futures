from datetime import datetime
from time import sleep
from data.get_quote import get_open_price
from public.jiaoyisuo import get_future_info
from public.print_context import print_context
from public import shared_data
import os

# 全局标记：防止当日夜盘区间内重复执行
TRIGGER_DONE = False

def reget_open_price(ts_code=None):
    global TRIGGER_DONE
    ts_code = ts_code if ts_code else shared_data.ts_code

    # 判断品种是否有夜盘
    try:
        info = get_future_info(symbol=ts_code)
        IS_NIGHT_MODE = info.get("night_trading", False)
    except Exception:
        IS_NIGHT_MODE = False
        print_context(f"[{ts_code}] 获取夜盘信息失败，判定为无夜盘")

    cache_folder = os.path.join(os.getcwd(), "futures_data")
    os.makedirs(cache_folder, exist_ok=True)
    # print(cache_folder)

    last_day = datetime.now().day

    while True:
        now = datetime.now()
        cur_hour = now.hour
        cur_day = now.day
        str_time = now.strftime("%Y%m%d")
        tscode_file_path = os.path.join(cache_folder, f"{ts_code}_{str_time}_openprice.json")

        # 跨天重置标记，保证次日夜盘可正常触发
        if cur_day != last_day:
            TRIGGER_DONE = False
            last_day = cur_day

        # 核心：判断当前是否处于 21:00 ~ 次日 02:00 夜盘区间（不含02点）
        in_night_range = (cur_hour >= 21) or (0 <= cur_hour < 2)
        if not IS_NIGHT_MODE:
            print_context(f"[{ts_code}] 无夜场交易，程序自动放弃交易！")
            return
        # 仅 有夜盘 + 处于夜盘区间 + 未执行过 才进入判断
        if IS_NIGHT_MODE and in_night_range and not TRIGGER_DONE:
            need_refresh = True

            # 新增：判断文件最后修改时间，避免重复刷新
            if os.path.exists(tscode_file_path):
                # 获取文件最后修改时间（转为本地datetime）
                file_mtime_ts = os.path.getmtime(tscode_file_path)
                file_mtime = datetime.fromtimestamp(file_mtime_ts)
                file_hour = file_mtime.hour
                # 判断文件是否已经是【夜盘时段生成】
                file_in_night = (file_hour >= 21) or (0 <= file_hour < 2)
                # print_context(f"文件[{tscode_file_path}]的修改时间：{file_mtime}")
                if file_in_night:
                    # 文件已在夜盘生成，无需再次删除&拉取
                    print_context(f"[{ts_code}] 检测到夜盘已生成文件，跳过刷新，避免重复请求")
                    TRIGGER_DONE = True
                    need_refresh = False

            # 需要刷新才执行删文件+重拉数据
            if need_refresh:
                if os.path.exists(tscode_file_path):
                    try:
                        os.remove(tscode_file_path)
                        print_context(f"[{ts_code}] 处于夜盘时段，已删除日间开盘价文件: {os.path.basename(tscode_file_path)}")
                    except Exception as e:
                        print_context(f"[{ts_code}] 删除文件异常: {str(e)}")

                # 重新获取开盘价
                get_open_price(ts_code=ts_code)
                TRIGGER_DONE = True
                print_context(f"重新获取期货品种[{ts_code}]的夜盘开盘价")

            break  # 本轮逻辑结束，退出轮询

        sleep(1)

if __name__ == '__main__':
    reget_open_price(ts_code="jd2609")