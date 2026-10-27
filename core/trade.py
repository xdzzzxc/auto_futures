import os
import ast
import time
import threading
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
from ruamel.yaml import YAML

from data.get_quote import get_open_price
from data.db_price import read_db
from public.jiaoyisuo import get_future_info
from public import shared_data
from public.print_context import print_context
from public.shared_data import (
    click_position,
    is_trade_status,
    trade_flag,
    is_cooling,
    variables_rlock
)
from core.connect_ths import set_loss_profit
from core.monitor import auto_trade
from core.private import get_user_today_trade_stat
from audio.play_alert import *
import signal
import traceback


yaml = YAML()
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=4, offset=2)

# 无需eval计算的key白名单
GLOBAL_NO_EVAL_KEYS = {
    "priority",
    "enable",
    "comment",
    "trade_direction",
    "pre_profit",
    "pre_loss",
}
_NO_EVAL = {}

trans_map = {
    "tscode": "ts_code",
    "日期": "trade_datetime",
    "今日开盘价": "today_open",
    "昨日结算价": "pre_settle_hist",
    '前日结算价': "pre_settle_hist",
    "昨日收盘价": "pre_close",
    "交易费": "trade_fee",
    "夜市": "night_trading",
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
    "第一位高值价": "above1_price",
    "第二位高值价": "above2_price",
    "第一位低值价": "below1_price",
    "第二位低值价": "below2_price",
    "交易所": "exchange",
    "期货代码": "ths_tscode",
    "K线时长": "k_minutes",
    "手数": "lots",
    "获取价格频率": "get_price_interval",
    "小时": "hour",
    "分钟": "minute",
    "固止盈200": "profit_value_200",
    "固止损20": "loss_value_20",
    "固止盈150": "profit_value_150",
    "固止损500": "loss_value_500",
    "固止盈100": "profit_value_100",
    "固止盈80": "profit_value_80",
    "固止盈50": "profit_value_50",
    "今日最大高开差": "today_max_high_open",
    "今日平均高开差": "today_avg_high_open",
    "今日最大低开差": "today_max_low_open",
    "今日平均低开差": "today_avg_low_open",
    "中盘开盘数据统计": "middle_session_from_open",
    "中盘中位数": "median_price",
    "中盘中位数据统计": "middle_session_from_median",
    "交易状态": "is_trade_status",
    "冷却期": "is_cooling"
}

BASE_EVAL_TPL = {
    "__builtins__": {
        "abs": abs,
        "min": min,
        "max": max,
        "len": len,
        "int": int,
        "map": map,
        "any": any,
        "all": all,
        "round": round
    },
}

_counter_lock = threading.Lock()


def is_user_reach_max_limit(user_type: int) -> tuple[bool, int, int]:
    """
    判断当前用户是否到达今日平仓上限
    return (是否超限,今日计数,最大允许次数)
    """
    today_cnt, max_cnt = get_user_today_trade_stat(user_type)
    return today_cnt >= max_cnt, today_cnt, max_cnt


stop_flag = False


def sig_handler(signum, frame):
    global stop_flag
    stop_flag = True


signal.signal(signal.SIGINT, sig_handler)
signal.signal(signal.SIGTERM, sig_handler)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CFG_POOL_PATH = os.path.join(_BASE_DIR, "cfg_pool.yaml")
_last_cfg_mtime = 0.0
config_pool = None


def reset_temp_params_in_yaml(yaml_path: str = CFG_POOL_PATH):
    try:
        p = Path(yaml_path).resolve()
        print_context(f"📂 当前操作的yaml绝对路径：{p}")
        print_context(f"📄 文件是否存在：{p.exists()}")

        with variables_rlock:
            with open(yaml_path, "r", encoding="utf-8") as f:
                cfg = yaml.load(f) or {}

            print_context(f"🔍读取到的temp_params原值：{cfg.get('temp_params')}")

            if "temp_params" not in cfg or not isinstance(cfg["temp_params"], dict):
                cfg["temp_params"] = {}

            cfg["temp_params"]["temp_profit"] = None
            cfg["temp_params"]["temp_loss"] = None

            with open(yaml_path, "w", encoding="utf-8") as f:
                yaml.dump(cfg, f)

            with open(yaml_path, "r", encoding="utf-8") as f:
                check_cfg = yaml.load(f) or {}

        print_context(f"✅写入后校验 temp_params：{check_cfg.get('temp_params')}")
        print_context("✅开仓完成，已重置yaml中temp_params，恢复默认冷却时间")
    except Exception as e:
        print_context(f"❌重置yaml temp_params失败: {str(e)}")


