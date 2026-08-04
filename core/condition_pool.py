from market_ctx import get_market_ctx

config_pool = {
    "trade_001": {
        "enabled": True,
        "conditions": [
            "direction == 'rise'",
            "open > pre_settle",
            "gap_percent > 0.02"
        ],
        "priority": 10,
        "trade_params": {
            "trade_direction": "fall",
            "trade_price": "open + 20",
            "profit_price": "resistance - 10",
            "loss_price": "support + 5"
        }
    },
    "trade_002": {
        "enabled": True,
        "conditions": [
            "direction == 'sideways'",
            "open < pre_settle",
            "gap_percent < 0.02"
        ],
        "priority": 5,
        "trade_params": {
            "trade_direction": "rise",
            "trade_price": "open + 10",
            "profit_price": "resistance",
            "loss_price": "support"
        }
    }
}


def check_rule(rule_info: dict, market_ctx: dict) -> tuple[bool, list[str]]:
    if not rule_info.get("enabled", False):
        return False, ["策略enabled关闭"]

    cond_list = rule_info.get("conditions", [])
    fail_conds = []

    for expr in cond_list:
        try:
            env_globals = {
                "__builtins__": {
                    "abs": abs,
                    "min": min,
                    "max": max
                }
            }
            env_globals.update(market_ctx)
            result = eval(expr, env_globals, {})
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


_PRICE_EVAL_WHITELIST = {"trade_price", "profit_price", "loss_price"}


def _eval_price_expr(expr, market_ctx: dict):
    if expr is None:
        return None
    if isinstance(expr, (int, float)):
        return expr

    env_globals = {
        "__builtins__": {
            "abs": abs,
            "min": min,
            "max": max
        }
    }
    env_globals.update(market_ctx)
    try:
        val = eval(expr, env_globals, {})
        return val
    except Exception:
        return None


def select_best_trade_rule(ts_code: str) -> dict:
    """
    返回 {ts_code: {全部trade_params字段，价格自动计算，其他字段原样保留}}
    无命中返回 {}
    """
    ctx = get_market_ctx(ts_code)
    hit_list, _ = scan_all_rules(config_pool, ctx)
    best_rule_name = get_highest_priority_rule(hit_list)

    if best_rule_name is None:
        return {}

    raw_params = config_pool[best_rule_name]["trade_params"]
    out_params = {}
    for k, v in raw_params.items():
        if k in _PRICE_EVAL_WHITELIST:
            out_params[k] = _eval_price_expr(v, ctx)
        else:
            out_params[k] = v

    return {ts_code: out_params}


if __name__ == '__main__':
    target_ts = "m2609"
    result = select_best_trade_rule(target_ts)
    print("输出下单参数：", result)