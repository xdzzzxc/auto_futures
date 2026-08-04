from data.get_quote import get_open_price
from public import shared_data
from data.data_from_sina import fetch_future_data, bin_analyzer

trans_map = {
    "压力位": "resistance",
    "支撑位": "support",
    "最大波动": "max_range",
    "平均波动": "avg_range",
    "最小波动": "min_range",
    "最大高开差": "max_high_gap",
    "最小高开差": "min_high_gap",
    "平均高开差": "avg_high_gap",
    "最大低开差": "max_low_gap",
    "最小低开差": "min_low_gap",
    "平均低开差": "avg_low_gap",
    "前日结算价": "pre_settle_hist",
    "标准差": "std_dev",
    "稳定性": "stability",
    "周期涨跌": "period_net_change",
    "周期走势": "period_trend",
    "tscode": "ts_code"
}
# 修改中文键名
def rename_dict_keys(src_dict, map_rule=None):
    if map_rule is None:
        map_rule = trans_map
    new_dict = {}
    for old_key, val in src_dict.items():
        new_key = map_rule.get(old_key, old_key)
        new_dict[new_key] = val
    return new_dict

# 分箱字典扁平化供eval使用
def flatten_bin_data(prefix: str, data: dict, target_ctx: dict):
    """
    prefix: 前缀 rise_ / fall_ / side_
    data: 单一类分箱字典
    target_ctx: eval上下文字典，原地写入
    """
    for k, v in data.items():
        new_key = f"{prefix}{k}_"
        if isinstance(v, dict):
            flatten_bin_data(new_key, v, target_ctx)
        elif isinstance(v, tuple):
            length = len(v)
            val_min = v[0]
            val_mid = v[1] if length >= 2 else val_min
            val_max = v[2] if length >= 3 else val_mid
            target_ctx[f"{new_key}min"] = val_min
            target_ctx[f"{new_key}mid"] = val_mid
            target_ctx[f"{new_key}max"] = val_max
        else:
            target_ctx[new_key.rstrip("_")] = v

# 获取期货品种市场行情
def get_market_ctx(ts_code):
    market_ctx = {}  # 局部命名空间
    ts_code = ts_code if ts_code is not None else shared_data.ts_code
    if ts_code is None:
        print("ts_code is None, program has stopped!")
        exit(0)
    if shared_data.open_price is None or ts_code not in shared_data.open_price:
        open_info = get_open_price(ts_code)  # 执行获取期货品种的今日开盘信息
    else:
        open_info = shared_data.open_price
    market_ctx.update(open_info[ts_code])
    market_ctx["direction"] = getattr(shared_data, "direction", "sideways").lower()
    market_ctx["gap_percent"] = round((open_info[ts_code]["open"] - open_info[ts_code]["pre_settle"])/open_info[ts_code]["pre_settle"], 4)
    if shared_data.history_data_analysis is None or ts_code not in shared_data.history_data_analysis:
        history_data, _ = fetch_future_data(ts_code)

    else:
        history_data = shared_data.history_data_analysis
    market_ctx.update(history_data)

    # =================分箱操作代码返回数据处理====================
    bin_rise, bin_fall, bin_side = bin_analyzer(ts_code)
    # 上涨分箱
    if ts_code in bin_rise and "rise" in bin_rise[ts_code]:
        rise_data = bin_rise[ts_code]["rise"]
        flatten_bin_data("rise_", rise_data, market_ctx)
    else:
        print(f"⚠️ {ts_code} rise分箱数据缺失，跳过扁平化")

    # 下跌分箱
    if ts_code in bin_fall and "fall" in bin_fall[ts_code]:
        fall_data = bin_fall[ts_code]["fall"]
        flatten_bin_data("fall_", fall_data, market_ctx)
    else:
        print(f"⚠️ {ts_code} fall分箱数据缺失，跳过扁平化")

    # 震荡分箱
    if ts_code in bin_side and "sideways" in bin_side[ts_code]:
        side_data = bin_side[ts_code]["sideways"]
        flatten_bin_data("side_", side_data, market_ctx)
    else:
        print(f"⚠️ {ts_code} sideways分箱数据缺失，跳过扁平化")
    # flatten_bin_data("rise_", rise_data, market_ctx)
    # flatten_bin_data("fall_", fall_data, market_ctx)
    # flatten_bin_data("side_", side_data, market_ctx)
    market_ctx = rename_dict_keys(market_ctx, trans_map)
    return market_ctx

if __name__ == '__main__':
    print(get_market_ctx(ts_code="m2609"))