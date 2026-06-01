"""
本模块利用akshare从新浪网获取期货商品的交易数据；
通过分析数据自定义该期货品种的交易参数，并将其传递到公共模块变量：shared_data.order_param_dict
交易参数主要是多、空两个方向
"""
import os
from datetime import datetime
from functools import lru_cache
import akshare as ak
import pandas as pd
from data.get_quote import get_open_price
from public.jiaoyisuo import futures_info
from public import shared_data
import numpy as np
from public.print_context import print_context

# 将列标题转换成英文标题
zh_en_dict = {"日期": "trade_date", "开盘价": "open", "最高价": "high", "最低价": "low", "收盘价": "close",
              "成交量": "volume", "动态结算价": "settle_price",
              "持仓量": "open_interest", "结算价": "settle_price", "极值差": "extreme_diff",
              "标准差": "standard_deviation", "高开差": "high_open_diff", "低开差": "low_open_diff",
              "走势": "trend"}
# print({v: k for k, v in zh_en_dict.items()})
en_zh_dict = {'trade_date': '日期', 'open': '开盘价', 'high': '最高价', 'low': '最低价', 'close': '收盘价',
              'volume': '成交量', 'settle_price': '结算价', 'open_interest': '持仓量',
              'extreme_diff': '极值差', 'standard_deviation': '标准差',
              'high_open_diff': '高开差', 'low_open_diff': '低开差', 'trend': '走势'}

def setup_pandas_display():
    # 核心对齐配置
    pd.set_option('display.unicode.ambiguous_as_wide', True)  # 处理模糊字符宽度
    pd.set_option('display.unicode.east_asian_width', True)   # 处理中文字符宽度
    # 其他优化配置
    pd.set_option('display.unicode.ambiguous_as_wide', True)
    pd.set_option('display.max_columns', None)                # 显示所有列
    pd.set_option('display.width', None)                      # 自动适配宽度
    pd.set_option('display.max_colwidth', None)               # 列宽不截断
    pd.set_option('display.float_format', '{:.2f}'.format)    # 浮点数统一保留1位小数（可选）

setup_pandas_display()


def fetch_future_data(ts_code=None):
    # ts_code = shared_data.ts_code if ts_code is None else ts_code
    today = datetime.now().strftime("%Y%m%d")
    cache_folder = os.path.join(os.getcwd(), "futures_data\\sina_data")
    cache_file = os.path.join(cache_folder, f"{today}_open_price.pkl")
    os.makedirs(cache_folder, exist_ok=True)
    # ==================== 清理旧json：只保留今天的缓存文件 ====================
    for filename in os.listdir(cache_folder):
        file_path = os.path.join(cache_folder, filename)
        if os.path.isfile(file_path):
            # 只清理 .pkl 文件
            if filename.endswith(".pkl"):
                # 如果文件名里 不包含 今天日期 → 删掉
                if today not in filename:
                    try:
                        os.remove(file_path)
                        # print_context(f"已清理旧缓存：{filename}")
                    except Exception as e:
                        print_context(f"清理失败 {filename}：{str(e)}")
    print_context("已清理所有过期缓存！")
    # 读取或拉取数据
    if os.path.exists(cache_file):
        print_context(f"从本地加载数据：{cache_file}")
        sina_fut_data = pd.read_pickle(cache_file)
    else:
        print_context("从新浪获取数据...")
        days = shared_data.target_days
        sina_fut_data = ak.futures_main_sina(ts_code)

        # 转英文（内部计算用）
        sina_fut_data.rename(columns=zh_en_dict, inplace=True)

        # 日期处理
        sina_fut_data["trade_date"] = pd.to_datetime(sina_fut_data["trade_date"], errors="coerce")
        sina_fut_data.dropna(subset=["trade_date"], inplace=True)

        # 计算
        sina_fut_data["extreme_diff"] = sina_fut_data["high"] - sina_fut_data["low"]
        sina_fut_data["high_open_diff"] = sina_fut_data["high"] - sina_fut_data["open"]
        sina_fut_data["low_open_diff"] = sina_fut_data["open"] - sina_fut_data["low"]
        sina_fut_data["trend"] = np.sign(sina_fut_data["close"] - sina_fut_data["open"])

        # 排序
        sina_fut_data.sort_values("trade_date", ascending=False, inplace=True)
        fut_data = sina_fut_data.head(days).reset_index(drop=True)
        fut_data["trade_date"] = fut_data["trade_date"].dt.strftime("%Y%m%d")

        # 保存缓存
        fut_data.to_pickle(cache_file)

    # ==============================================
    # 这里统一转回中文！！！（修复点）
    # ==============================================
    sina_fut_data = sina_fut_data.rename(columns=en_zh_dict)

    # 下面所有计算都不变（满足你的需求）
    max_range = round(sina_fut_data['极值差'].max())
    min_range = round(sina_fut_data['极值差'].min())
    avg_range = round(sina_fut_data['极值差'].mean())
    range_std = round(sina_fut_data['极值差'].std())

    support = round(sina_fut_data['最低价'].mean())
    resistance = round(sina_fut_data['最高价'].mean())
    settle_price = sina_fut_data['结算价'].iloc[0]

    max_gap_up = round(sina_fut_data['高开差'].max())
    min_gap_up = round(sina_fut_data['高开差'].min())
    avg_gap_up = round(sina_fut_data['高开差'].mean())

    max_gap_down = round(sina_fut_data['低开差'].max())
    min_gap_down = round(sina_fut_data['低开差'].min())
    avg_gap_down = round(sina_fut_data['低开差'].mean())

    cv = round(range_std / avg_range, 2) if avg_range != 0 else 0
    if cv < 0.2:
        stability = f"极稳定-{cv}"
    elif cv < 0.45:
        stability = f"稳定-{cv}"
    elif cv < 0.6:
        stability = f"较稳定-{cv}"
    elif cv < 0.8:
        stability = f"不稳定-{cv}"
    else:
        stability = f"极不稳定-{cv}"

    result = {
        "压力位": resistance, "支撑位": support, "最大波动": max_range, "平均波动": avg_range,
        "最小波动": min_range, "最大高开差": max_gap_up, "最小高开差": min_gap_up,
        "平均高开差": avg_gap_up, "最大低开差": max_gap_down, "最小低开差": min_gap_down,
        "平均低开差": avg_gap_down, "前日结算价": settle_price, "标准差": range_std, "稳定性": stability
    }

    shared_data.history_data_analysis = result
    shared_data.history_trade_df = sina_fut_data

    return result, sina_fut_data  # 现在返回的就是中文列名！


if __name__ == "__main__":
    result_dict, fut_data = fetch_future_data("c2609")
    print(f'传入shared_data.history_data_analysis:\n{result_dict}\n'
          f'传入shared_trade_df:\n{fut_data}')