def sync_temp_params(new_pool: dict):
    """
    热加载完成后同步临时止盈止损参数
    temp_profit / temp_loss：仅【有持仓】并且参数不为null时，更新shared_data.pre_profit/pre_loss
    valid_trade_interval：无论有无持仓，参数不为null就更新shared_data.valid_trade_interval
    """
    temp_params = new_pool.get("temp_params", {})
    temp_profit = temp_params.get("temp_profit")
    temp_loss = temp_params.get("temp_loss")
    temp_valid_trade_interval = temp_params.get("valid_trade_interval")
    lots = temp_params.get("temp_lots")

    with shared_data.dict_rlock:
        if temp_valid_trade_interval is not None:
            try:
                shared_data.valid_trade_interval = float(temp_valid_trade_interval)
                print_context(
                    f"✅[临时参数热更新] valid_trade_interval 更新为 {shared_data.valid_trade_interval}分钟 - (交易冷却期)")
            except (ValueError, TypeError):
                print_context(f"❌[临时参数] temp_valid_trade_interval 数值解析失败: {temp_valid_trade_interval}")

        if not is_trade_status():
            print_context("[temp_params] 当前无持仓，忽略临时止盈止损参数")
            return

        lots = shared_data.tscode_lots_dict.get(shared_data.ts_code, 1)
        if temp_profit is not None:
            try:
                tp_val = float(temp_profit) * lots
                shared_data.pre_profit = tp_val
                shared_data.trade_menu_dict["pre_profit"] = tp_val
                print_context(f"✅[临时参数热更新] [{lots}手{shared_data.ts_code}] pre_profit 更新为 {tp_val:.2f}")
            except (ValueError, TypeError):
                print_context(f"❌[临时参数] temp_profit 数值解析失败: {temp_profit}")

        if temp_loss is not None:
            try:
                tl_val = float(temp_loss) * lots
                shared_data.pre_loss = tl_val
                shared_data.trade_menu_dict["pre_loss"] = tl_val
                print_context(f"✅[临时参数热更新] [{lots}手{shared_data.ts_code}] pre_loss 更新为 {tl_val:.2f}")
            except (ValueError, TypeError):
                print_context(f"❌[临时参数] temp_loss 数值解析失败: {temp_loss}")


def load_config_pool(yaml_path: str = CFG_POOL_PATH) -> dict:
    """
    从yaml加载条件策略池，返回和原config_pool完全同结构字典
    :param yaml_path: 配置文件路径
    :return: config_pool dict
    """
    try:
        with variables_rlock:
            with open(yaml_path, "r", encoding="utf-8") as f:
                pool = yaml.load(f)
            if pool is None:
                print_context("⚠️策略yaml文件为空，返回空策略池")
                return {}
            strategy_count = len(pool) - (1 if "common_conditions" in pool else 0)
            print_context(
                f"\n✅成功加载策略配置文件 {yaml_path}，共读取 {strategy_count} 条策略  [ {datetime.now().strftime('%H:%M:%S')} ]")
            return pool
    except FileNotFoundError:
        print_context(f"❌找不到策略配置文件:{yaml_path}")
        return {}
    except yaml.YAMLError as ye:
        print_context(f"❌YAML语法解析错误：{str(ye)}")
        return {}
    except Exception as e:
        print_context(f"加载策略池异常：{str(e)}")
        return {}


def reload_config_pool(yaml_path: str = CFG_POOL_PATH) -> dict:
    """热重载yaml策略，更新全局config_pool，外部可直接调用"""
    global config_pool, _last_cfg_mtime
    new_pool = load_config_pool(yaml_path)
    if new_pool:
        config_pool = new_pool
        _last_cfg_mtime = os.stat(yaml_path).st_mtime
        sync_temp_params(new_pool)
    return config_pool


def auto_reload_cfg_if_changed():
    """检测cfg_pool.yaml文件是否被修改，变更则自动reload，无变更直接跳过"""
    global _last_cfg_mtime
    if not os.path.exists(CFG_POOL_PATH):
        return
    try:
        mtime = os.stat(CFG_POOL_PATH).st_mtime
        if mtime > _last_cfg_mtime:
            print_context("\n🔍检测到cfg_pool.yaml已修改，执行热重载...")
            reload_config_pool(CFG_POOL_PATH)
    except Exception as e:
        print_context(f"\n检测配置文件变更异常：{e}")


