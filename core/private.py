# core/private.py
"""
core包私有模块：存放平仓记录、交易计数相关函数，解决trade/monitor循环导入
本次修复：
1. record内部增加 close_time 字段，trade_log.json和trade_records.json记录实体完全一致
2. trade_log.json records的key直接使用record["close_time"]
3. 保证两个文件的record字典字段完全相同：close_time,user_type,pnl,trade_dir,ts_code,strategy_id,trade_period
4. prune_old_records：仅保留当日记录；config配置节点永久保留
5. 修复：不再出现两个文件record字段不一致问题
6. 保留DEBUG打印用于排查strategy_id传参
"""
import os
from datetime import datetime
from public.shared_data import get_data_cache_dir
from public import shared_data
from public.print_context import print_context
import threading
import json

_counter_lock = threading.Lock()


def get_trade_counter_filepath() -> str:
    cache_dir = get_data_cache_dir()
    log_dir = os.path.join(cache_dir, "trade_log")
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, "trade_log.json")


def get_trade_records_filepath() -> str:
    """获取追加记录文件 trade_records.json 路径"""
    cache_dir = get_data_cache_dir()
    log_dir = os.path.join(cache_dir, "trade_log")
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, "trade_records.json")


def get_today_date_short() -> str:
    """获取今日8位日期字符串 YYYYMMDD"""
    return datetime.now().strftime("%Y%m%d")


def get_now_time_full() -> str:
    """获取精确到毫秒时间字符串 YYYYMMDDHHMMSSfff，用作close_time"""
    return datetime.now().strftime("%Y%m%d%H%M%S%f")[:17]


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


def append_trade_record_file(record: dict):
    """追加一条完整平仓记录到 trade_records.json，顶层为数组，只追加不清理（全量历史）"""
    fp = get_trade_records_filepath()
    with _counter_lock:
        if not os.path.exists(fp):
            arr = []
        else:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    arr = json.load(f)
                if not isinstance(arr, list):
                    arr = []
            except (json.JSONDecodeError, Exception):
                arr = []
        arr.append(record)
        tmp_fp = fp + ".tmp"
        try:
            with open(tmp_fp, "w", encoding="utf-8") as f:
                json.dump(arr, f, ensure_ascii=False, indent=4)
            os.replace(tmp_fp, fp)
            print_context(f"✅追加记录成功到 trade_records.json")
        except Exception as e:
            print_context(f"❌写入trade_records.json失败: {e}")
            if os.path.exists(tmp_fp):
                os.remove(tmp_fp)


def prune_old_records(cfg: dict):
    """
    清理trade_log.json records中非今日记录；config节点完全不动。
    使用record内部close_time判断日期，不再依靠外部key。
    """
    today_ymd = get_today_date_short()
    new_records = {}
    for rec_key, rec_val in cfg["records"].items():
        close_time = rec_val.get("close_time", "")
        if len(close_time) >= 8:
            rec_date = close_time[:8]
            if rec_date == today_ymd:
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
    # 遍历records，读取record内部close_time判断日期
    for rec_key, rec_val in cfg["records"].items():
        close_time = rec_val.get("close_time", "")
        if len(close_time) >= 8 and close_time[:8] == today_ymd:
            if rec_val.get("user_type") == user_type:
                today_cnt += 1
    return today_cnt, max_cnt


def append_close_record(user_type: int,
                        pnl: float,
                        ts_code: str,
                        strategy_id: str = "",
                        trade_period: str = ""):
    """
    新增一条平仓记录；monitor自动平仓成功调用
    组装唯一record字典，record内部自带close_time。
    同一份record写入trade_log.json和trade_records.json，两个文件记录实体完全一致。
    :param user_type: 0模拟 1实盘
    :param pnl: 本次平仓盈亏数值
    :param ts_code: 期货品种代码
    :param strategy_id: 策略编号
    :param trade_period: 策略配置的 trade_period
    """
    print_context(f"DEBUG append_close_record: strategy_id=[{strategy_id}]")
    # ts_code兜底防止None.lower()报错
    ts_code = ts_code or shared_data.ts_code or ""
    ts_code = ts_code.lower()
    trade_dir = shared_data.trade_menu_dict["trade_direction"]
    close_time = get_now_time_full()

    # ==========核心：自包含完整record，两个文件共用这个对象==========
    record = {
        "close_time": close_time,
        "user_type": user_type,
        "pnl": pnl,
        "trade_dir": trade_dir,
        "ts_code": ts_code,
        "strategy_id": strategy_id,
        "trade_period": trade_period,
    }

    cfg = load_trade_counter()
    # trade_log.json 的key就是close_time，value就是完整record
    cfg["records"][close_time] = record

    # 清理非今日旧记录
    prune_old_records(cfg)
    save_trade_counter(cfg)

    # 写入全量历史文件，record完全一样
    append_trade_record_file(record)
