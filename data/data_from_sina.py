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
        sina_fut_data = ak.futures_main_sina(symbol=ts_code)

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
    # if cv < 0.2:
    #     stability = f"极稳定-{cv}"
    # elif cv < 0.45:
    #     stability = f"稳定-{cv}"
    # elif cv < 0.6:
    #     stability = f"较稳定-{cv}"
    # elif cv < 0.8:
    #     stability = f"不稳定-{cv}"
    # else:
    #     stability = f"极不稳定-{cv}"

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

# def calc_q4_dict(df_sub, contract_code: str, trend_name: str, bin_q: int):
#     res_dict = {contract_code: {"gap_pos": {}, "gap_neg": {}}}
#     df_pos = df_sub[df_sub["开结差"] > 0].copy()
#     df_neg = df_sub[df_sub["开结差"] < 0].copy()
#     # 标记是否存在某个分箱内样本不足6条（仅用作上层判断是否扩容25天）
#     sample_not_enough = False
#
#     def single_bin_calc(sub_df, target_key: str):
#         nonlocal sample_not_enough
#         from typing import Tuple
#         total_rows = len(sub_df)
#         # ========== 新增：打印分组行数，调试空分组问题 ==========
#         # print_context(f"【调试】{trend_name}-{target_key} 有效K线行数：{total_rows}")
#         # 无数据：写入占位空字典，避免外层无key
#         if total_rows == 0:
#             print_context(f"提示：{trend_name}-{target_key} 无任何有效K线，跳过分箱")
#             return
#         # 自适应真实分箱数量：总行数少于基准分箱则用行数作为分箱数
#         real_q = bin_q if total_rows >= bin_q else total_rows
#         # print(f"{trend_name}-{target_key} 总行数{total_rows}，基准分箱{bin_q}，实际使用{real_q}分箱")
#
#         _, bin_np = pd.qcut(
#             sub_df["开结差"],
#             q=real_q,
#             retbins=True,
#             duplicates="drop"
#         )
#         bin_count = len(bin_np) - 1
#         if bin_count < 1:
#             print_context(f"警告：{trend_name}-{target_key} 分箱边界去重后无有效箱体")
#             sample_not_enough = True
#             return
#         dynamic_labels = list(range(1, bin_count + 1))
#         cut_obj, _ = pd.qcut(
#             sub_df["开结差"],
#             q=real_q,
#             labels=dynamic_labels,
#             retbins=True,
#             duplicates="drop"
#         )
#         sub_df["分箱标记"] = cut_obj
#         agg_df = sub_df.groupby("分箱标记", observed=False).agg(
#             change_max=("极值差", "max"),
#             change_min=("极值差", "min"),
#             change_avg=("极值差", "mean"),
#
#             high_open_max=("高开差", "max"),
#             high_open_min=("高开差", "min"),
#             high_open_avg=("高开差", "mean"),
#
#             low_open_max=("低开差", "max"),
#             low_open_min=("低开差", "min"),
#             low_open_avg=("低开差", "mean")
#         ).reset_index()
#
#         # 校验每个分箱样本量，单箱不足6个标记扩容标识
#         group_count = sub_df["分箱标记"].value_counts()
#         for box_idx, cnt in group_count.items():
#             if cnt < 6:
#                 sample_not_enough = True
#
#         bin_ranges: list[Tuple[float, float]] = []
#         for i in range(bin_count):
#             # ========== 修复1：保留4位小数，减少精度丢失 ==========
#             left: float = round(float(bin_np[i]), 4)
#             right: float = round(float(bin_np[i + 1]), 4)
#             rt: Tuple[float, float] = (left, right)
#             bin_ranges.append(rt)
#             # 新增调试打印生成的区间
#             # print_context(f"【调试】生成分箱区间 {target_key}: {rt}")
#
#         target_sub_dict = res_dict[contract_code][target_key]
#         for idx, row in agg_df.iterrows():
#             range_tuple: Tuple[float, float] = bin_ranges[idx]
#             inner_data = {
#                 "change": (
#                     round(float(row["change_max"]), 2),
#                     round(float(row["change_min"]), 2),
#                     round(float(row["change_avg"]), 2)
#                 ),
#                 "high_open": (
#                     round(float(row["high_open_max"]), 2),
#                     round(float(row["high_open_min"]), 2),
#                     round(float(row["high_open_avg"]), 2)
#                 ),
#                 "low_open": (
#                     round(float(row["low_open_max"]), 2),
#                     round(float(row["low_open_min"]), 2),
#                     round(float(row["low_open_avg"]), 2)
#                 )
#             }
#             target_sub_dict[range_tuple] = inner_data
#
#     # 分别计算正向、负向跳空分箱
#     single_bin_calc(df_pos, "gap_pos")
#     single_bin_calc(df_neg, "gap_neg")
#     # 返回分箱字典 + 样本不足标记
#     return res_dict, sample_not_enough
#
#
# def judge_trend(ts_code, days=20):
#     ts_code = ts_code if ts_code else shared_data.ts_code
#     base_days = days
#     use_days = base_days + 1 if base_days is not None else shared_data.target_days + 1
#     # print(f"[{ts_code}] {use_days-1}天交易历史数据分析 ..................")
#
#     # ========== 修改：农产品m/c/jd强制3分箱，震荡行情统一3分箱 ==========
#     sideways_product_list = shared_data.sideways_product_list
#     product_head = ts_code[:1].lower() if len(ts_code) >= 1 else ""
#     if product_head in sideways_product_list:
#         bin_q = 3
#         # print_context(f"震荡农产品{product_head}，固定使用3分箱计算跳空区间")
#     else:
#         market_direction = getattr(shared_data, "direction", "")
#         if market_direction == "Sideways":
#             bin_q = 3
#             # print_context(f"市场震荡行情，基准使用3分箱计算跳空区间")
#         else:
#             bin_q = 4
#             # print_context(f"趋势行情/非震荡农产品，基准使用4分箱计算跳空区间")
#
#     # 重试循环：存在分箱单箱样本不足6条则自动切换25个交易日，最多重试1次
#     final_rise_bin_result = None
#     final_fall_bin_result = None
#     final_sideways_bin_result = None
#     for run_times in range(2):
#         _, fut_df = fetch_future_data(ts_code=ts_code, days=use_days)
#         if fut_df is None:
#             print_context("行情数据拉取失败，终止分箱计算")
#             return {}, {}, {}
#         fut_df = fut_df.head(use_days).copy()
#         # 计算前一日结算、收盘价，生成跳空差值
#         fut_df["前结价"] = fut_df["结算价"].shift(-1)
#         fut_df["前收价"] = fut_df["收盘价"].shift(-1)
#         fut_df["开结差"] = fut_df["开盘价"] - fut_df["前结价"]
#         fut_df["开收差"] = fut_df["开盘价"] - fut_df["前收价"]
#
#         # 跳空类型标记函数
#         def get_gap_type(val):
#             if val > 0:
#                 return "up"
#             elif val < 0:
#                 return "down"
#             return "flat"
#         fut_df["开结类型"] = fut_df["开结差"].apply(get_gap_type)
#         fut_df["开收类型"] = fut_df["开收差"].apply(get_gap_type)
#         fut_df = fut_df.head(use_days - 1)
#         calc_gap_trend_match(df=fut_df)
#
#         # ========== 核心新增：按走势拆分三组K线 ==========
#         # 拆分当日强多(1)、强空(-1)、震荡(0)三组K线
#         df_rise = fut_df[fut_df["走势"] == 1].copy()
#         df_fall = fut_df[fut_df["走势"] == -1].copy()
#         df_sideways = fut_df[fut_df["走势"] == 0].copy()
#         # print_context(f"【调试】历史强多K线：{len(df_rise)}，强空K线：{len(df_fall)}，震荡K线：{len(df_sideways)}")
#
#         # 调用顶层独立calc_q4_dict，传入动态基准分箱参数bin_q
#         rise_bin_data, rise_sample_short = calc_q4_dict(df_rise, ts_code, "rise", bin_q)
#         fall_bin_data, fall_sample_short = calc_q4_dict(df_fall, ts_code, "fall", bin_q)
#         # 震荡统一强制3分箱
#         side_bin_data, side_sample_short = calc_q4_dict(df_sideways, ts_code, "sideways", bin_q=3)
#
#         # 任意分组存在单箱样本不足6条，扩容至25天重算
#         if rise_sample_short or fall_sample_short or side_sample_short:
#             if run_times == 0:
#                 # print_context("检测存在分箱内样本偏少，自动切换25个交易日重新计算")
#                 use_days = 25 + 1  # head(use_days-1) = 25个交易日
#                 continue
#             else:
#                 print_context("扩容至25天后仍存在样本偏少分箱，数据仅作参考")
#         # 样本达标，保存结果跳出循环
#         final_rise_bin_result = rise_bin_data
#         final_fall_bin_result = fall_bin_data
#         final_sideways_bin_result = side_bin_data
#         break
#
#     # 新增返回震荡分箱字典
#     return final_rise_bin_result, final_fall_bin_result, final_sideways_bin_result
#
# def bin_analyzer(ts_code=None, direction=None):
#     # 合约校验
#     ts_code = ts_code if ts_code is not None else shared_data.ts_code
#     if ts_code is None:
#         print_context("无效的期货品种 - 你可能没有指定具体的品种代码！")
#         exit()
#
#     # 入参direction为空时，自动读取全局shared_data.direction作为返回分支判断依据
#     if direction is None:
#         direction = getattr(shared_data, "direction", None)
#
#     # 获取开盘、昨结、昨收，计算当日开结差 + 当日开收差
#     open_info = get_open_price(ts_code)
#     open_price = open_info[ts_code]['open']
#     pre_settle = open_info[ts_code]['pre_settle']
#     pre_close = open_info[ts_code]['pre_close']
#     current_gap = round(open_price - pre_settle, 4)
#     current_close_gap = round(open_price - pre_close, 4)
#     # 组装要求的元组：(开结差值, 开收差值)
#     gap_range_val = (current_gap, current_close_gap)
#
#     # ========== 重写匹配函数：无精准匹配自动取最近区间兜底 ==========
#     def get_match_stat(source_bin_dict, target_gap):
#         contract_data = source_bin_dict[ts_code]
#         gap_val = target_gap
#         if gap_val > 0:
#             gap_key = "gap_pos"
#             target_group = contract_data["gap_pos"]
#         elif gap_val < 0:
#             gap_key = "gap_neg"
#             target_group = contract_data["gap_neg" ]
#         else:
#             # 平开无跳空
#             return None, None
#
#         match_data = None
#         min_distance = float("inf")
#         fallback_info = None
#
#         for range_tuple, stat_info in target_group.items():
#             left, right = range_tuple
#             # 区分单点区间 (x,x) 和正常左开右闭区间
#             if left == right:
#                 exact_hit = (gap_val == left)
#                 dist = abs(gap_val - left)
#             else:
#                 exact_hit = (left < gap_val <= right)
#                 mid = (left + right) / 2
#                 dist = abs(gap_val - mid)
#
#             # 精准匹配直接锁定
#             if exact_hit:
#                 match_data = stat_info
#                 break
#             # 记录距离最近的区间作为兜底
#             if dist < min_distance:
#                 min_distance = dist
#                 fallback_info = stat_info
#
#         # print_context(f"【调试】遍历区间组{gap_key}，当前跳空值{gap_val}，精准匹配：{match_data is not None}，最小差值:{min_distance:.2f}")
#         # 无精准匹配，返回距离最近的区间，杜绝空结果
#         if match_data is None and fallback_info is not None:
#             # print_context(f"【提示】无完全匹配跳空区间，采用历史最接近跳空数据兜底")
#             match_data = fallback_info
#         return gap_key, match_data
#
#     # 临时覆盖全局shared_data.direction供judge_trend计算分箱，执行完恢复原始值
#     original_dir = getattr(shared_data, "direction", None)
#     if direction is not None:
#         shared_data.direction = direction
#     try:
#         # 接收三组数据：多、空、震荡
#         final_rise_bin_result, final_fall_bin_result, final_side_bin_result = judge_trend(ts_code, days=20)
#     finally:
#         # 恢复全局变量，不污染外部环境
#         if original_dir is not None:
#             shared_data.direction = original_dir
#         elif hasattr(shared_data, "direction"):
#             delattr(shared_data, "direction")
#
#     # 匹配涨、跌、震荡分箱数据，传入当前跳空值用于距离计算
#     rise_gap_key, rise_stat = get_match_stat(final_rise_bin_result, current_gap)
#     fall_gap_key, fall_stat = get_match_stat(final_fall_bin_result, current_gap)
#     side_gap_key, side_stat = get_match_stat(final_side_bin_result, current_gap)
#
#     # 组装指定嵌套字典格式，插入gap_range放在字典最前面
#     full_rise_output = {}
#     full_fall_output = {}
#     full_side_output = {}
#     if rise_gap_key and rise_stat is not None:
#         # 把gap_range插到字典首位
#         new_rise_dict = {"gap_range": gap_range_val}
#         new_rise_dict.update(rise_stat)
#         full_rise_output[ts_code] = {"rise": {rise_gap_key: new_rise_dict}}
#     if fall_gap_key and fall_stat is not None:
#         new_fall_dict = {"gap_range": gap_range_val}
#         new_fall_dict.update(fall_stat)
#         full_fall_output[ts_code] = {"fall": {fall_gap_key: new_fall_dict}}
#     # ========== 新增震荡输出字典 ==========
#     if side_gap_key and side_stat is not None:
#         new_side_dict = {"gap_range": gap_range_val}
#         new_side_dict.update(side_stat)
#         full_side_output[ts_code] = {"sideways": {side_gap_key: new_side_dict}}
#     # 分支返回逻辑：同时返回多、空、震荡三组
#
#     return full_rise_output, full_fall_output, full_side_output





if __name__ == "__main__":
    fut_code = "m2609"
    # jd属于震荡农产品，强制设置direction=Sideways，触发3分箱
    shared_data.direction = "Fall"
    res1, res2 = fetch_future_data(ts_code=fut_code)
    exit()
    print(f"{res1}\n{res2}")
    print(f"公共模块：{shared_data.history_data_analysis}")
    # 接收三组返回值
    rise_data, fall_data, side_data = bin_analyzer(ts_code=fut_code)
    print(f"=====今日开盘与历史数据匹配结果=====\n做多参考数据： {rise_data}\n做空参考数值： {fall_data}\n震荡参考数值： {side_data}")
    data = calc_stable_amplitude(res2)
    print(data)