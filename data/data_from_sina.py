"""
本模块利用akshare从新浪网获取期货商品的交易数据；
通过分析数据自定义该期货品种的交易参数，并将其传递到公共模块变量：shared_data.order_param_dict
交易参数主要是多、空、震荡三个方向
适配盘中动态切换合约(m2609/c2609等)，多品种缓存隔离，杜绝数据串用
"""
import os
from datetime import datetime
import akshare as ak
import pandas as pd
from public import shared_data
from public.print_context import print_context
from public.shared_data import get_data_cache_dir
from data.get_quote import get_open_price
from public.jiaoyisuo import get_future_info

COEFFICIENT = 0  # 倍率系数

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
    pd.set_option('display.width', 2000)
    pd.set_option('display.max_colwidth', None)
    pd.set_option('display.float_format', '{:.0f}'.format)
    pd.set_option('display.colheader_justify', 'left')  # 表头左对齐

setup_pandas_display()

def calc_gap_trend_match(df):
    """
    统计跳空方向 和 日内走势(1涨/-1跌/0震荡) 的吻合度
    返回字典：结算跳空吻合统计、收盘跳空吻合统计
    """
    # 只过滤有效行（shift产生最后一行NaN丢弃）
    df_valid = df.dropna(subset=["开结类型"])

    # 1. 结算跳空 vs 日内走势匹配
    match_settle = 0
    mismatch_settle = 0
    for _, row in df_valid.iterrows():
        gap = row["开结类型"]
        trend = row["走势"]
        # 高开+收涨 / 低开+收跌 = 吻合
        if (gap == "up" and trend == 1) or (gap == "down" and trend == -1):
            match_settle += 1
        else:
            mismatch_settle += 1
    total_settle = match_settle + mismatch_settle
    settle_match_rate = round(match_settle / total_settle, 2) if total_settle > 0 else 0

    # 2. 前收盘价跳空 vs 日内走势匹配
    match_close = 0
    mismatch_close = 0
    for _, row in df_valid.iterrows():
        gap = row["开收类型"]
        trend = row["走势"]
        if (gap == "up" and trend == 1) or (gap == "down" and trend == -1):
            match_close += 1
        else:
            mismatch_close += 1
    total_close = match_close + mismatch_close
    close_match_rate = round(match_close / total_close, 2) if total_close > 0 else 0

    return {
        "结算跳空_吻合数量": match_settle,
        "结算跳空_背离数量": mismatch_settle,
        "结算跳空_吻合率": settle_match_rate,
        "收盘跳空_吻合数量": match_close,
        "收盘跳空_背离数量": mismatch_close,
        "收盘跳空_吻合率": close_match_rate,
        "有效样本行数": total_settle
    }

def calc_stable_amplitude(fut_df):
    """
    从fetch_future_data返回的res2(fut_df)计算【稳定振幅区间】
    df必须包含列："极值差"
    返回中文key字典，可以直接update进market_ctx，eval表达式直接写中文变量
    """
    if fut_df is None or fut_df.empty:
        return {
            "稳定振幅下限": None,
            "稳定振幅上限": None,
            "历史最大振幅": None,
            "历史最小振幅": None,
            "历史平均振幅": None,
            "历史振幅标准差": None
        }

    ser = fut_df["极值差"].dropna()
    q1 = ser.quantile(0.25)
    q3 = ser.quantile(0.75)
    iqr = q3 - q1

    # IQR 过滤异常值：剔除过小、过大异动样本
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    valid_ser = ser[(ser >= lower_bound) & (ser <= upper_bound)]

    if valid_ser.empty:
        # 过滤后全部干掉，退回到全部样本
        valid_ser = ser

    stable_low = round(valid_ser.min(), 2)
    stable_high = round(valid_ser.max(), 2)

    return {
        "稳定振幅下限": stable_low,
        "稳定振幅上限": stable_high,
        "历史最大振幅": round(ser.max(), 2),
        "历史最小振幅": round(ser.min(), 2),
        "历史平均振幅": round(ser.mean(), 2),
        "历史振幅标准差": round(ser.std(), 2)
    }

