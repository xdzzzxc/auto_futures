import os
import random
from time import sleep
import akshare as ak
import pandas as pd
import numpy as np
from public import shared_data
from public.print_context import print_context

def setup_pandas_display():
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 10000)
    pd.set_option('display.max_colwidth', 10000)
    pd.set_option('display.unicode.ambiguous_as_wide', True)
    pd.set_option('display.unicode.east_asian_width', True)
    pd.set_option('display.float_format', '{:.2f}'.format)
    pd.set_option('display.expand_frame_repr', False)

setup_pandas_display()

# ---------------------- 核心函数：1分钟K自动计算策略信号 ----------------------
def collect_current_price(ts_code=None):
    if ts_code is None or str(ts_code).strip() == "":
        print_context("❌ 请输入合法合约代码，如 m2609")
        return

    # 合约优先级
    run_ts = shared_data.ts_code if shared_data.ts_code else ts_code

    today = pd.Timestamp.now().strftime("%Y%m%d")
    cache_folder = os.path.join(os.getcwd(), "futures_data", "sina_data")
    os.makedirs(cache_folder, exist_ok=True)
    min_cache_path = os.path.join(cache_folder, f"{run_ts}_{today}_min.pkl")

    last_k_time = None
    print_context(f"✅ 启动 {run_ts} 1分钟实时行情监听")

    while True:
        try:
            # 拉取1分钟数据
            df_raw = ak.futures_zh_minute_sina(symbol=run_ts, period="1")
            if df_raw.empty:
                print_context("⚠️ 数据为空，休眠8秒")
                sleep(8)
                continue

            df_raw["datetime"] = pd.to_datetime(df_raw["datetime"])

            # 增量缓存
            if os.path.exists(min_cache_path):
                df_old = pd.read_pickle(min_cache_path)
                df_all = pd.concat([df_old, df_raw]).drop_duplicates(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)
            else:
                df_all = df_raw.copy()
            df_all.to_pickle(min_cache_path)

            latest_dt = df_all["datetime"].iloc[-1]
            if latest_dt == last_k_time:
                sleep(random.uniform(2.2, 3.8))
                continue
            last_k_time = latest_dt

            # ===================== 自动计算日内指标 =====================
            day_high = round(df_all["high"].max(), 0)
            day_low  = round(df_all["low"].min(), 0)
            now_close = df_all["close"].iloc[-1]
            avg_cost  = round(df_all["close"].mean(), 0)

            # 成交量过滤
            vol_5 = df_all["volume"].tail(5).mean()
            curr_vol = df_all["volume"].iloc[-1]

            # 持仓变化
            hold_now = df_all["hold"].iloc[-1]
            hold_pre = df_all["hold"].iloc[-2] if len(df_all) >=2 else hold_now

            # ===================== 自动开仓信号 =====================
            enable_long = False
            enable_short = False
            tick = 1

            # 做多信号：靠近支撑 + 缩量止跌
            if abs(now_close - day_low) <= tick and curr_vol < vol_5 * 0.8:
                enable_long = True

            # 做空信号：靠近压力 + 缩量滞涨
            if abs(now_close - day_high) <= tick and curr_vol < vol_5 * 0.8:
                enable_short = True

            # 自适应止损止盈（不依赖历史数据，直接用日内波动）
            day_range = day_high - day_low
            if day_range < 5:
                day_range = 10
            base_stop = int(day_range * 0.35)
            base_tp = int(day_range * 0.8)

            # 多空点位
            long_entry = day_low + tick
            long_stop  = day_low - base_stop
            long_tp    = day_high - tick

            short_entry = day_high - tick
            short_stop  = day_high + base_stop
            short_tp    = day_low + tick

            # ===================== 写入公共下单参数 =====================
            shared_data.order_param_dict = {
                "合约代码": run_ts,
                "现价": now_close,
                "压力": day_high,
                "支撑": day_low,
                "均价": avg_cost,
                "可开多": enable_long,
                "可开空": enable_short,
                "多头": {"开仓": long_entry, "止损": long_stop, "止盈": long_tp},
                "空头": {"开仓": short_entry, "止损": short_stop, "止盈": short_tp},
            }

            # 实时输出
            print(f"【{latest_dt}】现价={now_close} 压力={day_high} 支撑={day_low} 可多={enable_long} 可空={enable_short}")

            sleep(random.uniform(2.2, 3.8))

        except Exception as err:
            print_context(f"❌ 错误：{str(err)}")
            sleep(10)

# ------------------- 测试入口 -------------------
if __name__ == "__main__":
    shared_data.ts_code = "m2609"  # 必须赋值
    collect_current_price(ts_code="m2609")