def wait_position_filled(target_ts_code: str, max_wait_sec=60, poll_interval=1.0) -> bool:
    """
    等待报单真实成交，轮询持仓列表检测目标合约
    :param target_ts_code: 合约代码，例 MA2611
    :param max_wait_sec: 最大等待撮合秒数
    :param poll_interval: 轮询间隔秒
    :return True=检测到持仓；False=超时未成交
    """
    start = time.time()
    print_context(f"开始等待[{target_ts_code}]成交，最大等待{max_wait_sec}秒……")
    while time.time() - start < max_wait_sec:
        try:
            pos_list = click_position()
            pos_codes = [item.get("ts_code", "").upper() for item in pos_list]
            if target_ts_code.upper() in pos_codes:
                print_context(f"✅检测到持仓[{target_ts_code}]，报单已经成交，继续设置云止损止盈")
                return True
        except Exception as e:
            print_context(f"读取持仓异常继续轮询: {str(e)}")
        time.sleep(poll_interval)
    print_context(f"❌等待[{target_ts_code}]成交超时{max_wait_sec}秒，未检测到持仓，放弃设置云止损止盈保本单")
    return False


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

    max_retries = 5
    counts = 0
    while counts <= max_retries:
        try:
            df = read_db(full_ts_code=ts_code)
        except Exception as e:
            print(f"\r[{ts_code}]读取数据库异常: {str(e)}", flush=True)
            df = None

        if df is not None and not df.empty and len(df) >= 5:
            break

        current_len = len(df) if df is not None else 0
        if counts % (max_retries * shared_data.get_price_interval) == 0:
            print(f"\r[{ts_code}]等待tick数据，目前已采集即时价格数：{current_len}条。", flush=True)
        time.sleep(shared_data.get_price_interval)
        counts += 1

    if df is None or df.empty:
        print(f"暂时没有对应品种[{ts_code}]的今日交易数据！")
        return None

    total_rows = len(df)
    max_today_price = df["price"].max()
    min_today_price = df["price"].min()
    today_amplitude = max_today_price - min_today_price
    last_price = df.iloc[0]["price"]

    if shared_data.open_price is None or ts_code not in shared_data.open_price:
        get_open_price(ts_code)
        open_first_price = shared_data.open_price[ts_code]["今日开盘价"]
    else:
        open_first_price = shared_data.open_price[ts_code]["今日开盘价"]

    try:
        open_first_price = float(open_first_price)
    except (TypeError, ValueError):
        print_context(f"[{ts_code}]开盘价数据异常，无法转为数值：{open_first_price}")
        return None

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

    price_vc = df["price"].value_counts()
    above_open = price_vc[price_vc.index > open_first_price].head(2)
    below_open = price_vc[price_vc.index < open_first_price].head(2)

    above1_price = above_open.index[0] if len(above_open) >= 1 else None
    above2_price = above_open.index[1] if len(above_open) >= 2 else None
    below1_price = below_open.index[0] if len(below_open) >= 1 else None
    below2_price = below_open.index[1] if len(below_open) >= 2 else None

    print("\n")
    print_context(f"高于开盘价的前两个价位：{above1_price} {above2_price}\n低于开盘价的前两个价位：{below1_price} {below2_price}")

    today_max_high_open = None
    today_avg_high_open = None
    today_max_low_open = None
    today_avg_low_open = None
    if total_rows >= 90 * (60 / shared_data.get_price_interval):
        high_diff = df["price"] - open_first_price
        low_diff = open_first_price - df["price"]
        above_mask = df["price"] > open_first_price
        below_mask = df["price"] < open_first_price

        if above_mask.any():
            today_max_high_open = round(high_diff[above_mask].max(), 2)
            today_avg_high_open = round(high_diff[above_mask].mean(), 2)
        if below_mask.any():
            today_max_low_open = round(low_diff[below_mask].max(), 2)
            today_avg_low_open = round(low_diff[below_mask].mean(), 2)

    def calc_after_10am_stats(data_df, base_price):
        after_10_df = data_df[data_df["dt"].dt.time >= datetime.strptime("10:00:00", "%H:%M:%S").time()].copy()
        print_context(f"10:00:00以后价格表：\n{after_10_df}")
        if after_10_df.empty:
            return {
                "cnt_above": None, "cnt_below": None, "cnt_eq": None, "total": 0,
                "pct_above": None, "pct_below": None, "direction": None
            }
        cnt_above = int((after_10_df["price"] > base_price).sum())
        cnt_below = int((after_10_df["price"] < base_price).sum())
        cnt_eq = int((after_10_df["price"] == base_price).sum())
        total = len(after_10_df)
        pct_above = round(cnt_above / total, 3)
        pct_below = round(cnt_below / total, 3)
        diff = pct_above - pct_below
        if diff > 0.05:
            direction = "rise"
        elif diff < -0.05:
            direction = "fall"
        else:
            direction = "sideways"
        return {
            "cnt_above": cnt_above,
            "cnt_below": cnt_below,
            "cnt_eq": cnt_eq,
            "total": total,
            "pct_above": pct_above,
            "pct_below": pct_below,
            "direction": direction
        }

    middle_session_from_open = calc_after_10am_stats(df, open_first_price)
    after_10_df = df[df["dt"].dt.time >= datetime.strptime("10:00:00", "%H:%M:%S").time()].copy()
    median_price = round(after_10_df["price"].median(), 2) if not after_10_df.empty else None
    print_context(f"10:00:00以后中位数：{median_price}")
    middle_session_from_median = calc_after_10am_stats(df, median_price)
    print_context(f"stats_median_base数据展示：\n{middle_session_from_median}")

    return {
        "总记录数": total_rows,
        "窗口记录数": ticks_per_window,
        "今日最高价": max_today_price,
        "今日最低价": min_today_price,
        "首单交易价": open_first_price,
        "今日最大高开差": today_max_high_open,
        "今日平均高开差": today_avg_high_open,
        "今日最大低开差": today_max_low_open,
        "今日平均低开差": today_avg_low_open,
        "最新价": last_price,
        "交易日走势": long_direction,
        "最新K线走势": short_direction,
        "交易日价差": long_price_diff,
        "最新K线价差": short_price_diff,
        "交易日振幅": today_amplitude,
        "第一位高值价": above1_price,
        "第二位高值价": above2_price,
        "第一位低值价": below1_price,
        "第二位低值价": below2_price,
        "中盘开盘数据统计": middle_session_from_open,
        "中盘中位数": median_price,
        "中盘中位数据统计": middle_session_from_median
    }


