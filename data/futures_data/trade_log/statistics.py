# statistics.py
import json
import os
from typing import Optional, Dict, Tuple, List
from collections import defaultdict
from datetime import datetime


def statistics_trade_recorders(
    ts_code: Optional[str] = None,
    count_date: Optional[str] = None,
    user_type: Optional[int] = None  # 新增入参：None=全部账户，0虚拟，1实盘
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """
    统计 trade_records.json 平仓交易记录
    :param ts_code: 品种代码，None=全部品种；指定如 "c2611" 只统计该品种
    :param count_date: 统计时间范围，None=本月；
        "2026" → 2026全年；"202609" → 2026年09月
    :param user_type: 账户类型 None=全部；0虚拟盘，1实盘
    :return: tuple(总表, 品种策略明细报表, 策略汇总报表)
        总表：按【ts_code + 时间维度 + user_type】聚合：ts_code,时间维度,账户类型,总盈亏,fall盈亏,rise盈亏
        品种策略明细报表：按【ts_code + 时间维度 + strategy_id + user_type】聚合：ts_code,时间维度,账户类型,strategy_id,交易次数,总盈亏,盈利次数,盈利胜率(%),亏损次数,亏损率(%)
        策略汇总报表：按【strategy_id + 时间维度 + user_type】聚合：strategy_id,时间维度,账户类型,交易次数,总盈亏,盈利次数,盈利胜率(%),亏损次数,亏损率(%)
    """
    # 文件路径，statistics.py 和 trade_records.json 在同一目录
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_records.json")
    # ========= 调试打印 =========
    print(f"【DEBUG】json完整路径：{json_path}")
    print(f"【DEBUG】文件存在？{os.path.exists(json_path)}")
    # ============================

    # 加载json
    if not os.path.exists(json_path):
        return [], [], []
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            records = json.load(f)
    except (json.JSONDecodeError, Exception) as e:
        print(f"【DEBUG】读取JSON异常：{e}")
        return [], [], []
    if not isinstance(records, list):
        records = []
    print(f"【DEBUG】原始记录条数：{len(records)}")

    now = datetime.now()

    # 解析count_date，构造过滤条件
    def get_time_filter(close_time_str: str) -> bool:
        if count_date is None:
            # 默认：本月，格式 close_time: YYYYMMDDHHMMSS
            if len(close_time_str) < 6:
                return False
            rec_year = int(close_time_str[:4])
            rec_month = int(close_time_str[4:6])
            return rec_year == now.year and rec_month == now.month
        elif len(count_date) == 4:
            # 4位：年度统计 例 "2026"
            if len(close_time_str) < 4:
                return False
            return close_time_str[:4] == count_date
        elif len(count_date) == 6:
            # 6位：年月统计 例 "202609"
            if len(close_time_str) < 6:
                return False
            return close_time_str[:6] == count_date
        else:
            return False

    # 筛选记录
    filtered = []
    for r in records:
        close_time = r.get("close_time", "")
        rec_ts = r.get("ts_code", "")
        # 新增：读取记录内user_type，缺失默认0虚拟盘
        rec_user_type = r.get("user_type", 0)

        if not get_time_filter(close_time):
            continue
        if ts_code is not None and rec_ts.lower() != ts_code.lower():
            continue
        # 新增账户过滤：入参user_type不为None时只匹配对应账户
        if user_type is not None and rec_user_type != user_type:
            continue

        filtered.append(r)
    print(f"【DEBUG】过滤后符合条件记录条数：{len(filtered)}")

    # ===== 聚合容器 =====
    # 总表聚合 key=(ts_code, time_label, user_type)
    total_agg = defaultdict(lambda: {
        "total_pnl": 0.0,
        "fall_pnl": 0.0,
        "rise_pnl": 0.0
    })
    # 品种策略明细报表 key=(ts_code, time_label, strategy_id, user_type)
    detail_agg = defaultdict(lambda: {
        "count": 0,
        "total_pnl": 0.0,
        "win_count": 0,
        "loss_count": 0
    })
    # 策略汇总聚合 key=(strategy_id, time_label, user_type)
    strategy_agg = defaultdict(lambda: {
        "count": 0,
        "total_pnl": 0.0,
        "win_count": 0,
        "loss_count": 0
    })

    for rec in filtered:
        close_time = rec.get("close_time", "")
        rec_ts = rec.get("ts_code", "").lower()
        pnl = float(rec.get("pnl", 0.0))
        strategy_id = rec.get("strategy_id", "")
        trade_dir = rec.get("trade_dir", "")
        # 读取当前记录账户类型
        rec_user_type = rec.get("user_type", 0)

        # 时间标签
        if count_date is None:
            time_label = f"{now.year}-{now.month:02d}"
        elif len(count_date) == 4:
            time_label = count_date
        elif len(count_date) == 6:
            time_label = f"{count_date[:4]}-{count_date[4:]}"
        else:
            time_label = "unknown"

        # 聚合key全部追加 rec_user_type
        agg_key = (rec_ts, time_label, rec_user_type)
        strat_key = (rec_ts, time_label, strategy_id, rec_user_type)
        strat_only_key = (strategy_id, time_label, rec_user_type)

        # 总表统计
        total_agg[agg_key]["total_pnl"] += pnl
        if trade_dir == "fall":
            total_agg[agg_key]["fall_pnl"] += pnl
        elif trade_dir == "rise":
            total_agg[agg_key]["rise_pnl"] += pnl

        # 品种策略明细报表统计
        detail_agg[strat_key]["count"] += 1
        detail_agg[strat_key]["total_pnl"] += pnl
        if pnl > 0:
            detail_agg[strat_key]["win_count"] += 1
        elif pnl < 0:
            detail_agg[strat_key]["loss_count"] += 1

        # 策略汇总统计
        strategy_agg[strat_only_key]["count"] += 1
        strategy_agg[strat_only_key]["total_pnl"] += pnl
        if pnl > 0:
            strategy_agg[strat_only_key]["win_count"] += 1
        elif pnl < 0:
            strategy_agg[strat_only_key]["loss_count"] += 1

    # ========= 组装总表结果 =========
    summary_table = []
    for (ts, t_label, ut), val in total_agg.items():
        account_name = "虚拟盘" if ut == 0 else "实盘"
        summary_table.append({
            "ts_code": ts,
            "时间": t_label,
            "账户类型": account_name,
            "user_type": ut,
            "总盈亏": round(val["total_pnl"], 2),
            "fall盈亏": round(val["fall_pnl"], 2),
            "rise盈亏": round(val["rise_pnl"], 2),
        })

    # ========= 组装品种策略明细报表 =========
    detail_table = []
    for (ts, t_label, sid, ut), val in detail_agg.items():
        total_cnt = val["count"]
        win_rate = round(val["win_count"] / total_cnt * 100, 2) if total_cnt > 0 else 0.0
        loss_rate = round(val["loss_count"] / total_cnt * 100, 2) if total_cnt > 0 else 0.0
        account_name = "虚拟盘" if ut == 0 else "实盘"
        detail_table.append({
            "ts_code": ts,
            "时间": t_label,
            "账户类型": account_name,
            "user_type": ut,
            "策略": sid,
            "次数": total_cnt,
            "总盈亏": round(val["total_pnl"], 2),
            "盈利次数": val["win_count"],
            "盈利胜率(%)": win_rate,
            "亏损次数": val["loss_count"],
            "亏损率(%)": loss_rate,
        })

    # ========== 组装策略汇总报表 ==========
    strategy_report = []
    for (sid, t_label, ut), val in strategy_agg.items():
        total_cnt = val["count"]
        win_rate = round(val["win_count"] / total_cnt * 100, 2) if total_cnt > 0 else 0.0
        loss_rate = round(val["loss_count"] / total_cnt * 100, 2) if total_cnt > 0 else 0.0
        account_name = "虚拟盘" if ut == 0 else "实盘"
        strategy_report.append({
            "策略": sid,
            "时间": t_label,
            "账户类型": account_name,
            "user_type": ut,
            "次数": total_cnt,
            "总盈亏": round(val["total_pnl"], 2),
            "盈利次数": val["win_count"],
            "盈利胜率(%)": win_rate,
            "亏损次数": val["loss_count"],
            "亏损率(%)": loss_rate,
        })

    return summary_table, detail_table, strategy_report


def print_stat_result(ts_code=None, count_date=None, user_type=None):
    """
    调用统计函数并格式化打印三张报表
    :param ts_code: 品种代码
    :param count_date: 时间维度 None本月 / "2026"全年 / "202609"年月
    :param user_type: None全部账户，0虚拟盘，1实盘
    """
    summary_table, detail_table, strategy_report = statistics_trade_recorders(
        ts_code=ts_code,
        count_date=count_date,
        user_type=user_type
    )
    # 账户名称显示
    user_type_map = {None: "全部账户", 0: "虚拟盘", 1: "实盘"}
    account_name = user_type_map.get(user_type, str(user_type))

    print("=" * 100)
    print(f"【交易统计报表】品种:{ts_code if ts_code else '全部品种'} | 时间:{count_date if count_date else '本月'} | 账户:{account_name}")
    print("=" * 100)

    # ========== 1.总表 ==========
    print("\n===== 总表（品种+时间+账户） =====")
    if not summary_table:
        print("无记录")
    else:
        # 表头
        print(f"{'ts_code':<8}{'时间':<10}{'账户类型':<8}{'总盈亏':<10}{'fall盈亏':<10}{'rise盈亏':<10}")
        print("-" * 70)
        for row in summary_table:
            print(
                f"{row['ts_code']:<8}"
                f"{row['时间']:<8}"
                f"{row['账户类型']:<8}"
                f"{row['总盈亏']:<12.2f}"
                f"{row['fall盈亏']:<12.2f}"
                f"{row['rise盈亏']:<12.2f}"
            )

    # ========== 2.品种策略明细 ==========
    print("\n===== 品种策略明细报表（品种+时间+策略+账户） =====")
    if not detail_table:
        print("无记录")
    else:
        print(
            f"{'ts_code':<8}{'时间':<10}{'账户类型':<8}{'策略':<12}{'次数':<6}"
            f"{'总盈亏':<12}{'盈利次数':<8}{'胜率(%)':<10}{'亏损次数':<8}{'亏损率(%)':<10}"
        )
        print("-" * 105)
        for row in detail_table:
            print(
                f"{row['ts_code']:<8}"
                f"{row['时间']:<10}"
                f"{row['账户类型']:<8}"
                f"{row['策略']:<12}"
                f"{row['次数']:<6d}"
                f"{row['总盈亏']:<12.2f}"
                f"{row['盈利次数']:<8d}"
                f"{row['盈利胜率(%)']:<10.2f}"
                f"{row['亏损次数']:<8d}"
                f"{row['亏损率(%)']:<10.2f}"
            )

    # ==========3.策略汇总 ==========
    print("\n===== 策略汇总报表（策略+时间+账户） =====")
    if not strategy_report:
        print("无记录")
    else:
        print(
            f"{'策略':<12}{'时间':<10}{'账户类型':<8}{'次数':<6}"
            f"{'总盈亏':<12}{'盈利次数':<8}{'胜率(%)':<10}{'亏损次数':<8}{'亏损率(%)':<10}"
        )
        print("-" * 90)
        for row in strategy_report:
            print(
                f"{row['策略']:<12}"
                f"{row['时间']:<8}"
                f"{row['账户类型']:<8}"
                f"{row['次数']:<6d}"
                f"{row['总盈亏']:<12.2f}"
                f"{row['盈利次数']:<8d}"
                f"{row['盈利胜率(%)']:<10.2f}"
                f"{row['亏损次数']:<8d}"
                f"{row['亏损率(%)']:<10.2f}"
            )
    print("\n" + "=" * 100 + "\n")


# ====================== 新增：trade_log.json 今日统计函数 ======================
def statistics_today_trade_log(user_type: Optional[int] = None):
    """
    读取同级目录 trade_log.json，统计【今日】平仓记录，按user_type区分
    :param user_type: None全部账户，0虚拟盘，1实盘
    :return: Tuple[List[Dict], List[Dict], List[Dict]] 总表、品种策略明细、策略汇总
    """
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_log.json")
    print(f"【DEBUG】trade_log.json路径：{json_path}")
    print(f"【DEBUG】文件存在？{os.path.exists(json_path)}")

    if not os.path.exists(json_path):
        return [], [], []
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except (json.JSONDecodeError, Exception) as e:
        print(f"【DEBUG】读取trade_log异常：{e}")
        return [], [], []

    # 解析 {config, records:{close_time:record}} 结构
    records = []
    if isinstance(raw_data, dict) and "records" in raw_data:
        record_dict = raw_data["records"]
        for close_time_str, item in record_dict.items():
            row = item.copy()
            row["close_time"] = close_time_str
            records.append(row)
    print(f"【DEBUG】trade_log原始记录条数：{len(records)}")

    now = datetime.now()
    today_str = now.strftime("%Y%m%d")  # 当日日期 YYYYMMDD

    # 筛选今日记录
    filtered = []
    for r in records:
        close_time = r.get("close_time", "")
        # 取close_time前8位为日期 YYYYMMDD
        if len(close_time) < 8 or close_time[:8] != today_str:
            continue
        rec_user_type = r.get("user_type", 0)
        if user_type is not None and rec_user_type != user_type:
            continue
        filtered.append(r)
    print(f"【DEBUG】trade_log今日过滤后记录条数：{len(filtered)}")

    # 聚合容器，结构和上面保持一致
    total_agg = defaultdict(lambda: {"total_pnl": 0.0, "fall_pnl": 0.0, "rise_pnl": 0.0})
    detail_agg = defaultdict(lambda: {"count": 0, "total_pnl": 0.0, "win_count": 0, "loss_count": 0})
    strategy_agg = defaultdict(lambda: {"count": 0, "total_pnl": 0.0, "win_count": 0, "loss_count": 0})

    for rec in filtered:
        rec_ts = rec.get("ts_code", "").lower()
        pnl = float(rec.get("pnl", 0.0))
        strategy_id = rec.get("strategy_id", "")
        trade_dir = rec.get("trade_dir", "")
        rec_user_type = rec.get("user_type", 0)
        time_label = today_str

        agg_key = (rec_ts, time_label, rec_user_type)
        strat_key = (rec_ts, time_label, strategy_id, rec_user_type)
        strat_only_key = (strategy_id, time_label, rec_user_type)

        # 总表
        total_agg[agg_key]["total_pnl"] += pnl
        if trade_dir == "fall":
            total_agg[agg_key]["fall_pnl"] += pnl
        elif trade_dir == "rise":
            total_agg[agg_key]["rise_pnl"] += pnl

        # 品种策略明细
        detail_agg[strat_key]["count"] += 1
        detail_agg[strat_key]["total_pnl"] += pnl
        if pnl > 0:
            detail_agg[strat_key]["win_count"] += 1
        elif pnl < 0:
            detail_agg[strat_key]["loss_count"] += 1

        # 策略汇总
        strategy_agg[strat_only_key]["count"] += 1
        strategy_agg[strat_only_key]["total_pnl"] += pnl
        if pnl > 0:
            strategy_agg[strat_only_key]["win_count"] += 1
        elif pnl < 0:
            strategy_agg[strat_only_key]["loss_count"] += 1

    # 组装总表
    summary_table = []
    for (ts, t_label, ut), val in total_agg.items():
        account_name = "虚拟盘" if ut == 0 else "实盘"
        summary_table.append({
            "ts_code": ts,
            "时间": t_label,
            "账户类型": account_name,
            "user_type": ut,
            "总盈亏": round(val["total_pnl"], 2),
            "fall盈亏": round(val["fall_pnl"], 2),
            "rise盈亏": round(val["rise_pnl"], 2),
        })
    # 组装明细
    detail_table = []
    for (ts, t_label, sid, ut), val in detail_agg.items():
        total_cnt = val["count"]
        win_rate = round(val["win_count"] / total_cnt * 100, 2) if total_cnt > 0 else 0.0
        loss_rate = round(val["loss_count"] / total_cnt * 100, 2) if total_cnt > 0 else 0.0
        account_name = "虚拟盘" if ut == 0 else "实盘"
        detail_table.append({
            "ts_code": ts,
            "时间": t_label,
            "账户类型": account_name,
            "user_type": ut,
            "策略": sid,
            "次数": total_cnt,
            "总盈亏": round(val["total_pnl"], 2),
            "盈利次数": val["win_count"],
            "盈利胜率(%)": win_rate,
            "亏损次数": val["loss_count"],
            "亏损率(%)": loss_rate,
        })
    # 组装策略汇总
    strategy_report = []
    for (sid, t_label, ut), val in strategy_agg.items():
        total_cnt = val["count"]
        win_rate = round(val["win_count"] / total_cnt * 100, 2) if total_cnt > 0 else 0.0
        loss_rate = round(val["loss_count"] / total_cnt * 100, 2) if total_cnt > 0 else 0.0
        account_name = "虚拟盘" if ut == 0 else "实盘"
        strategy_report.append({
            "策略": sid,
            "时间": t_label,
            "账户类型": account_name,
            "user_type": ut,
            "次数": total_cnt,
            "总盈亏": round(val["total_pnl"], 2),
            "盈利次数": val["win_count"],
            "盈利胜率(%)": win_rate,
            "亏损次数": val["loss_count"],
            "亏损率(%)": loss_rate,
        })
    return summary_table, detail_table, strategy_report



def print_today_log_result(user_type=None):
    """打印trade_log.json今日统计结果，格式和print_stat_result保持一致"""
    summary_table, detail_table, strategy_report = statistics_today_trade_log(user_type=user_type)
    user_type_map = {None: "全部账户", 0: "虚拟盘", 1: "实盘"}
    account_name = user_type_map.get(user_type, str(user_type))

    print("=" * 100)
    print(f"【trade_log.json - 今日交易统计】账户:{account_name}")
    print("=" * 100)

    # ========== 1.总表 ==========
    print("\n===== 总表（品种+日期+账户） =====")
    if not summary_table:
        print("今日无记录")
    else:
        print(f"{'ts_code':<8}{'时间':<10}{'账户类型':<8}{'总盈亏':<10}{'fall盈亏':<10}{'rise盈亏':<10}")
        print("-" * 70)
        for row in summary_table:
            print(
                f"{row['ts_code']:<8}"
                f"{row['时间']:<8}"
                f"{row['账户类型']:<8}"
                f"{row['总盈亏']:<12.2f}"
                f"{row['fall盈亏']:<12.2f}"
                f"{row['rise盈亏']:<12.2f}"
            )

    # ========== 2.品种策略明细 ==========
    print("\n===== 品种策略明细报表（品种+日期+策略+账户） =====")
    if not detail_table:
        print("今日无记录")
    else:
        print(
            f"{'ts_code':<8}{'时间':<10}{'账户类型':<8}{'策略':<12}{'次数':<6}"
            f"{'总盈亏':<12}{'盈利次数':<8}{'胜率(%)':<10}{'亏损次数':<8}{'亏损率(%)':<10}"
        )
        print("-" * 105)
        for row in detail_table:
            print(
                f"{row['ts_code']:<8}"
                f"{row['时间']:<10}"
                f"{row['账户类型']:<8}"
                f"{row['策略']:<12}"
                f"{row['次数']:<6d}"
                f"{row['总盈亏']:<12.2f}"
                f"{row['盈利次数']:<8d}"
                f"{row['盈利胜率(%)']:<10.2f}"
                f"{row['亏损次数']:<8d}"
                f"{row['亏损率(%)']:<10.2f}"
            )

    # ==========3.策略汇总 ==========
    print("\n===== 策略汇总报表（策略+日期+账户） =====")
    if not strategy_report:
        print("今日无记录")
    else:
        print(
            f"{'策略':<12}{'时间':<10}{'账户类型':<8}{'次数':<6}"
            f"{'总盈亏':<12}{'盈利次数':<8}{'胜率(%)':<10}{'亏损次数':<8}{'亏损率(%)':<10}"
        )
        print("-" * 90)
        for row in strategy_report:
            print(
                f"{row['策略']:<12}"
                f"{row['时间']:<8}"
                f"{row['账户类型']:<8}"
                f"{row['次数']:<6d}"
                f"{row['总盈亏']:<12.2f}"
                f"{row['盈利次数']:<8d}"
                f"{row['盈利胜率(%)']:<10.2f}"
                f"{row['亏损次数']:<8d}"
                f"{row['亏损率(%)']:<10.2f}"
            )
    print("\n" + "=" * 100 + "\n")


if __name__ == "__main__":
    # 使用示例，取消注释即可直接运行打印
    # print_stat_result()                                    # trade_records 全部账户，本月，全部品种
    # print_stat_result(user_type=1)                         # trade_records 只看实盘本月
    # print_stat_result(ts_code="c2611", count_date="202609", user_type=0) # trade_records 虚拟盘 c2611，202609
    print_stat_result(count_date="2026")

    # ========= trade_log.json 今日统计示例 =========
    print_today_log_result()              # trade_log 今日，全部账户（虚拟+实盘）
    # print_today_log_result(user_type=0) # trade_log 今日，仅虚拟盘
    # print_today_log_result(user_type=1) # trade_log 今日，仅实盘
