from time import sleep
from datetime import datetime, timedelta
from data.get_quote import get_open_price
from data.db_price import read_db
from public.jiaoyisuo import get_future_info
from public import shared_data
from public.print_context import print_context
from sendmsg.weichat_push import send_msg
from public.shared_data import click_position, is_trade_status, trade_flag
from log.trade_log import setup_trade_loggers
from core.connect_ths import set_loss_profit
import ast
from core.condition_pool import config_pool
from core.monitor import auto_trade
import signal

logger = setup_trade_loggers()

# 创建eval()函数命名空间
BASE_EVAL_TPL = {
    "__builtins__": {"abs": abs, "min": min, "max": max, "len": len, "int": int, "map": map, "any": any,
                     "all": all, "round": round},
}

# ======信号处理：安全退出======
stop_flag = False


def sig_handler(signum, frame):
    global stop_flag
    stop_flag = True


signal.signal(signal.SIGINT, sig_handler)
signal.signal(signal.SIGTERM, sig_handler)


def extract_expr_vars(expr_str: str):
    """提取eval表达式中的变量名，忽略字面量字符串"""
    try:
        tree = ast.parse(expr_str, mode="eval")
        vars_set = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                vars_set.add(node.id)
        return sorted(vars_set)
    except Exception:
        return []


def get_db_data(ts_code, k_minutes=5):
    k_minutes = shared_data.k_minutes if k_minutes is None else k_minutes
    tick_per_window = int(k_minutes * 60 / shared_data.get_price_interval)
    ts_code = ts_code if ts_code is not None else shared_data.ts_code
    try:
        df = read_db(full_ts_code=ts_code)
    except Exception:
        df = None
    if df is None or df.empty:
        print("No records in db")
        raise RuntimeError(f"{ts_code}: empty kline dataframe")

    total_rows = len(df)
    max_today_price = df["price"].max()
    min_today_price = df["price"].min()
    today_amplitude = max_today_price - min_today_price

    long_direction = None
    short_direction = None

    # open_first_price = df.iloc[-1]["price"]  # 今日第一条交易价
    open_first_price = shared_data.open_price[ts_code]["今日开盘价"]
    # print("今日首单交易价（今日开盘价）:", open_first_price)
    print_context(f"今日开盘价 - {open_first_price}\n"
                  f"今日最高交易价（截止：{datetime.now().strftime('%H:%M:%S')}） - {max_today_price}")
    last_price = df.iloc[0]["price"]

    if total_rows <= tick_per_window:
        short_window_start_price = last_price
    else:
        short_window_df = df.head(tick_per_window)
        short_window_start_price = short_window_df.iloc[-1]["price"]

    long_price_diff = last_price - open_first_price
    short_price_diff = last_price - short_window_start_price

    if long_price_diff > 0:
        long_direction = "rise"
    elif long_price_diff < 0:
        long_direction = "fall"
    else:
        long_direction = "sideways"

    if short_price_diff > 0:
        short_direction = "rise"
    elif short_price_diff < 0:
        short_direction = "fall"
    else:
        short_direction = "sideways"

    return {
        "今日最高价": max_today_price,
        "今日最低价": min_today_price,
        "首单交易价": open_first_price,
        "最新价": last_price,
        "交易日走势": long_direction,
        "最新K线走势": short_direction,  # 最新K线走势（自定义为1分钟、5分钟不等）
        "交易日价差": long_price_diff,  # 最新价与开盘价差
        "最新K线价差": short_price_diff,  #
        "交易日振幅": today_amplitude,
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
    "周期涨跌幅": "period_net_change",
    "周期方向": "period_direction",
    "tscode": "ts_code"
}


def rename_dict_keys(src_dict, mapping=None):
    if mapping is None:
        mapping = trans_map
    new_dict = {}
    for old_key, val in src_dict.items():
        new_key = mapping.get(old_key, old_key)
        new_dict[new_key] = val
    return new_dict


