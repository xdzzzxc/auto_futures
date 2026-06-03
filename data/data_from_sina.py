"""
本模块利用akshare从新浪网获取期货商品的交易数据；
通过分析数据自定义该期货品种的交易参数，并将其传递到公共模块变量：shared_data.order_param_dict
交易参数主要是多、空两个方向
适配盘中动态切换合约(m2609/c2609等)，多品种缓存隔离，杜绝数据串用
"""
import os
from datetime import datetime
import akshare as ak
import pandas as pd
import numpy as np
from public import shared_data
from public.print_context import print_context

# 列名中英文映射
zh_en_dict = {
    "日期": "trade_date", "开盘价": "open", "最高价": "high", "最低价": "low", "收盘价": "close",
    "成交量": "volume", "动态结算价": "settle_price", "持仓量": "open_interest", "结算价": "settle_price"
}
en_zh_dict = {v: k for k, v in zh_en_dict.items()}


def setup_pandas_display():
    pd.set_option('display.unicode.ambiguous_as_wide', True)
    pd.set_option('display.unicode.east_asian_width', True)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', None)
    pd.set_option('display.float_format', '{:.2f}'.format)

setup_pandas_display()


def fetch_future_data(ts_code=None):
    # 1. 优先入参，无入参则取公共变量（盘中动态切换依赖shared_data.ts_code）
    if ts_code is None:
        ts_code = shared_data.ts_code
    if not isinstance(ts_code, str) or len(ts_code) < 4:
        print_context("❌ 错误：期货合约代码无效")
        return None, None

    today = datetime.now().strftime("%Y%m%d")
    cache_folder = os.path.join(os.getcwd(), "futures_data", "sina_data")
    os.makedirs(cache_folder, exist_ok=True)

    # 2. 缓存文件名：【合约代码_日期】，多品种彻底隔离，核心防串数据
    cache_file = os.path.join(cache_folder, f"{ts_code}_{today}.pkl")

    # 3. 清理：只删除非今日的过期缓存，同天所有品种缓存全部保留
    for filename in os.listdir(cache_folder):
        file_path = os.path.join(cache_folder, filename)
        if os.path.isfile(file_path) and filename.endswith(".pkl"):
            if today not in filename:
                try:
                    os.remove(file_path)
                except Exception as e:
                    print_context(f"⚠️ 清理旧缓存失败 {filename}：{str(e)}")

    # 4. 读取缓存 + 合法性二次校验（双重保险）
    if os.path.exists(cache_file):
        print_context(f"✅ 读取本地缓存 | 合约: {ts_code} >>> {cache_file}")
        try:
            fut_data = pd.read_pickle(cache_file)
            # 强制校验必须包含的列，不存在就重新拉取
            required_cols = ["极值差", "高开差", "低开差", "日期"]
            for col in required_cols:
                if col not in fut_data.columns:
                    raise ValueError(f"缺少列: {col}")
            if fut_data.empty:
                raise ValueError("缓存数据为空")
        except Exception as e:
            print_context(f"⚠️ 缓存数据异常，自动重新拉取 | 原因: {str(e)}")
            fut_data = None
    else:
        fut_data = None

    # 5. 无有效缓存 → 线上拉取数据、计算指标
    if fut_data is None:
        print_context(f"🌐 线上拉取历史行情数据 | 合约: {ts_code}")
        days = getattr(shared_data, "target_days", 10)
        sina_fut_data = ak.futures_main_sina(symbol=ts_code)

        # 列名转英文，用于内部计算
        sina_fut_data.rename(columns=zh_en_dict, inplace=True)
        # 日期清洗
        sina_fut_data["trade_date"] = pd.to_datetime(sina_fut_data["trade_date"], errors="coerce")
        sina_fut_data.dropna(subset=["trade_date"], inplace=True)
        if sina_fut_data.empty:
            print_context(f"❌ 拉取数据为空 | 合约: {ts_code}")
            return None, None

        # =============== 核心修复：先计算所有指标，再转中文 ===============
        # 计算衍生指标（英文列）
        sina_fut_data["extreme_diff"] = sina_fut_data["high"] - sina_fut_data["low"]
        sina_fut_data["high_open_diff"] = sina_fut_data["high"] - sina_fut_data["open"]
        sina_fut_data["low_open_diff"] = sina_fut_data["open"] - sina_fut_data["low"]
        sina_fut_data["trend"] = np.sign(sina_fut_data["close"] - sina_fut_data["open"])

        # 按日期倒序，截取指定天数
        sina_fut_data.sort_values("trade_date", ascending=False, inplace=True)
        fut_data = sina_fut_data.head(days).copy()

        # 转回中文列名（包含计算好的指标一起转）
        add_zh_dict = {
            "extreme_diff": "极值差",
            "high_open_diff": "高开差",
            "low_open_diff": "低开差",
            "trend": "走势"
        }
        en_zh_dict.update(add_zh_dict)
        fut_data.rename(columns=en_zh_dict, inplace=True)
        fut_data["日期"] = fut_data["日期"].dt.strftime("%Y%m%d")

        # 保存缓存
        fut_data.to_pickle(cache_file)
        print_context(f"💾 新数据已以[{os.path.basename(cache_file)}]文件格式缓存,保存路径 >>> {cache_file}")

    # 6. 指标计算（统一使用当前合约的有效数据）
    max_range = round(fut_data['极值差'].max())
    min_range = round(fut_data['极值差'].min())
    avg_range = round(fut_data['极值差'].mean())
    range_std = round(fut_data['极值差'].std())

    support = round(fut_data['最低价'].min())
    resistance = round(fut_data['最高价'].max())
    settle_price = fut_data['结算价'].iloc[0]

    max_gap_up = round(fut_data['高开差'].max())
    min_gap_up = round(fut_data['高开差'].min())
    avg_gap_up = round(fut_data['高开差'].mean())

    max_gap_down = round(fut_data['低开差'].max())
    min_gap_down = round(fut_data['低开差'].min())
    avg_gap_down = round(fut_data['低开差'].mean())

    # 波动稳定性判断
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

    # 组装结果并写入公共变量
    result = {
        "压力位": resistance, "支撑位": support, "最大波动": max_range, "平均波动": avg_range,
        "最小波动": min_range, "最大高开差": max_gap_up, "最小高开差": min_gap_up,
        "平均高开差": avg_gap_up, "最大低开差": max_gap_down, "最小低开差": min_gap_down,
        "平均低开差": avg_gap_down, "前日结算价": settle_price, "标准差": range_std, "稳定性": stability
    }

    shared_data.history_data_analysis = result
    shared_data.history_trade_df = fut_data

    return result, fut_data


if __name__ == "__main__":
    # 本地测试：模拟盘中切换合约
    shared_data.target_days = 10

    # 第一次：m2609
    shared_data.ts_code = "m2609"
    res1, df1 = fetch_future_data()
    print("===== m2609 数据 =====", res1, "\n")
    print(df1)
    # 第二次：切换 c2609（自动新建缓存，不会混用m2609数据）
    shared_data.ts_code = "c2609"
    res2, df2 = fetch_future_data()
    print("===== c2609 数据 =====", res2)
    print(df2)