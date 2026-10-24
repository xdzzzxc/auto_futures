import ast
from typing import Tuple, Set, List
from ruamel.yaml import YAML
from pathlib import Path
from public.shared_data import get_data_cache_dir
from pathlib import Path


# ====================== 1. 白名单：从你这份cfg_pool.yaml提取全部标识符 ======================
# 【行情上下文变量 ctx】
CTX_VARS = {
    "ts_code", "ths_tscode",
    "market_trend", "latest_k_trend", "day_trend",
    "hour", "minute", "night_trading",
    "today_open", "pre_settle_hist", "pre_close",
    "last_price", "today_high", "today_low",
    "history_min_high_open", "history_avg_high_open", "history_max_high_open",
    "history_min_low_open", "history_avg_low_open", "history_max_low_open",
    "history_support", "history_resistance",
    "coefficient", "trade_fee",
    "above1_price", "above2_price", "below1_price", "below2_price",
}

# 【自定义函数，注入SAFE_GLOBALS】
CUSTOM_FUNCS = {
    "is_trade_status", "is_cooling",
}

# 【基础内置函数/常量，注入SAFE_GLOBALS】
SAFE_FUNC_NAMES = {
    "max", "min", "abs", "round", "pow", "sum", "len",
    "int", "float", "bool",
    "True", "False", "None",
    "any", "map",  # 你的common_conditions用到了 any(map(...))
}

# 合并总白名单
ALLOWED_NAMES = CTX_VARS | CUSTOM_FUNCS | SAFE_FUNC_NAMES


# ====================== 2. AST 标识符收集器 ======================
class NameCollector(ast.NodeVisitor):
    def __init__(self):
        self.names: Set[str] = set()

    def visit_Name(self, node: ast.Name):
        self.names.add(node.id)
        self.generic_visit(node)


def check_one_expression(expr: str) -> Tuple[bool, str, Set[str]]:
    """
    单条表达式校验：语法 + 标识符白名单
    返回 (ok:bool, msg:str, found_names:Set)
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        return False, f"语法错误: {e.msg} (offset {e.offset})", set()
    except Exception as e:
        return False, f"AST解析异常: {str(e)}", set()

    collector = NameCollector()
    collector.visit(tree)
    unknown = collector.names - ALLOWED_NAMES
    if unknown:
        return False, f"非法标识符: {sorted(unknown)}", collector.names
    return True, "OK", collector.names


# ====================== 3. yaml加载（ruamel.yaml 保留行号） ======================
yaml = YAML()
yaml.preserve_quotes = True


def check_cfg_pool_yaml(filepath: str | Path) -> List[dict]:
    """
    扫描整个cfg_pool.yaml
    返回错误列表：[ {"line":行号, "strategy":策略名, "key":字段名, "expr":表达式, "msg":错误信息} ]
    """
    fp = Path(filepath)
    data = yaml.load(fp)
    errors: List[dict] = []

    # 先扫 common_conditions
    common_conds = data.get("common_conditions", [])
    for idx, cond in enumerate(common_conds):
        if not isinstance(cond, dict):
            continue
        expr = cond.get("expr")
        if expr is None:
            continue
        # 获取节点行号
        lc = cond.lc
        line_no = lc.line if lc else -1
        ok, msg, _ = check_one_expression(expr)
        if not ok:
            errors.append({
                "line": line_no,
                "strategy": "common_conditions",
                "key": f"[{idx}] expr",
                "expr": expr,
                "msg": msg
            })

    # 扫描所有 strategy_xxx
    for strat_name, strat_cfg in data.items():
        if not strat_name.startswith("strategy_"):
            continue
        if not isinstance(strat_cfg, dict):
            continue

        # 扫描 strategy.conditions
        conds = strat_cfg.get("conditions", [])
        for idx, cond in enumerate(conds):
            if not isinstance(cond, dict):
                continue
            expr = cond.get("expr")
            if expr is None:
                continue
            lc = cond.lc
            line_no = lc.line if lc else -1
            ok, msg, _ = check_one_expression(expr)
            if not ok:
                errors.append({
                    "line": line_no,
                    "strategy": strat_name,
                    "key": f"conditions[{idx}] expr",
                    "expr": expr,
                    "msg": msg
                })

        # 扫描 strategy.trade_params
        trade_params = strat_cfg.get("trade_params", {})
        for param_key, expr in trade_params.items():
            if expr is None:
                continue
            lc = trade_params.lc.data[param_key]
            line_no = lc.line if lc else -1
            ok, msg, _ = check_one_expression(expr)
            if not ok:
                errors.append({
                    "line": line_no,
                    "strategy": strat_name,
                    "key": f"trade_params.{param_key}",
                    "expr": expr,
                    "msg": msg
                })
    return errors


def print_check_result(errors: List[dict]):
    """格式化打印结果"""
    if not errors:
        print("✅ 全部表达式校验通过，无语法/非法标识符错误！")
        return
    print(f"❌ 一共发现 {len(errors)} 处表达式错误：\n")
    for err in errors:
        print(f"【行号 {err['line']}】 策略：{err['strategy']}，字段：{err['key']}")
        print(f"表达式：{err['expr']}")
        print(f"错误：{err['msg']}")
        print("-" * 80)


if __name__ == "__main__":
    print(Path(get_data_cache_dir()).parent.parent / "core")
    err_list = check_cfg_pool_yaml("cfg_pool.yaml")
    print_check_result(err_list)
