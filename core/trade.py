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

trans_map = {
    "tscode": "ts_code",
    "日期": "trade_datetime",
    "今日开盘价": "today_open",
    "昨日结算价": "pre_settle_hist",
    '前日结算价': "pre_settle_hist",
    "昨日收盘价": "pre_close",
    "交易费": "trade_fee",
    "盈亏系数": "coefficient",
    "大盘走势": "market_trend",
    "历史压力位": "history_resistance",
    "历史支撑位": "history_support",
    "历史最大振幅": "history_max_amp",
    "历史平均振幅": "history_avg_amp",
    "历史最小振幅": "history_min_amp",
    "历史最大高开差": "history_max_high_open",
    "历史最小高开差": "history_min_high_open",
    "历史平均高开差": "history_avg_high_open",
    "历史最大低开差": "history_max_low_open",
    "历史最小低开差": "history_min_low_open",
    "历史平均低开差": "history_avg_low_open",
    "历史标准差": "history_std_dev",
    "历史稳定性": "history_stability",
    "历史收盘价差": "history_close_diff",
    "历史走势": "history_trend",
    "稳定振幅下限": "stable_amp_low",
    "稳定振幅上限": "stable_amp_high",
    "历史振幅标准差": "history_amp_std",
    "今日最高价": "today_high",
    "今日最低价": "today_low",
    "总记录数": "total_rows",
    "窗口记录数": "ticks_per_window",
    "首单交易价": "today_open",
    "最新价": "last_price",
    "交易日走势": "day_trend",
    "最新K线走势": "latest_k_trend",
    "交易日价差": "day_price_diff",
    "最新K线价差": "latest_k_diff",
    "交易日振幅": "day_amplitude",

}

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


def get_db_data(ts_code, k_minutes=None):
    k_minutes = shared_data.k_minutes if k_minutes is None else k_minutes
    ticks_per_window = int(k_minutes * 60 / shared_data.get_price_interval)
    ts_code = ts_code if ts_code is not None else shared_data.ts_code
    df = None
    while True:
        try:
            df = read_db(full_ts_code=ts_code)
            # 读到df并且不为空，才跳出循环
            if df is not None and not df.empty and len(df) >= 5:
                break
        except Exception:
            pass
        print(f"\r[{ts_code}]等待tick数据，目前已采集即时价格数：{len(df)}条。", flush=True)
        sleep(1)

    if df is None or df.empty:
        print(f"\r暂时没有对应品种[{ts_code}]的今日交易数据库文件！", flush=True, end="")
        return

    total_rows = len(df)
    max_today_price = df["price"].max()
    min_today_price = df["price"].min()
    today_amplitude = max_today_price - min_today_price
    last_price = df.iloc[0]["price"]
    long_direction = None
    short_direction = None

    open_first_price = shared_data.open_price[ts_code]["今日开盘价"]
    print_context(f"今日开盘价 - {open_first_price}  （截止：{datetime.now().strftime('%H:%M:%S')}）\n"
                  f"最高交易价:{max_today_price} - 最低交易价：{min_today_price} - 最新价：{last_price} - 最高震幅 ：{today_amplitude}\n")


    if total_rows <= ticks_per_window:
        short_window_start_price = last_price
    else:
        short_window_df = df.head(ticks_per_window)
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
        "总记录数": total_rows,
        "窗口记录数": ticks_per_window,
        "今日最高价": max_today_price,
        "今日最低价": min_today_price,
        "首单交易价": open_first_price,
        "最新价": last_price,
        "交易日走势": long_direction,
        "最新K线走势": short_direction,
        "交易日价差": long_price_diff,
        "最新K线价差": short_price_diff,
        "交易日振幅": today_amplitude,
    }




def rename_dict_keys(src_dict, mapping=None):
    if mapping is None:
        mapping = trans_map
    new_dict = {}
    # 每一条：先写中文原key，紧跟着写英文别名，实现成对相邻
    for old_key, val in src_dict.items():
        new_dict[old_key] = val
        if old_key in mapping:
            eng_key = mapping[old_key]
            new_dict[eng_key] = val
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
    market_ctx["大盘走势"] = getattr(shared_data, "direction", "rise").lower()

    if shared_data.history_data_analysis is None or ts_code not in shared_data.history_data_analysis:
        from data.data_from_sina import fetch_future_data
        history_data, _ = fetch_future_data(ts_code)
    else:
        history_data = shared_data.history_data_analysis
    market_ctx.update(history_data)

    # -------- 重点：中文key全部保留，追加英文别名key --------
    market_ctx = rename_dict_keys(market_ctx, trans_map)

    # db_data返回的是中文键，同样执行追加英文别名
    db_data = get_db_data(ts_code=ts_code)
    db_data_with_eng = rename_dict_keys(db_data, trans_map)
    market_ctx.update(db_data_with_eng)

    eval_ctx = BASE_EVAL_TPL.copy()
    eval_ctx.update(market_ctx)

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


