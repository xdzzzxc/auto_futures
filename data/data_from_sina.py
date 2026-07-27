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
from public.shared_data import get_data_cache_dir

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
    统计跳空方向 和 日内走势(1涨/-1跌) 的吻合度
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


def fetch_future_data(ts_code=None, days=None):
    # 1. 优先入参，无入参则取公共变量（盘中动态切换依赖shared_data.ts_code）
    if ts_code is None:
        ts_code = shared_data.ts_code
    days = days if days is not None else shared_data.target_days
    if not isinstance(ts_code, str) or len(ts_code) < 4:
        print_context("❌ 错误：期货合约代码无效")
        return None, None

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
        # print_context(f"🌐 线上拉取历史行情数据 | 合约: {ts_code}")
        # days = getattr(shared_data, "target_days", 10)  # 会影响judge_trend()函数的取值
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
        print_context(f"💾 成功获取[{ts_code}]合约历史数据，缓存路径 >>>{cache_file}")

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
        "平均低开差": avg_gap_down, "前日结算价": settle_price, "标准差": range_std, "稳定性": stability,
        "涨跌": rise_fall, "走势": trend
    }

    shared_data.history_data_analysis = result
    shared_data.history_trade_df = fut_data
    # print(fut_data)
    return result, fut_data

def calc_q4_dict(df_sub, contract_code: str, trend_name: str, bin_q: int):
    res_dict = {contract_code: {"gap_pos": {}, "gap_neg": {}}}
    df_pos = df_sub[df_sub["开结差"] > 0].copy()
    df_neg = df_sub[df_sub["开结差"] < 0].copy()
    # 标记是否存在某个分箱内样本不足6条（仅用作上层判断是否扩容25天）
    sample_not_enough = False

    def single_bin_calc(sub_df, target_key: str):
        nonlocal sample_not_enough
        from typing import Tuple, Dict
        total_rows = len(sub_df)
        # 无数据直接跳过
        if total_rows == 0:
            print(f"提示：{trend_name}-{target_key} 无任何有效K线，跳过分箱")
            return
        # 自适应真实分箱数量：总行数少于基准分箱则用行数作为分箱数
        real_q = bin_q if total_rows >= bin_q else total_rows
        # print(f"{trend_name}-{target_key} 总行数{total_rows}，基准分箱{bin_q}，实际使用{real_q}分箱")

        _, bin_np = pd.qcut(
            sub_df["开结差"],
            q=real_q,
            retbins=True,
            duplicates="drop"
        )
        bin_count = len(bin_np) - 1
        if bin_count < 1:
            print(f"警告：{trend_name}-{target_key} 分箱边界去重后无有效箱体")
            sample_not_enough = True
            return
        dynamic_labels = list(range(1, bin_count + 1))
        cut_obj, _ = pd.qcut(
            sub_df["开结差"],
            q=real_q,
            labels=dynamic_labels,
            retbins=True,
            duplicates="drop"
        )
        sub_df["分箱标记"] = cut_obj
        agg_df = sub_df.groupby("分箱标记", observed=False).agg(
            change_max=("极值差", "max"),
            change_min=("极值差", "min"),
            change_avg=("极值差", "mean"),

            high_open_max=("高开差", "max"),
            high_open_min=("高开差", "min"),
            high_open_avg=("高开差", "mean"),

            low_open_max=("低开差", "max"),
            low_open_min=("低开差", "min"),
            low_open_avg=("低开差", "mean")
        ).reset_index()

        # 校验每个分箱样本量，单箱不足6标记扩容标识
        group_count = sub_df["分箱标记"].value_counts()
        for box_idx, cnt in group_count.items():
            if cnt < 6:
                # print(f"警告：{trend_name}-{target_key} 分箱{box_idx}仅{cnt}条数据，样本偏少")
                sample_not_enough = True

        bin_ranges: list[Tuple[float, float]] = []
        for i in range(bin_count):
            left: float = round(float(bin_np[i]), 2)
            right: float = round(float(bin_np[i + 1]), 2)
            rt: Tuple[float, float] = (left, right)
            bin_ranges.append(rt)

        target_sub_dict = res_dict[contract_code][target_key]
        for idx, row in agg_df.iterrows():
            range_tuple: Tuple[float, float] = bin_ranges[idx]
            inner_data = {
                "change": (
                    round(float(row["change_max"]), 2),
                    round(float(row["change_min"]), 2),
                    round(float(row["change_avg"]), 2)
                ),
                "high_open": (
                    round(float(row["high_open_max"]), 2),
                    round(float(row["high_open_min"]), 2),
                    round(float(row["high_open_avg"]), 2)
                ),
                "low_open": (
                    round(float(row["low_open_max"]), 2),
                    round(float(row["low_open_min"]), 2),
                    round(float(row["low_open_avg"]), 2)
                )
            }
            target_sub_dict[range_tuple] = inner_data

    # 分别计算正向、负向跳空分箱
    single_bin_calc(df_pos, "gap_pos")
    single_bin_calc(df_neg, "gap_neg")
    # 返回分箱字典 + 样本不足标记
    return res_dict, sample_not_enough