def rename_dict_keys(src_dict, mapping=None):
    if mapping is None:
        mapping = trans_map
    new_dict = {}
    for old_key, val in src_dict.items():
        new_dict[old_key] = val
        if old_key in mapping:
            eng_key = mapping[old_key]
            new_dict[eng_key] = val
    return new_dict


def get_market_ctx(ts_code=None):
    market_ctx = {}
    ui_read_code = None
    try:
        ths_tscode = shared_data.ths_common_control["期货代码"][0].window_text()
        ths_tscode = ths_tscode.strip().lower()
        if ths_tscode:
            ui_read_code = ths_tscode
    except Exception as e:
        print_context(f"UI读取【期货代码】控件失败：{str(e)}")

    if ui_read_code is not None:
        actual_code = ui_read_code
        print_context(f"正在获取期货品种[{actual_code}]的交易参考数据 - 品种交易来源：同花顺交易即时窗口")
    else:
        fallback_code = ts_code if ts_code is not None else shared_data.ts_code
        if fallback_code is None:
            raise RuntimeError("ts_code is None，无法解析交易品种")
        actual_code = fallback_code.strip().lower()
        print_context(
            f"UI读取无有效合约，正在获取期货品种[{actual_code}]的交易参考数据 - 品种交易来源：shared_data.ts_code")

    market_ctx["期货代码"] = actual_code
    if shared_data.history_data_analysis is None or actual_code not in shared_data.history_data_analysis:
        from data.data_from_sina import fetch_future_data
        history_data, _ = fetch_future_data(actual_code)
    else:
        history_data = shared_data.history_data_analysis
    market_ctx.update(history_data)
    market_ctx = rename_dict_keys(market_ctx, trans_map)

    db_data = get_db_data(ts_code=actual_code)
    if db_data is None:
        raise RuntimeError(f"获取数据库tick数据失败，actual_code={actual_code}，db_data为None（今日交易数据不足5条）")
    market_ctx.update(db_data)

    cur_time = datetime.now()
    market_ctx["小时"] = cur_time.hour
    market_ctx["分钟"] = cur_time.minute
    market_ctx["手数"] = shared_data.tscode_lots_dict.get(actual_code, 1)
    market_ctx["固止损500"] = 500
    market_ctx["固止损20"] = 20
    market_ctx["固止盈200"] = 200
    market_ctx["固止盈150"] = 150
    market_ctx["固止盈100"] = 100
    market_ctx["固止盈80"] = 80
    market_ctx["固止盈50"] = 50

    fut_info = get_future_info(symbol=str(actual_code), trade_price=db_data["最新价"])
    if shared_data.open_price is None or actual_code not in shared_data.open_price:
        open_info = get_open_price(actual_code)
    else:
        open_info = shared_data.open_price
    if fut_info is None:
        raise RuntimeError(f"获取合约 {actual_code} 的fut_info失败，返回None，无法继续交易")
    market_ctx.update(open_info[actual_code])

    market_ctx["交易状态"] = is_trade_status
    market_ctx["冷却期"] = is_cooling
    market_ctx["交易费"] = fut_info["fee"]
    market_ctx["盈亏系数"] = fut_info["coefficient"]
    market_ctx["夜市"] = fut_info["night_trading"]
    market_ctx["大盘走势"] = shared_data.get_direction().lower()
    market_ctx["K线时长"] = getattr(shared_data, "k_minutes", 1)
    market_ctx["获取价格频率"] = getattr(shared_data, "get_price_interval", 5)

    eval_ctx = BASE_EVAL_TPL.copy()
    eval_ctx.update(market_ctx)
    shared_data.market_ctx_dict.update(eval_ctx)
    eval_ctx = rename_dict_keys(eval_ctx, trans_map)
    return eval_ctx