def calc_trade_pnl(trade_dir: str, cur_price: float, loss_price: float, profit_price: float, coefficient: float, lot_size:int, total_fee: float):
    """计算止损、止盈对应的实际盈亏（已扣除双向手续费，纳入手数lot_size）"""
    pnl_loss = 0.0
    pnl_profit = 0.0
    if trade_dir == "rise":
        pnl_loss = (loss_price - cur_price) * coefficient * lot_size - total_fee
        pnl_profit = (profit_price - cur_price) * coefficient * lot_size - total_fee
    elif trade_dir == "fall":
        pnl_loss = (cur_price - loss_price) * coefficient * lot_size - total_fee
        pnl_profit = (cur_price - profit_price) * coefficient * lot_size - total_fee
    return {
        "pnl_loss": round(pnl_loss, 2),
        "pnl_profit": round(pnl_profit, 2)
    }


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
            if reasons:
                if not no_print:
                    print_context(f"当前不满足交易条件，请等待...\n具体原因解析： {' '.join(reasons)}")
                    no_print = True
                sleep(1)
                continue

            no_print = False
            print_context(f"现在可以进行正常期货交易，拟交易品种 - {ts_code}")

            signal_res, detail_map = select_best_trade_rule(ts_code)

            if signal_res:
                params = signal_res[ts_code]
                trade_dir = params.get("trade_direction")
                loss_price = params.get("loss_price")  # 止损价
                profit_price = params.get("profit_price")  # 止盈价
                rule_id = params["rule_id"]

                ok_flag, fail_list = detail_map[rule_id]
                print_context(f"✅命中策略:{rule_id},不满足条件:{ok_flag}")

                if trade_dir and loss_price is not None and profit_price is not None:
                    cur_price = auto_trade(trade_dir)  # 根据trade_dir点击多空控件同时返回即时交易价
                    fut_info = get_future_info(ts_code, cur_price)
                    total_fee = fut_info.get('fee', 0) * 2
                    coefficient = fut_info.get('coefficient', 0)
                    lot_size = getattr(shared_data, "lot_size", 1)   # 获取手数，默认1

                    # 方向合法性校验标记
                    price_valid = True
                    if trade_dir == "rise":
                        if any((loss_price >= cur_price, profit_price <= cur_price)):
                            print(f"\r设置云止损单错误：交易方向-买多，交易价-{cur_price}，止损价-{loss_price}，止盈价-{profit_price}")
                            logger.warning(f"[{ts_code}]多单价位校验失败，cur_price={cur_price}, loss={loss_price}, profit={profit_price}")
                            price_valid = False
                            sleep(0.2)
                    elif trade_dir == "fall":
                        if any((loss_price <= cur_price, profit_price >= cur_price)):
                            print(f"\r设置云止损单错误：交易方向-卖空，交易价‑{cur_price}，止损价‑{loss_price}，止盈价‑{profit_price}")
                            logger.warning(f"[{ts_code}]空单价位校验失败，cur_price={cur_price}, loss={loss_price}, profit={profit_price}")
                            price_valid = False
                            sleep(0.2)

                    if not price_valid:
                        continue

                    # ========= 纳入lot_size手数，计算止盈盈亏值 =========
                    pnl_result = calc_trade_pnl(
                        trade_dir=trade_dir,
                        cur_price=cur_price,
                        loss_price=loss_price,
                        profit_price=profit_price,
                        coefficient=coefficient,
                        lot_size=lot_size,
                        total_fee=total_fee
                    )
                    calc_profit_val = pnl_result["pnl_profit"]   # 计算出的止盈盈亏(元)

                    # 业务分支逻辑
                    if calc_profit_val < 50:
                        # 止盈盈亏小于50
                        shared_data.pre_profit = 50
                        shared_data.pre_loss = 0.0
                        # 云全部置0
                        final_cloud_profit = 0
                        final_cloud_loss = 0
                        final_cloud_break = 0

                    elif calc_profit_val > 200:
                        # 止盈盈亏大于200
                        shared_data.pre_profit = calc_profit_val * 1.2
                        shared_data.pre_loss = 0.0
                        final_cloud_profit = profit_price
                        final_cloud_loss = 0
                        final_cloud_break = 200

                    else:
                        # 50 <= calc_profit_val <=200
                        shared_data.pre_profit = calc_profit_val
                        shared_data.pre_loss = 0.0
                        final_cloud_profit = profit_price
                        final_cloud_loss = 0
                        final_cloud_break = 0

                    # 写入loss_profit_param
                    shared_data.loss_profit_param["云止盈单"] = final_cloud_profit
                    shared_data.loss_profit_param["云止损单"] = final_cloud_loss
                    shared_data.loss_profit_param["云保本单"] = final_cloud_break

                    # 下单时务必打印完整设置信息
                    set_msg = (
                        f"【下单设置详情】品种:{ts_code},方向:{trade_dir},手数lot_size={lot_size}\n"
                        f"成交参考价cur_price={cur_price}\n"
                        f"计算止盈盈亏calc_profit_val={calc_profit_val:.2f}元\n"
                        f"shared_data.pre_profit={shared_data.pre_profit:.2f}, shared_data.pre_loss={shared_data.pre_loss:.2f}\n"
                        f"云止盈单={final_cloud_profit},云止损单={final_cloud_loss},云保本单={final_cloud_break}"
                    )
                    print_context(set_msg)
                    # logger.info(set_msg)

                    # 设置云止损UI调用
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
                    logger.warning("策略参数不全，跳过下单")
            else:
                print(f"\r本轮没有命中策略！", end="")
                for r_name, (ok, fails) in detail_map.items():
                    print_context(f"❌策略[{r_name}]未通过，不满足条件：{fails}")

            sleep(5)
        except Exception as e:
            logger.exception(f"order_loop异常")
            sleep(1)


if __name__ == "__main__":
    # order(ts_code="m2609")
    market_ctx = get_market_ctx(ts_code="dj2609")
    print(market_ctx)