def get_market_ctx(ts_code):
    market_ctx = {}
    ts_code = ts_code if ts_code is not None else shared_data.ts_code
    if ts_code is None:
        raise RuntimeError("ts_code is None")
    fut_info = get_future_info(symbol=ts_code)
    if shared_data.open_price is None or ts_code not in shared_data.open_price:
        open_info = get_open_price(ts_code)
    else:
        open_info = shared_data.open_price
    market_ctx["shared_data"] = shared_data
    market_ctx.update(open_info[ts_code])
    market_ctx["交易费"] = fut_info["fee"]
    market_ctx["盈亏系数"] = fut_info["coefficient"]
    market_ctx["大盘走势"] = getattr(shared_data, "direction", "rise").lower()  # 测试时的默认值

    # 保留history_data，但不再调用bin_analyzer分箱
    if shared_data.history_data_analysis is None or ts_code not in shared_data.history_data_analysis:
        from data.data_from_sina import fetch_future_data
        history_data, _ = fetch_future_data(ts_code)
    else:
        history_data = shared_data.history_data_analysis
    market_ctx.update(history_data)

    # ========= 删除整块bin_analyzer分箱、flatten_bin_data扁平化逻辑 =========

    market_ctx = rename_dict_keys(market_ctx, trans_map)
    db_data = get_db_data(ts_code=ts_code)
    market_ctx.update(db_data)

    eval_ctx = BASE_EVAL_TPL.copy()
    eval_ctx.update(market_ctx)

    # 仅更新全局快照，不做clear，业务逻辑不依赖此全局
    shared_data.market_ctx_dict.update(eval_ctx)
    return eval_ctx


def check_rule(rule_info: dict, market_ctx: dict):
    if not rule_info.get("enabled", False):
        return False, [{"expr": "", "reason": "策略enabled关闭", "actual": {}}]
    cond_list = rule_info.get("conditions", [])
    fail_items = []

    for expr in cond_list:
        try:
            res = eval(expr, market_ctx)
            if not res:
                # 条件不满足，提取变量，拿到实际值
                var_names = extract_expr_vars(expr)
                actual_map = {}
                for vn in var_names:
                    if vn in market_ctx:
                        actual_map[vn] = market_ctx[vn]
                    else:
                        actual_map[vn] = "<missing>"
                fail_items.append({
                    "expr": expr,
                    "reason": "条件返回False",
                    "actual": actual_map
                })
        except NameError as e:
            fail_items.append({
                "expr": expr,
                "reason": f"变量缺失:{str(e)}",
                "actual": {}
            })
        except Exception as e:
            fail_items.append({
                "expr": expr,
                "reason": f"执行异常:{str(e)}",
                "actual": {}
            })
    ok = len(fail_items) == 0
    return ok, fail_items


def scan_all_rules(pool: dict, market_ctx: dict):
    detail_map = {}
    hit_list = []
    default_priority = 0
    for rule_name, rule_data in pool.items():
        ok, fails = check_rule(rule_data, market_ctx)
        detail_map[rule_name] = (ok, fails)
        if ok:
            prio = rule_data.get("priority", default_priority)
            hit_list.append((prio, rule_name))
    hit_list.sort(key=lambda x: -x[0])
    hit_rule_names = [name for (p, name) in hit_list]
    return hit_rule_names, detail_map


def get_highest_priority_rule(hit_list):
    if not hit_list:
        return None
    return hit_list[0]


_NO_EVAL = {"trade_direction"}


def eval_price_expression(expr, market_ctx: dict):
    if expr is None:
        return None
    if isinstance(expr, (int, float)):
        return expr
    try:
        val = eval(expr, market_ctx)
        return val
    except Exception as e:
        print(f"【表达式计算失败】expr={expr}, err={e}")
        return None


def select_best_trade_rule(ts_code: str, ctx=None):
    """
    返回 (result_dict, detail_map)
    result_dict: {ts_code: {rule_id, priority, trade_params...}}，无命中返回 {}
    """
    if ctx is None:
        ctx = get_market_ctx(ts_code)

    hit_rules, detail_map = scan_all_rules(config_pool, ctx)
    best_rule_name = get_highest_priority_rule(hit_rules)

    if best_rule_name is None:
        return {}, detail_map

    rule_data = config_pool[best_rule_name]
    trade_params_raw = rule_data["trade_params"]
    priority = rule_data.get("priority", 0)

    out = {
        "rule_id": best_rule_name,
        "priority": priority,
    }
    for k, v in trade_params_raw.items():
        if k in _NO_EVAL:
            out[k] = v
        else:
            out[k] = eval_price_expression(v, ctx)

    return {ts_code: out}, detail_map


