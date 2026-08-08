from time import sleep
from datetime import datetime
from data.data_from_sina import bin_analyzer
# from core.market_ctx import get_market_ctx
from data.get_quote import get_open_price
from public import shared_data
from data.data_from_sina import fetch_future_data, bin_analyzer
from data.db_price import read_db
from public.jiaoyisuo import get_future_info
from public import shared_data
from public.print_context import print_context
from sendmsg.weichat_push import send_msg
from public.shared_data import click_position, is_trade_status, trade_flag
from log.trade_log import setup_trade_loggers
from enum import Enum
from core.condition_pool import config_pool
from core.monitor import auto_trade
import signal
logger = setup_trade_loggers()

# 创建eval()函数命名空间
BASE_EVAL_TPL = {
    "__builtins__": {"abs": abs, "min": min, "max": max, "len": len},
}

# ======为本程序注册一个程序：收到退出程序时发出信号以安全停止======
stop_flag = False
def sig_handler(signum, frame):
    global stop_flag
    stop_flag = True
signal.signal(signal.SIGINT, sig_handler)
# ===========================
def get_db_data(ts_code, k_minutes=5):
    k_minutes = shared_data.k_minutes if k_minutes is None else k_minutes
    # N分钟窗口对应的tick数量，强制int，避免浮点数传入head
    tick_per_window = int(k_minutes * 60 / shared_data.get_price_interval)
    ts_code = ts_code if ts_code is not None else shared_data.ts_code

    df = read_db(full_ts_code=ts_code)
    if df.empty:
        print("No recorders in df")
        # 不要exit(0)，抛异常交给上层处理
        raise RuntimeError(f"{ts_code}: empty kline dataframe")

    all_kline_num = len(df)
    max_today_price = df["price"].max()
    min_today_price = df["price"].min()
    today_amplitude = max_today_price - min_today_price
    long_direction = None   # 当日全天走势 rise/fall/sideways
    short_direction = None  # 最近N分钟走势 rise/fall/sideways

    # df.iloc[0] → 最新tick；df.iloc[-1] → 今日开盘第一条tick（全天最早）
    open_first_price = df.iloc[-1]["price"]   # 今日开市第一条tick价格
    last_price = df.iloc[0]["price"]          # 当前最新tick价格

    if all_kline_num <= tick_per_window:
        # 开市时长不足k_minutes分钟，全部数据作为短期窗口
        short_window_first_price = last_price
    else:
        # head取最新 tick_per_window 条tick；iloc[-1]取这组里时间最旧的那一根（窗口起始价格）
        short_window_df = df.head(tick_per_window)
        short_window_first_price = short_window_df.iloc[-1]["price"]

    # 价差计算
    long_price_diff = last_price - open_first_price
    short_price_diff = last_price - short_window_first_price

    # 全天方向
    if long_price_diff > 0:
        long_direction = "rise"
    elif long_price_diff < 0:
        long_direction = "fall"
    else:
        long_direction = "sideways"

    # 短期N分钟方向
    if short_price_diff > 0:
        short_direction = "rise"
    elif short_price_diff < 0:
        short_direction = "fall"
    else:
        short_direction = "sideways"

    return {
        # "ts_code": ts_code,
        "max_today_price": max_today_price,
        "min_today_price": min_today_price,
        "open_first_price": open_first_price,
        "last_price": last_price,
        "long_direction": long_direction,
        "short_direction": short_direction,
        "long_price_diff": long_price_diff,
        "short_price_diff": short_price_diff,
        "today_amplitude": today_amplitude
        # "tick_per_window": tick_per_window,
        # "total_ticks": all_kline_num
    }

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
    market_ctx = rename_dict_keys(market_ctx, trans_map)
    db_data = get_db_data(ts_code=ts_code)
    market_ctx.update(db_data)
    eval_ctx = BASE_EVAL_TPL.copy()
    eval_ctx.update(market_ctx)
    return eval_ctx

