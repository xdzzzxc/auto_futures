# reget_open_price.py 修改后完整代码
from datetime import datetime
from time import sleep
from data.get_quote import get_open_price, get_trade_day_str  # 导入get_open_price和交易日判断函数
from public.jiaoyisuo import get_future_info
from public.print_context import print_context
from public import shared_data
import os

DEBUG_MODE = True

def reget_open_price(ts_code=None):
    ts_code = ts_code if ts_code else shared_data.ts_code
    # 初始化该品种的触发标记，如果不存在则置False
    if ts_code not in shared_data.night_trigger_done:
        shared_data.night_trigger_done[ts_code] = False

    print_context(f"[{ts_code}] reget_open_price线程启动，DEBUG_MODE={DEBUG_MODE}")

    # 判断品种是否有夜盘
    try:
        info = get_future_info(symbol=ts_code)
        IS_NIGHT_MODE = info.get("night_trading", False)
        print_context(f"[{ts_code}] 品种夜盘配置 IS_NIGHT_MODE={IS_NIGHT_MODE}")
    except Exception as e:
        IS_NIGHT_MODE = False
        print_context(f"[{ts_code}] 获取夜盘信息失败，判定为无夜盘, err:{str(e)}")

    if not IS_NIGHT_MODE:
        print_context(f"[{ts_code}] 无夜场交易，reget_open_price线程退出！")
        return

    cache_folder = os.path.join(os.getcwd(), "futures_data", "open_price")
    os.makedirs(cache_folder, exist_ok=True)
    last_day = datetime.now().day
    heartbeat_cnt = 0

    while True:
        # 优雅退出检查
        if shared_data.stop_flag:
            print_context(f"[{ts_code}] reget_open_price 收到停止标记，线程退出")
            break

        now = datetime.now()
        cur_hour = now.hour
        cur_minute = now.minute
        cur_day = now.day

        # 跨天重置标记
        if cur_day != last_day:
            shared_data.night_trigger_done[ts_code] = False
            last_day = cur_day
            print_context(f"[{ts_code}] 跨天，重置night_trigger_done标记，cur_day={cur_day}")

        # 复用getquote的交易日逻辑，统一规则
        is_night_session, sys_today_str, real_trade_day_str = get_trade_day_str()

        # ========== 调试心跳 ==========
        # heartbeat_cnt += 1
        # if DEBUG_MODE and heartbeat_cnt >= 10:
        #     heartbeat_cnt = 0
        #     trigger_state = shared_data.night_trigger_done[ts_code]
            # print_context(
            #     f"[{ts_code}] 心跳 | 当前时间:{now.strftime('%Y-%m-%d %H:%M:%S')} "
            #     f"is_night_session={is_night_session}, night_trigger_done={trigger_state}, "
            #     f"real_trade_day={real_trade_day_str}"
            # )
        # ==============================

        # 满足条件：有夜盘、当前属于夜盘时段、本次夜盘还未触发
        if IS_NIGHT_MODE and is_night_session and not shared_data.night_trigger_done[ts_code]:
            print_context(f"[{ts_code}] ✅ 命中夜盘重取开盘价条件！")
            need_refresh = True

            # 直接检查【真实交易日】缓存文件是否存在，不再读取文件mtime！
            trade_cache_file = os.path.join(cache_folder, f"{ts_code}_{real_trade_day_str}_openprice.json")
            if os.path.exists(trade_cache_file):
                print_context(f"[{ts_code}] 检测到已存在【真实交易日】缓存 {trade_cache_file}，跳过重拉")
                shared_data.night_trigger_done[ts_code] = True
                need_refresh = False

            if need_refresh:
                # 调用get_open_price，内部会自动处理：删旧缓存、网络拉取、双文件保存
                get_open_price(ts_code=ts_code)
                print_context(f"[{ts_code}] ✅ 夜盘调用get_open_price完成，开盘信息已更新至shared_data.open_price")
                shared_data.night_trigger_done[ts_code] = True

        sleep(1)


if __name__ == '__main__':
    shared_data.night_trigger_done = {}
    shared_data.stop_flag = False
    print_context("===== 单独调试 reget_open_price =====")
    reget_open_price(ts_code="jd2609")