def is_valid_trade_time():
    with shared_data.valid_time_lock:
        now = datetime.now()
        valid_time = shared_data.valid_time
        if valid_time is None:
            return True
        if now >= valid_time:
            return True
        return False


def order(ts_code=None):
    global stop_flag
    ts_code = ts_code if ts_code is not None else shared_data.ts_code
    no_print = False

    while not stop_flag:
        cond_time = trade_flag()
        cond_hold = is_trade_status()
        cond_cool = is_valid_trade_time()
        reasons = []
        if not cond_time:
            reasons.append(f"期货休市中-[{datetime.now().strftime('%H:%M:%S')}]")
        if cond_hold:
            reasons.append(f"|当前有持仓 - [{shared_data.ts_code}] |")
        if not cond_cool:
            reasons.append("请在上一次交易后的规定时间再进行交易！")
        try:
            # if reasons:
            #     if not no_print:
            #         print_context(f"当前不满足交易条件，请等待...\n具体原因解析： {' '.join(reasons)}")
            #         no_print = True
            #     sleep(1)
            #     continue

            no_print = False
            print_context(f"现在可以进行正常期货交易，拟交易品种 - {ts_code}")

            signal_res, detail_map = select_best_trade_rule(ts_code)
            print_context(f"signal_res: {signal_res}")
            if signal_res:
                params = signal_res[ts_code]
                trade_dir = params.get("trade_direction")
                loss_price = params.get("loss_price")  # 止损价
                profit_price = params.get("profit_price")  # 止盈价
                rule_id = params["rule_id"]

                ok_flag, fail_list = detail_map[rule_id]
                print_context(f"✅命中策略:{rule_id},不满足条件:{ok_flag}")

                if trade_dir and loss_price is not None and profit_price is not None:
                    shared_data.loss_profit_param["云止损单"] = loss_price
                    shared_data.loss_profit_param["云止盈单"] = profit_price
                    cur_price = auto_trade(trade_dir)  # 根据trade_dir点击多空控件同时返回即时交易价
                    # 计算盈亏设置是否合理：修改手动固定止损止盈值和相应价位
                    fut_info = get_future_info(ts_code, cur_price)
                    total_fee = fut_info.get('fee', 0) * 2
                    coefficient = fut_info.get('coefficient', 0)
                    if trade_dir == "rise":
                        if any((loss_price >= cur_price, profit_price <= cur_price)):
                            print(
                                f"\r设置云止损单错误：交易方向-买多，交易价-{cur_price}，止损价-{loss_price}，止盈价-{profit_price}")
                            sleep(0.2)
                            continue
                        if abs((profit_price - cur_price) * coefficient) - total_fee < 50:
                            shared_data.pre_profit = 50
                            shared_data.loss_profit_param["云止盈单"] = 0
                            shared_data.loss_profit_param["云止损单"] = 0
                        if abs((loss_price - cur_price) * coefficient) - total_fee < 50:
                            shared_data.loss_profit_param["云止损单"] = 0

                    if trade_dir == "fall" and any((loss_price <= cur_price, profit_price >= cur_price)):
                        print(
                            f"\r设置云止损单错误：交易方向-卖空，交易价‑{cur_price}，止损价‑{loss_price}，止盈价‑{profit_price}")
                        sleep(0.2)
                        continue
                    # 设置云止损
                    shared_data.ui_busy = True
                    try:
                        set_loss_profit()
                    finally:
                        shared_data.ui_busy = False

                    with shared_data.valid_time_lock:
                        shared_data.valid_time = datetime.now() + timedelta(seconds=shared_data.valid_trade_interval)
                        print_context(f"下次交易有效时间起点：{shared_data.valid_time}")
                else:
                    print_context("参数不全，跳过本次下单")
                    # logger.warning("策略参数不全，跳过下单")
            else:
                print(f"\r本轮没有命中策略！", end="")
                for r_name, (ok, fails) in detail_map.items():
                    print_context(f"❌策略[{r_name}]未通过，不满足条件：{fails}")

            sleep(5)

        except Exception as e:
            logger.exception(f"order_loop异常")
            sleep(1)


if __name__ == "__main__":
    order(ts_code="m2609")
    # get_db_data(ts_code="jd2609")
    print(get_market_ctx(ts_code="m2609"))
    # select_best_trade_rule(ts_code="c2609")