def check_rule(rule_info: dict, market_ctx: dict) -> tuple[bool, list[str]]:
    if not rule_info.get("enabled", False):
        return False, ["策略enabled关闭"]

    cond_list = rule_info.get("conditions", [])
    fail_conds = []

    for expr in cond_list:
        try:
            # 直接使用传入完整market_ctx，不再重建env_globals
            result = eval(expr, market_ctx)
            if not result:
                fail_conds.append(expr)
        except NameError as e:
            fail_conds.append(f"{expr} 变量缺失:{str(e)}")
        except Exception as e:
            fail_conds.append(f"{expr} 执行异常:{str(e)}")

    meet_all = len(fail_conds) == 0
    return meet_all, fail_conds


def scan_all_rules(rule_pool: dict, market_ctx: dict) -> tuple[list[tuple[str, int]], dict]:
    detail_map = {}
    hit_list = []
    default_priority = 0

    for rule_name, rule_data in rule_pool.items():
        ok, fails = check_rule(rule_data, market_ctx)
        detail_map[rule_name] = (ok, fails)
        if ok:
            prio = rule_data.get("priority", default_priority)
            hit_list.append((rule_name, prio))

    return hit_list, detail_map


def get_highest_priority_rule(hit_list: list[tuple[str, int]]) -> str | None:
    if not hit_list:
        return None
    hit_list.sort(key=lambda x: x[1], reverse=True)
    return hit_list[0][0]


_NO_EVAL = {"trade_direction"}


def _eval_price_expr(expr, market_ctx: dict):
    if expr is None:
        return None
    if isinstance(expr, (int, float)):
        return expr

    try:
        val = eval(expr, market_ctx)
        return val
    except Exception as e:
        print(f"【表达式计算失败】expr={expr}, error={e}")
        return None


def select_best_trade_rule(ts_code: str) -> dict:
    """
    返回 {ts_code: {rule_id, priority, trade_direction, trade_price, profit_price, loss_price}}
    无命中返回 {}
    """
    ctx = get_market_ctx(ts_code)
    hit_list, _ = scan_all_rules(config_pool, ctx)
    best_rule_name = get_highest_priority_rule(hit_list)

    if best_rule_name is None:
        return {}

    rule_data = config_pool[best_rule_name]
    raw_params = rule_data["trade_params"]
    prio = rule_data.get("priority", 0)

    out_params = {}
    out_params["rule_id"] = best_rule_name
    out_params["priority"] = prio

    for k, v in raw_params.items():
        if k in _NO_EVAL:
            # 黑名单：不eval，直接复制原始值
            out_params[k] = v
        else:
            # 其余全部执行eval表达式计算
            out_params[k] = _eval_price_expr(v, ctx)

    return {ts_code: out_params}

def order(ts_code=None):
    global stop_flag
    ts_code = shared_data.ts_code if ts_code is None else ts_code
    while not stop_flag:
        # trade_period = trade_flag()  # 检测是否在交易时段
        # if not trade_period:
        #     sleep(1)
        #     logger.info(f"目前处于合法交易时段，等待交易的期货品种 - {ts_code}")
        #     continue
        # trade_status = is_trade_status()  # 检测目前是否有品种交易中
        # if trade_status:
        #     sleep(1)
        #     continue

        eval_ctx = get_market_ctx(ts_code)  # 获取命名空间字典供后续eval()使用
        logger.info(f"目前处于合法交易时段，等待交易的期货品种 - {ts_code}")

        # =====调用函数检查条件池，获取下单参数=====
        signal_res = select_best_trade_rule(ts_code)
        # print_context(f"程序获取的最佳下单参数：{signal_res}")
        if signal_res:
            # 开始下单：点击下单、设置云止损止盈
            params = signal_res[ts_code]
            auto_trade(trade_dir=params["trade_direction"])

            logger.info(f"命中策略，下单参数：{params}")
            # 业务校验：关键参数不为None再执行下单
            if params.get("trade_direction") is not None and params.get("trade_price") is not None:
                # 此处写你的下单逻辑
                pass
            else:
                logger.warning("策略参数计算存在空值，跳过本次信号")
        else:
            logger.info("无策略命中")

        sleep(5)



# ===================== 启动 =====================
if __name__ == "__main__":
    order(ts_code="m2609")
    # result = get_market_ctx(ts_code="m2609")
    # print(result)