def check_rule(rule_info: dict, merged_cond: list, market_ctx: dict, rule_name: str):
    """
    校验单条策略，已经传入【公共条件+策略自身条件合并后的条件对象列表】
    merged_cond 元素格式: {"expr":"xxx","enable":bool,"desc":"xxx"}
    返回：(ok:bool, fail_items:list, condition_detail:list)
    """
    condition_detail = []
    if not rule_info.get("enable", False):
        condition_detail.append({"expr": "", "result": False, "reason": "策略enable关闭", "actual": {}, "desc": ""})
        print_context(f"--------策略[{rule_name}]条件明细--------")
        status = "✅满足" if condition_detail[0]["result"] else "❌不满足"
        print_context(
            f"{status} | expr:{condition_detail[0]['expr']} | desc:{condition_detail[0]['desc']} | reason:{condition_detail[0]['reason']} | actual:{condition_detail[0]['actual']}")
        return False, [{"expr": "", "reason": "策略enable关闭", "actual": {}}], condition_detail

    cond_list = merged_cond
    fail_items = []

    for cond_item in cond_list:
        cond_enable = cond_item.get("enable", True)
        cond_expr = cond_item["expr"]
        cond_desc = cond_item.get("desc", "")

        if not cond_enable:
            condition_detail.append({
                "expr": cond_expr,
                "desc": cond_desc,
                "result": True,
                "reason": "条件enable关闭，跳过校验",
                "actual": {}
            })
            continue

        try:
            res = eval(cond_expr, market_ctx.copy())
            var_names = extract_expr_vars(cond_expr)
            actual_map = {}
            for vn in var_names:
                actual_map[vn] = market_ctx.get(vn, "<missing>")
            if res:
                condition_detail.append({
                    "expr": cond_expr,
                    "desc": cond_desc,
                    "result": True,
                    "reason": "条件满足",
                    "actual": actual_map
                })
            else:
                condition_detail.append({
                    "expr": cond_expr,
                    "desc": cond_desc,
                    "result": False,
                    "reason": "条件返回False",
                    "actual": actual_map
                })
                fail_items.append({
                    "expr": cond_expr,
                    "desc": cond_desc,
                    "reason": "条件返回False",
                    "actual": actual_map
                })
        except NameError as e:
            condition_detail.append({
                "expr": cond_expr,
                "desc": cond_desc,
                "result": False,
                "reason": f"变量缺失:{str(e)}",
                "actual": {}
            })
            fail_items.append({
                "expr": cond_expr,
                "desc": cond_desc,
                "reason": f"变量缺失:{str(e)}",
                "actual": {}
            })
        except Exception as e:
            condition_detail.append({
                "expr": cond_expr,
                "desc": cond_desc,
                "result": False,
                "reason": f"执行异常:{str(e)}",
                "actual": {}
            })
            fail_items.append({
                "expr": cond_expr,
                "desc": cond_desc,
                "reason": f"执行异常:{str(e)}",
                "actual": {}
            })

    print_context(f"--------策略[{rule_name}]条件明细-------- >>> [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
    for item in condition_detail:
        status = "✅满足" if item["result"] else "❌不满足"
        print_context(
            f"{status} | expr:{item['expr']} | desc:{item['desc']} | reason:{item['reason']} | actual:{item['actual']}")
    try:
        _pp = f"{shared_data.pre_profit:.2f}" if shared_data.pre_profit is not None else "None"
        _pl = f"{shared_data.pre_loss:.2f}" if shared_data.pre_loss is not None else "None"
    except Exception:
        _pp, _pl = str(shared_data.pre_profit), str(shared_data.pre_loss)
    print_context(f"\n固定止盈值：{_pp} 固定止损值： {_pl} - 请与公共模块变量和下单参数表单校对！\n")
    ok = len(fail_items) == 0
    return ok, fail_items, condition_detail


def scan_all_rules(pool: dict, market_ctx: dict):
    detail_map = {}
    hit_list = []
    default_priority = 0
    common_conditions = pool.get("common_conditions", [])
    print_context("=====公共条件校验=====")
    for cc in common_conditions:
        ce = cc.get("enable", True)
        if not ce:
            continue
        try:
            res = eval(cc["expr"], market_ctx.copy())
            print_context(f"公共条件 expr={cc['expr']} → 结果={res}")
        except Exception as e:
            print_context(f"公共条件 expr={cc['expr']} → 异常:{e}")

    for rule_name, rule_data in pool.items():
        if rule_name in ["common_conditions", "temp_params"]:
            continue
        try:
            raw_cond = rule_data.get("conditions", [])
            merged_cond = [*common_conditions, *raw_cond]
            ok, fails, condition_detail = check_rule(rule_data, merged_cond, market_ctx, rule_name)
        except Exception as e:
            sound_warning()
            print_context(f"{'-' * 30}策略[{rule_name}]条件明细{'-' * 30}")
            print_context(f"❌策略整体异常：{str(e)}")
            detail_map[rule_name] = (False, [{"expr": "", "reason": f"策略整体异常:{str(e)}", "actual": {}}], [])
            print("\n")
            continue

        detail_map[rule_name] = (ok, fails, condition_detail)
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


def calc_trade_pnl(trade_dir: str, cur_price: float, loss_price: float, profit_price: float, coefficient: float,
                   lot_size: int, total_fee: float):
    """计算止损、止盈对应的实际盈亏（已扣除双向手续费，纳入手数lot_size）
    total_fee：【1手双向手续费】，函数内部自动 × lot_size
    """
    pnl_loss = 0.0
    pnl_profit = 0.0
    total_fee_all = total_fee * lot_size
    if trade_dir == "rise":
        pnl_loss = (loss_price - cur_price) * coefficient * lot_size - total_fee_all
        pnl_profit = (profit_price - cur_price) * coefficient * lot_size - total_fee_all
    elif trade_dir == "fall":
        pnl_loss = (cur_price - loss_price) * coefficient * lot_size - total_fee_all
        pnl_profit = (cur_price - profit_price) * coefficient * lot_size - total_fee_all
    print_context(
        f"[盈亏测算] dir={trade_dir}, lot={lot_size}, 单双向手续费={total_fee},总手续费={total_fee_all},pnl_loss={pnl_loss},pnl_profit={pnl_profit}")
    return {
        "pnl_loss": round(pnl_loss, 2),
        "pnl_profit": round(pnl_profit, 2)
    }


def select_best_trade_rule(ts_code: str, ctx=None):
    """
    返回 (result_dict, detail_map)
    result_dict: {ts_code: {rule_id, priority, trade_params...}}，无命中返回 {}
    """
    if is_cooling() or not trade_flag() or is_trade_status():
        _r = []
        if not trade_flag():
            _r.append("非交易时段")
        if is_cooling():
            try:
                with shared_data.variables_rlock:
                    _vt = shared_data.valid_time
                _r.append(f"冷却期至{_vt.strftime('%H:%M:%S')}")
            except Exception:
                _r.append("冷却期")
        if is_trade_status():
            _r.append(f"当前有持仓[{shared_data.ts_code}]")
        print_context(f"⏸策略分析暂停 >>> {' | '.join(_r)}")
        shared_data.trade_menu_dict = {}
        return {}, {}
    if ctx is None:
        ctx = get_market_ctx(ts_code)

    hit_rules, detail_map = scan_all_rules(config_pool, ctx)

    hit_count = len(hit_rules)
    print_context(f"[{ts_code}] 正在从条件池进行策略评估，评估结果 >>> 命中策略数：{hit_count}")
    for hit_rule_id in hit_rules:
        r_data = config_pool.get(hit_rule_id, {})
        prio = r_data.get("priority", 0)
        print_context(f"  命中策略 -> rule_id:{hit_rule_id}, priority:{prio}")

    best_rule_name = get_highest_priority_rule(hit_rules)
    if best_rule_name is None:
        print_context(f"[{ts_code}] 无最高优先级策略被选中")
        return {}, detail_map

    rule_data = config_pool[best_rule_name]
    trade_params_raw = rule_data.get("trade_params", {})
    priority = rule_data.get("priority", 0)

    print_context(f"[{ts_code}] ✅已选最优策略:{best_rule_name}, priority:{priority}")

    out = {
        "rule_id": best_rule_name,
        "priority": priority,
    }
    for k, v in trade_params_raw.items():
        if k in _NO_EVAL:
            out[k] = v
        else:
            out[k] = eval_price_expression(v, ctx)

    trade_menu = {
        "ts_code": ts_code,
        "产品代码": ts_code,
        "rule_id": best_rule_name,
        "trade_direction": out.get("trade_direction"),
        "trade_time": datetime.now()
    }
    trade_menu.update(out)
    trade_menu["profit_price"] = out.get("profit_price")
    trade_menu["loss_price"] = out.get("loss_price")

    shared_data.trade_menu_dict = trade_menu
    print_context(f"✅[{datetime.now().strftime('%H:%M:%S')}]-命中策略,合约交易参数信息设置>>>\n{shared_data.trade_menu_dict}")
    return {ts_code: out}, detail_map


def order(ts_code=None):
    global stop_flag, config_pool, _last_cfg_mtime
    try:
        print_context("【ORDER】进入order函数")
        ts_code = ts_code if ts_code is not None else shared_data.ts_code
        no_print = False

        if config_pool is None:
            print_context("【ORDER】首次初始化加载cfg_pool.yaml")
            config_pool = load_config_pool(CFG_POOL_PATH)
            if os.path.exists(CFG_POOL_PATH):
                _last_cfg_mtime = os.stat(CFG_POOL_PATH).st_mtime
        no_print = False

        while not stop_flag:
            auto_reload_cfg_if_changed()

            current_user_type = getattr(shared_data, "user_type", 0)
            reach_max, curr_cnt, max_cnt = is_user_reach_max_limit(current_user_type)
            if reach_max:
                print_context(
                    f"🚫user_type={current_user_type}，今日平仓 {curr_cnt}/{max_cnt}，到达上限，禁止新开仓，持仓仍可执行自动平仓。")
                time.sleep(5)
                continue

            cond_time = trade_flag()
            cond_hold = is_trade_status()
            cooling = is_cooling()
            reasons = []
            if not cond_time:
                reasons.append(f"期货休市中‑[{datetime.now().strftime('%A')}]")
            if cond_hold:
                reasons.append(f"| 当前有持仓 - [{shared_data.ts_code}] |")
            if cooling:
                reasons.append(f"| 交易冷却期 |")
            try:
                if reasons:
                    if not no_print:
                        with shared_data.variables_rlock:
                            v_time = shared_data.valid_time
                        print_context(f"\n当前不满足交易条件，请等待...\n具体原因解析： {' '.join(reasons)}")
                        no_print = True
                    time.sleep(1)
                    continue
                no_print = False

                signal_res, detail_map = select_best_trade_rule(ts_code)
                if signal_res:
                    params = signal_res[ts_code]
                    shared_data.strategy_id = params["rule_id"]
                    rule_cfg = config_pool.get(params["rule_id"], {})
                    shared_data.trade_period = rule_cfg.get("trade_period", "")
                    trade_dir = params.get("trade_direction")
                    loss_price = params.get("loss_price")
                    profit_price = params.get("profit_price")
                    rule_id = params["rule_id"]

                    ok_flag, fail_list, _ = detail_map[rule_id]
                    rule_data = config_pool[rule_id]
                    rule_comment = rule_data.get("comment", "无策略描述")
                    if ok_flag:
                        print_context(
                            f"[{datetime.now().strftime('%H:%M:%S')}]✅命中策略:{rule_id}｜策略说明：{rule_comment}，全部条件校验通过")
                    else:
                        print_context(f"❌策略:{rule_id},存在不满足条件:{fail_list}")

                    if trade_dir and loss_price is not None and profit_price is not None:
                        strat_pre_profit = params.get("pre_profit")
                        strat_pre_loss = params.get("pre_loss")
                        lots = shared_data.tscode_lots_dict.get(ts_code, 1)
                        use_strat_pre_setting = False
                        final_cloud_profit = 0
                        final_cloud_loss = 0
                        final_cloud_break = 0

                        if strat_pre_profit is not None:
                            shared_data.pre_profit = float(strat_pre_profit) * lots
                            print_context(
                                f"📌策略[{rule_id}]已设置固定止盈值： pre_profit={shared_data.pre_profit:.2f} - [{datetime.now().strftime('%H:%M:%S')}]")
                            use_strat_pre_setting = True
                        if strat_pre_loss is not None:
                            shared_data.pre_loss = float(strat_pre_loss) * lots
                            print_context(
                                f"📌策略[{rule_id}]已设置固定止损值： pre_loss={shared_data.pre_loss:.2f} - [{datetime.now().strftime('%H:%M:%S')}]")
                            use_strat_pre_setting = True

                        with variables_rlock:
                            if shared_data.ui_busy:
                                print_context("⚠️ui正在处理委托，跳过本次开仓，防止重复下单")
                                continue
                            shared_data.ui_busy = True
                            shared_data.valid_time = datetime.now() + timedelta(
                                minutes=shared_data.valid_trade_interval)
                        try:
                            cur_price = auto_trade(trade_dir)
                            # 【新增】等待持仓成交落地，再挂云单
                            filled_ok = wait_position_filled(ts_code, max_wait_sec=60, poll_interval=1.0)
                            if not filled_ok:
                                print_context(f"❌[{ts_code}] 下单后等待成交超时，放弃设置云条件单")
                                continue

                            lot_size = shared_data.tscode_lots_dict.get(ts_code, 1)
                            fut_info = get_future_info(ts_code, cur_price)
                            per_lot_two_way_fee = fut_info.get('fee', 0) * 2
                            coefficient = fut_info.get('coefficient', 10)
                            price_valid = True

                            # 价格合法性校验，区分多空
                            if trade_dir == "rise":
                                # 多单：止损价 < 开仓价，止盈价 > 开仓价
                                if not (loss_price < cur_price and profit_price > cur_price):
                                    print(
                                        f"\r[{datetime.now().strftime('%H:%M:%S')}] - 设置云止损单错误：交易方向-买多({lot_size}手)，交易价-{cur_price}，止损价-{loss_price}，止盈价-{profit_price}")
                                    price_valid = False
                                    time.sleep(0.2)
                            elif trade_dir == "fall":
                                # 空单：止损价 > 开仓价，止盈价 < 开仓价
                                if not (loss_price > cur_price and profit_price < cur_price):
                                    print(
                                        f"\r[{datetime.now().strftime('%H:%M:%S')}] - 设置云止损单错误：交易方向-卖空({lot_size}手)，交易价‑{cur_price}，止损价‑{loss_price}，止盈价‑{profit_price}")
                                    price_valid = False
                                    time.sleep(0.2)

                            if not price_valid:
                                print_context(f"⚠️{ts_code} {trade_dir} 止盈止损价格方向非法，跳过云单设置")
                                continue

                            pnl_result = calc_trade_pnl(
                                trade_dir=trade_dir,
                                cur_price=cur_price,
                                loss_price=loss_price,
                                profit_price=profit_price,
                                coefficient=coefficient,
                                lot_size=lot_size,
                                total_fee=per_lot_two_way_fee
                            )
                            calc_profit_val = pnl_result["pnl_profit"]

                            # ========== 【核心改动：保本价差公式】 ==========
                            cloud_break_raw = abs(profit_price - cur_price) * 0.8
                            final_cloud_break = int(cloud_break_raw)
                            # =============================================

                            if not use_strat_pre_setting:
                                if calc_profit_val < 50:
                                    shared_data.pre_profit = 50
                                    shared_data.pre_loss = 0.0
                                    final_cloud_profit = 0
                                    final_cloud_loss = 0
                                    print_context(
                                        f"【更新预设置盈亏】pre_profit={shared_data.pre_profit:.2f}, pre_loss={shared_data.pre_loss:.2f}")
                                elif calc_profit_val > 200:
                                    shared_data.pre_profit = 200
                                    shared_data.pre_loss = 0.0
                                    final_cloud_profit = profit_price
                                    final_cloud_loss = 0
                                    print_context(
                                        f"【更新预设置盈亏】pre_profit={shared_data.pre_profit:.2f}, pre_loss={shared_data.pre_loss:.2f}")
                                else:
                                    shared_data.pre_profit = calc_profit_val
                                    shared_data.pre_loss = 0.0
                                    final_cloud_profit = profit_price
                                    final_cloud_loss = 0
                                    print_context(
                                        f"【更新预设置盈亏】pre_profit={shared_data.pre_profit:.2f}, pre_loss={shared_data.pre_loss:.2f}")
                            else:
                                final_cloud_profit = profit_price
                                final_cloud_loss = loss_price
                                print_context(f"📌策略已配置pre_profit/pre_loss，使用策略原始云参数，保本值由价格差计算")

                            shared_data.hold_value = final_cloud_break
                            shared_data.loss_profit_param["云止损单"] = final_cloud_loss
                            shared_data.loss_profit_param["云止盈单"] = final_cloud_profit
                            shared_data.loss_profit_param["云保本单"] = final_cloud_break
                            shared_data.loss_profit_param["方向"] = trade_dir

                            set_msg = (
                                f"【下单设置详情 - {'模拟用户' if shared_data.user_type == 0 else '君安用户'}】 | 交易持仓时间： {datetime.now().strftime('%H:%M:%S')}\n品种:{ts_code},方向:{trade_dir},手数lot_size={lot_size}\n"
                                f"成交参考价cur_price={cur_price:.2f} 固定止盈值：{shared_data.pre_profit:.2f} 固定止损值：{shared_data.pre_loss:.2f}\n"
                                f"计算止盈盈亏calc_profit_val={calc_profit_val:.2f}元\n"
                                f"shared_data.pre_profit={shared_data.pre_profit:.2f}, shared_data.pre_loss={shared_data.pre_loss:.2f}\n"
                                f"云止盈价={final_cloud_profit},云止损价={final_cloud_loss},云保本差价={final_cloud_break},止盈开仓价差(原始)={abs(profit_price-cur_price):.2f}"
                            )
                            print_context(f"{set_msg}")
                            try:
                                set_loss_profit()
                            except Exception as e:
                                print_context(f"⚠️调用set_loss_profit设置云条件单异常：{str(e)}")
                        except Exception as e:
                            err_txt = f"order内下单业务异常：{str(e)}\n{traceback.format_exc()}"
                            print(err_txt, flush=True)
                            time.sleep(1)
                        finally:
                            with variables_rlock:
                                shared_data.ui_busy = False
                    else:
                        print_context("参数不全，跳过本次下单")
                time.sleep(5)
            except Exception as e:
                err_txt = f"order线程顶层异常：{str(e)}\n{traceback.format_exc()}"
                print(err_txt, flush=True)
                time.sleep(1)
    except Exception as e:
        err_txt = f"order线程顶层异常：{str(e)}\n{traceback.format_exc()}"
        print(err_txt, flush=True)



if __name__ == "__main__":
    print(get_market_ctx(ts_code="m2701"))