def fetch_future_data(ts_code=None, days=None):
    global COEFFICIENT

    # 1. 优先入参，无入参则取公共变量（盘中动态切换依赖shared_data.ts_code）
    if ts_code is None:
        ts_code = shared_data.ts_code
    days = days if days is not None else shared_data.target_days
    if not isinstance(ts_code, str) or len(ts_code) < 4:
        print_context("❌ 错误：期货合约代码无效")
        return None, None
    COEFFICIENT = get_future_info(symbol=ts_code).get("coefficient", 0)  # 获取期货品种对应的倍率系数*差价以计算差价盈亏
    today = datetime.now().strftime("%Y%m%d")
    # 获取数据缓存目录路径:\\auto_futures\data\futures_data\sina_data
    cache_folder = get_data_cache_dir()
    cache_folder = os.path.join(cache_folder, "sina_data")
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
            required_cols = ["极值差", "高开差", "低开差", "日期", "走势"]
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
        # print_context(f"🌐 线上拉取历史行情数据 | 合约: {ts_code}")
        # days = getattr(shared_data, "target_days", 10)  # 会影响judge_trend()函数的取值
        sina_fut_data = None
        try:
            sina_fut_data = ak.futures_main_sina(symbol=ts_code)
        except ValueError as e:
            # akshare内部read_json读取空字符串抛出此异常（远月合约/新浪返回空）
            print_context(f"⚠️新浪接口返回空JSON，未检查到合约 [{ts_code}] 历史数据，异常:{str(e)}")
            return None, None
        except Exception as e:
            print_context(f"⚠️线上拉取新浪行情异常 {ts_code}: {str(e)}")
            return None, None

        # print(sina_fut_data.head(20))
        # 列名转英文，用于内部计算
        sina_fut_data.rename(columns=zh_en_dict, inplace=True)
        # 日期清洗
        sina_fut_data["trade_date"] = pd.to_datetime(sina_fut_data["trade_date"], errors="coerce")
        sina_fut_data.dropna(subset=["trade_date"], inplace=True)
        if sina_fut_data.empty:
            print_context(f"❌ 拉取数据为空 | 合约: {ts_code}")
            return None, None

        # =============== 核心修复1：重写走势trend计算逻辑 ===============
        # 计算衍生指标（英文列）
        sina_fut_data["extreme_diff"] = sina_fut_data["high"] - sina_fut_data["low"]
        sina_fut_data["high_open_diff"] = sina_fut_data["high"] - sina_fut_data["open"]
        sina_fut_data["low_open_diff"] = sina_fut_data["open"] - sina_fut_data["low"]

        # 按规则计算走势
        high_minus_low = sina_fut_data["high_open_diff"] - sina_fut_data["low_open_diff"]
        low_minus_high = sina_fut_data["low_open_diff"] - sina_fut_data["high_open_diff"]
        cond_rise = high_minus_low * COEFFICIENT > 400
        cond_fall = low_minus_high * COEFFICIENT > 400

        sina_fut_data["trend"] = 0
        sina_fut_data.loc[cond_rise, "trend"] = 1
        sina_fut_data.loc[cond_fall, "trend"] = -1

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
        print_context(f"💾 成功获取[{ts_code}]合约{days}天历史交易数据，缓存路径 >>>{cache_file}")

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
    rise_fall = fut_data.iloc[0]['收盘价'] - fut_data.iloc[-1]['收盘价']
    trend = 0
    if rise_fall > 0:
        trend = 1
    elif rise_fall < 0:
        trend = -1
    # 波动稳定性判断
    cv = round(range_std / avg_range, 2) if avg_range != 0 else 0
    stability = cv

    # 组装结果并写入公共变量
    result = {"ts_code": ts_code,
        "历史压力位": resistance, "历史支撑位": support, "历史最大振幅": max_range, "历史平均振幅": avg_range,
        "历史最小振幅": min_range, "历史最大高开差": max_gap_up, "历史最小高开差": min_gap_up,
        "历史平均高开差": avg_gap_up, "历史最大低开差": max_gap_down, "历史最小低开差": min_gap_down,
        "历史平均低开差": avg_gap_down, "前日结算价": settle_price, "历史标准差": range_std, "历史稳定性": stability,
        "历史收盘价差": rise_fall, "历史走势": trend
    }

    shared_data.history_data_analysis = result
    shared_data.history_trade_df = fut_data
    fut_data = calc_stable_amplitude(fut_data)
    # print(fut_data)
    result.update(fut_data)
    # print(result)
    return result, fut_data


if __name__ == "__main__":
    fut_code = "jd2612"
    res1, res2 = fetch_future_data(ts_code=fut_code)

    print(f"{res1}\n{res2}")