def judge_trend(ts_code, days=20):
    ts_code = ts_code if ts_code else shared_data.ts_code
    base_days = days
    use_days = base_days + 1 if base_days is not None else shared_data.target_days + 1
    print(f"[{ts_code}] {use_days-1}天交易历史数据分析 ..................")

    # 动态判定分箱数量：震荡+农产品(m/c/jd)用3分箱，其余4分箱
    sideways_product_list = {"m", "c", "jd"}
    product_head = ts_code[:1].lower() if len(ts_code) >= 1 else ""
    market_direction = getattr(shared_data, "direction", "")
    if market_direction == "Sideways" and product_head in sideways_product_list:
        bin_q = 3
        print_context(f"市场震荡行情+品种{product_head}，基准使用3分箱计算跳空区间")
    else:
        bin_q = 4
        print_context(f"趋势行情/非震荡农产品，基准使用4分箱计算跳空区间")

    # 重试循环：存在分箱单箱样本不足6条则自动切换25个交易日，最多重试1次
    final_rise_bin_result = None
    final_fall_bin_result = None
    for run_times in range(2):
        _, fut_df = fetch_future_data(ts_code=ts_code, days=use_days)
        if fut_df is None:
            print_context("行情数据拉取失败，终止分箱计算")
            return {}, {}
        fut_df = fut_df.head(use_days).copy()
        # 计算前一日结算、收盘价，生成跳空差值
        fut_df["前结价"] = fut_df["结算价"].shift(-1)
        fut_df["前收价"] = fut_df["收盘价"].shift(-1)
        fut_df["开结差"] = fut_df["开盘价"] - fut_df["前结价"]
        fut_df["开收差"] = fut_df["开盘价"] - fut_df["前收价"]

        # 跳空类型标记函数
        def get_gap_type(val):
            if val > 0:
                return "up"
            elif val < 0:
                return "down"
            return "flat"
        fut_df["开结类型"] = fut_df["开结差"].apply(get_gap_type)
        fut_df["开收类型"] = fut_df["开收差"].apply(get_gap_type)
        fut_df = fut_df.head(use_days - 1)
        calc_gap_trend_match(df=fut_df)

        # 拆分当日收涨、收跌两组K线
        df_rise = fut_df[fut_df["走势"] == 1].copy()
        df_fall = fut_df[fut_df["走势"] == -1].copy()

        # 调用顶层独立calc_q4_dict，传入动态基准分箱参数bin_q
        rise_bin_data, rise_sample_short = calc_q4_dict(df_rise, ts_code, "rise", bin_q)
        fall_bin_data, fall_sample_short = calc_q4_dict(df_fall, ts_code, "fall", bin_q)

        # 任意分组存在单箱样本不足6条，扩容至25天重算
        if rise_sample_short or fall_sample_short:
            if run_times == 0:
                print_context("检测存在分箱内样本偏少，自动切换25个交易日重新计算")
                use_days = 25 + 1  # head(use_days-1) = 25个交易日
                continue
            else:
                print_context("扩容至25天后仍存在样本偏少分箱，数据仅作参考")
        # 样本达标，保存结果跳出循环
        final_rise_bin_result = rise_bin_data
        final_fall_bin_result = fall_bin_data
        break

    # print(f"===== 涨势[gap_pos]{len(final_rise_bin_result[ts_code]['gap_pos'])}分箱  涨势[gap_neg]"
    #       f"{len(final_rise_bin_result[ts_code]['gap_neg'])}分箱=====\n{final_rise_bin_result}")

    # print(f"===== 跌势[gap_pos]{len(final_fall_bin_result[ts_code]['gap_pos'])}分箱  跌势[gap_neg]"
    #       f"{len(final_fall_bin_result[ts_code]['gap_neg'])}分箱=====\n{final_fall_bin_result}")

    return final_rise_bin_result, final_fall_bin_result



if __name__ == "__main__":
    fut_code = "jd2609"
    judge_trend(ts_code=fut_code, days=20)