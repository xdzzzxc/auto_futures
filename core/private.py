# core/private.py
"""
core包私有模块：存放平仓记录、交易计数相关函数，解决trade/monitor循环导入
"""
import os
from datetime import datetime
from public.shared_data import get_data_cache_dir
from public import shared_data
from public.print_context import print_context
import threading
import json

_counter_lock = threading.Lock()
# 保留30天平仓记录
KEEP_DAYS = 30


def get_trade_counter_filepath() -> str:
    cache_dir = get_data_cache_dir()
    log_dir = os.path.join(cache_dir, "trade_log")
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, "trade_log.json")


def get_today_date_short() -> str:
    """获取今日8位日期字符串 YYYYMMDD"""
    return datetime.now().strftime("%Y%m%d")


def get_now_time_full() -> str:
    """获取精确到秒时间key YYYYMMDDHHMMSS，用于单条平仓记录key"""
    return datetime.now().strftime("%Y%m%d%H%M%S")


def load_trade_counter() -> dict:
    """加载计数文件，文件缺失/损坏返回默认配置"""
    fp = get_trade_counter_filepath()
    default_cfg = {
        "config": {
            "max_counts_0": 5,
            "max_counts_1": 5
        },
        "records": {}
    }
    with _counter_lock:
        if not os.path.exists(fp):
            return default_cfg
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, Exception):
            print_context("⚠️trade_log.json损坏，使用默认计数配置")
            return default_cfg
    # 兜底补齐字段
    if "config" not in data:
        data["config"] = {"max_counts_0": 5, "max_counts_1": 5}
    if "records" not in data:
        data["records"] = {}
    if "max_counts_0" not in data["config"]:
        data["config"]["max_counts_0"] = 5
    if "max_counts_1" not in data["config"]:
        data["config"]["max_counts_1"] = 5
    return data


def save_trade_counter(cfg: dict):
    fp = get_trade_counter_filepath()
    tmp_fp = fp + ".tmp"
    with _counter_lock:
        try:
            with open(tmp_fp, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=4)
            os.replace(tmp_fp, fp)
        except Exception as e:
            print_context(f"❌保存trade_log.json失败:{e}")
            if os.path.exists(tmp_fp):
                os.remove(tmp_fp)


def prune_old_records(cfg: dict):
    """清理超过KEEP_DAYS天的历史记录"""
    from datetime import timedelta
    now = datetime.now()
    keep_cutoff = now - timedelta(days=KEEP_DAYS)
    cutoff_str = keep_cutoff.strftime("%Y%m%d")
    new_records = {}
    for rec_key, rec_val in cfg["records"].items():
        if len(rec_key) >= 8:
            rec_date = rec_key[:8]
            if rec_date >= cutoff_str:
                new_records[rec_key] = rec_val
    cfg["records"] = new_records


def get_user_today_trade_stat(user_type: int):
    """
    根据user_type获取今日统计
    :param user_type: 0模拟 1实盘
    :return (today_cnt:int, max_cnt:int)
    """
    cfg = load_trade_counter()
    today_ymd = get_today_date_short()
    max_cnt = cfg["config"].get(f"max_counts_{user_type}", 5)
    today_cnt = 0
    # 只遍历records
    for rec_key, rec_val in cfg["records"].items():
        if len(rec_key) >= 8 and rec_key[:8] == today_ymd:
            if rec_val.get("user_type") == user_type:
                today_cnt += 1
    return today_cnt, max_cnt


def append_close_record(user_type: int, pnl: float, ts_code: str):
    """
    新增一条平仓记录；monitor自动平仓成功调用
    :param user_type: 0模拟 1实盘
    :param pnl: 本次平仓盈亏数值
    :param ts_code: 期货品种代码
    """
    ts_code = (ts_code if ts_code is not None else shared_data.ts_code).lower()
    cfg = load_trade_counter()
    rec_key = get_now_time_full()
    # 写入结构化记录，方便后续扩展
    cfg["records"][rec_key] = {
        "user_type": user_type,
        "pnl": pnl,
        "ts_code": ts_code
    }
    # 清理过期记录
    prune_old_records(cfg)
    save_trade_counter(cfg)
    today_cnt, max_cnt = get_user_today_trade_stat(user_type)
    print_context(f"📌平仓明细 | 时间:{rec_key} | user_type={user_type} | 品种:{ts_code} | 实际盈亏:{pnl:.2f} | "
                  f"今日已平仓 {today_cnt}/{max_cnt}")


if __name__ == '__main__':
    print(get_trade_counter_filepath())
