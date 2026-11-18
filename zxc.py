# -*- coding: utf-8 -*-
"""
锁仓持仓行：全平控件 <-> 同行实时盈亏数值 一一对应定位模块
业务背景（同花顺期货通 WPF 持仓面板）：
- 持仓每一行是一个 DataRowView，行内包含：方向(多/空)、合约、手数、价格、盈亏数值、“全平”按钮等 TextBlock。
- “逐笔浮盈”是表头文本，盈亏数值行位于该表头下方，与“全平”处于同一行（top 相同，可能 ±1 像素抖动）。
- 同一行所有控件 hwnd 相同（外层容器），不能用 hwnd 区分行；行绑定依据：top 坐标对齐 + 共同祖先 DataRowView。

返回约定：
- 只要扫描到 >=1 个“全平”控件（1 个单持仓 / 2 个锁仓 / 3 个及以上多持仓），逐行绑定：
    {
        1: {"close_ctrl": 全平控件对象, "pnl": 盈亏值, "variety": "中文品种名", "direction": "多/空", "ts_code": "合约代码"},
        2: { ... }
    }
- “全平”控件数量为 0（或窗口无效 / 扫描异常）：返回 None。
- 每次扫描结果会同步快照到 shared_data.position_data_dict；无持仓时清空该字典。

注意：pywinauto UIA 的 RECT 属性为 .left / .top / .right / .bottom（不是 .T/.L/.R/.B）。
"""
import re
from time import sleep
from core.connect_ths import local_control, is_win_valid, is_around
from pywinauto.controls.uiawrapper import UIAWrapper
from datetime import datetime, timedelta
from public import shared_data
from public.print_context import print_context
from sendmsg.pushplus import send_msg
from core.private import append_close_record
from core.trade import reset_temp_params_in_yaml
from public.jiaoyisuo import get_future_info
from core.monitor import get_today_trade_stat


_PNL_RAW_SYMBOLS = {",", "+", "-", ".", " "}

# 品种代码 -> 中文映射，按需自行扩充
CODE_TO_VARIETY = {
    "m": "豆粕",
    "c": "玉米",
    "jd": "鸡蛋",
    "fg": "玻璃",
    "ma": "纯碱",
    "rb": "螺纹钢",
    "cu": "沪铜",
    "au": "沪金",
    "ag": "沪银"
}

def _is_pnl_text(txt: str) -> bool:
    """判断文本是否像一个盈亏数值（含 +30 / -15 / 30.5 / -- 等占位）。"""
    if txt is None:
        return False
    t = txt.strip()
    if not t:
        return False
    if t in ("--", "-", "—", "暂无"):
        return True
    cleaned = "".join(ch for ch in t if ch not in _PNL_RAW_SYMBOLS)
    return cleaned.isdigit()

def _parse_pnl(txt: str):
    """盈亏文本 -> float；解析失败返回原始字符串。"""
    if txt is None:
        return None
    t = txt.strip().replace(",", "")
    try:
        return float(t)
    except (ValueError, TypeError):
        return txt.strip()

def _iter_text_controls(window):
    """递归遍历窗口内所有 Text 控件（descendants 不支持 title 过滤，文本需自行判断）。"""
    try:
        return window.descendants(control_type="Text")
    except Exception as e:
        print_context(f"[lock_position_profit] 遍历 Text 控件异常：{repr(e)}")
        return []

def _find_row_container(ctrl):
    """
    向上查找所属的 DataRowView 行容器（inspect 祖先："System.Data.DataRowView" 列表项目）。
    找不到返回 None。UIA-to-MSAA bridge 下祖先文本可能不稳定，仅作兜底辅助。
    """
    try:
        for anc in ctrl.ancestors():
            anc_name = ""
            try:
                anc_name = anc.window_text() or ""
            except Exception:
                anc_name = ""
            if "DataRowView" in anc_name:
                return anc
    except Exception:
        pass
    return None

def _match_profit_in_row(close_ctrl, close_rect, text_ctrls, header_left):
    """
    在“全平”所在行内匹配盈亏数值控件。
    匹配优先级：
    1. 同一行（top 与全平 top 误差 <=1）；
    2. 文本为可解析盈亏数值，排除“全平”“多”“空”等方向/按钮文本；
    3. 水平方向优先对齐“逐笔浮盈”表头列（left 与 header_left 距离最近）；
       表头未定位到时，取该行最靠右的数值控件兜底。
    返回 (profit_ctrl, profit_text)；未匹配到返回 (None, None)。
    """
    target_top = close_rect.top
    candidates = []

    for c in text_ctrls:
        try:
            if c is close_ctrl:
                continue
            r = c.rectangle()
        except Exception:
            continue

        # 同行判定：top 容差 1 像素
        if abs(r.top - target_top) > 1:
            continue

        txt = (c.window_text() or "").strip()
        if txt in ("全平", "多", "空", "买多", "卖空"):
            continue
        if not _is_pnl_text(txt):
            continue

        # 与表头列的水平距离；表头缺失时用 right 越大越靠右兜底
        col_dist = abs(r.left - header_left) if header_left is not None else -r.right
        candidates.append((col_dist, r.right, c, txt))

    if not candidates:
        # 兜底：通过共同祖先 DataRowView 在该行容器内再找一次数值控件
        row_container = _find_row_container(close_ctrl)
        if row_container is not None:
            try:
                for c in row_container.descendants(control_type="Text"):
                    txt = (c.window_text() or "").strip()
                    if txt in ("全平", "多", "空", "买多", "卖空"):
                        continue
                    if _is_pnl_text(txt):
                        r = c.rectangle()
                        col_dist = abs(r.left - header_left) if header_left is not None else -r.right
                        candidates.append((col_dist, r.right, c, txt))
            except Exception:
                pass

    if not candidates:
        return None, None
    candidates.sort(key=lambda x: (x[0], -x[1]))
    _, _, profit_ctrl, profit_text = candidates[0]
    return profit_ctrl, profit_text

def _match_text_in_row(close_ctrl, close_rect, text_ctrls, header_left):
    """
    【通用同行文本匹配】专门给品种、多空使用，不做数值过滤！
    同行判定：top 容差 <=1；优先按表头left就近匹配
    header_left=None 直接返回 None，禁止乱抓
    返回 (ctrl, text)
    """
    if header_left is None:
        return None, None
    target_top = close_rect.top
    candidates = []
    for c in text_ctrls:
        try:
            if c is close_ctrl:
                continue
            r = c.rectangle()
        except Exception:
            continue
        if abs(r.top - target_top) > 1:
            continue
        txt = (c.window_text() or "").strip()
        if not txt:
            continue
        dist = abs(r.left - header_left)
        candidates.append((dist, c, txt))
    if not candidates:
        # 容器兜底
        row_container = _find_row_container(close_ctrl)
        if row_container is not None:
            try:
                for c in row_container.descendants(control_type="Text"):
                    txt = (c.window_text() or "").strip()
                    if not txt:
                        continue
                    r = c.rectangle()
                    dist = abs(r.left - header_left)
                    candidates.append((dist, c, txt))
            except Exception:
                pass
    if not candidates:
        return None, None
    candidates.sort(key=lambda x: x[0])
    _, ctrl, txt = candidates[0]
    return ctrl, txt

def _collect_row_all_text(close_ctrl, close_rect, text_ctrls):
    """收集该行全部文本，用于兜底正则解析（适配 玉米2701  1手多仓 -60 这种合并文本）"""
    target_top = close_rect.top
    buf = []
    for c in text_ctrls:
        try:
            r = c.rectangle()
        except Exception:
            continue
        if abs(r.top - target_top) > 1:
            continue
        t = (c.window_text() or "").strip()
        if t:
            buf.append(t)
    return " ".join(buf)

def _normalize_direction(raw_txt: str):
    """归一化为 多 / 空，识别：买、多仓、卖、空仓"""
    if not raw_txt:
        return None
    s = raw_txt.lower()
    if any(k in s for k in ["多", "买"]):
        return "多"
    if any(k in s for k in ["空", "卖"]):
        return "空"
    return None

def _parse_variety_from_text(raw: str):
    """从整行文本提取中文品种名；取不到则用代码映射"""
    if not raw:
        return None
    # 优先提取中文
    chinese_list = re.findall(r"[\u4e00-\u9fa5]+", raw)
    if chinese_list:
        # 过滤掉 多仓、空仓、手 这类词
        ban_list = {"多仓", "空仓", "手", "仓"}
        for item in chinese_list:
            if item not in ban_list:
                return item
    # 提取合约前缀，匹配品种字典
    m = re.search(r"^([a-zA-Z]+)\d+", raw.replace(" ", ""))
    if m:
        code = m.group(1).lower()
        if code in CODE_TO_VARIETY:
            return CODE_TO_VARIETY[code]
    return None

def _parse_ts_code_from_text(raw: str):
    """从整行文本提取完整合约代码（如 m2701 / c2701）；取不到返回 None。"""
    if not raw:
        return None
    m = re.search(r"([a-zA-Z]+\d{3,4})", raw.replace(" ", ""))
    if m:
        return m.group(1).lower()
    return None

def match_close_and_profit(window=None):
    """
    主入口：定位两个“全平”持仓行，并逐一绑定同行：盈亏、品种(中文)、多空
    :param window: 可选，传入交易主窗口；为空则取 shared_data.trade_window
    :return:
        {
            1: {
                "close_ctrl": 全平控件对象,
                "pnl": 盈亏数值,
                "variety": "玉米 / 豆粕 中文品种名",
                "direction": "多 / 空"
            },
            2: { ... }
        }
        全平数量不为 2 / 窗口无效 / 扫描异常时返回 None。
    """
    # 1. 取窗口（加锁，避免与其他线程并发读写 trade_window）
    from public import shared_data
    if window is None:
        if shared_data is not None and hasattr(shared_data, "trade_window"):
            try:
                with shared_data.ctrl_rlock:
                    window = shared_data.trade_window
            except Exception:
                window = shared_data.trade_window
        else:
            window = None

    if window is None or not is_win_valid(window):
        print_context("[lock_position_profit] 交易主窗口无效，无法定位全平/盈亏控件，返回 None")
        return None

    try:
        text_ctrls = _iter_text_controls(window)

        if not text_ctrls:
            print_context("[lock_position_profit] 未扫描到任何 Text 控件，返回 None")
            return None

        # 表头别名池，自动匹配，不用反复改
        header_alias = {
            "pnl": ["逐笔浮盈"],
            "variety": ["品种", "合约名称", "名称"],
            "direction": ["多空", "买卖", "方向"]
        }
        header_map = {"pnl": None, "variety": None, "direction": None}
        debug_header_list = []

        for c in text_ctrls:
            try:
                txt = (c.window_text() or "").strip()
                rect = c.rectangle()
                debug_header_list.append(txt)
                if txt in header_alias["pnl"]:
                    header_map["pnl"] = rect.left
                elif txt in header_alias["variety"]:
                    header_map["variety"] = rect.left
                elif txt in header_alias["direction"]:
                    header_map["direction"] = rect.left
            except Exception:
                continue

        # print_context(f"[lock_position_profit] 【调试】面板全部静态文本：{debug_header_list}")
        # print_context(f"[lock_position_profit] 表头基准left：{header_map}")

        # 收集所有“全平”控件，按 top 从小到大排序（上面一行 = 1，下面一行 = 2）
        close_list = []
        for c in text_ctrls:
            try:
                txt = (c.window_text() or "").strip()
                if txt != "全平":
                    continue
                rect = c.rectangle()
                close_list.append((rect.top, c, rect))
            except Exception:
                continue
        close_list.sort(key=lambda x: x[0])

        # 数量校验：只要扫描到“全平”控件即视为有持仓，1 个 / 2 个 / 多个均逐行绑定；
        # 仅当 0 个时判定无持仓，清空持仓快照并返回 None。
        if len(close_list) == 0:
            with shared_data.dict_rlock:
                shared_data.position_data_dict.clear()
            print_context("[lock_position_profit] 未定位到“全平”控件，当前无持仓，返回 None")
            return None

        result = {}
        for idx, (_, close_ctrl, close_rect) in enumerate(close_list, start=1):
            # 逐笔浮盈（沿用原有盈亏匹配函数）
            if header_map["pnl"] is not None:
                _, profit_text = _match_profit_in_row(close_ctrl, close_rect, text_ctrls, header_map["pnl"])
            else:
                profit_text = None
            pnl_value = _parse_pnl(profit_text) if profit_text is not None else None

            # 品种：优先列匹配，失败走整行兜底解析
            _, variety_text = _match_text_in_row(close_ctrl, close_rect, text_ctrls, header_map["variety"])
            row_all_text = _collect_row_all_text(close_ctrl, close_rect, text_ctrls)
            if not variety_text:
                variety_text = _parse_variety_from_text(row_all_text)

            # 多空：优先列匹配，失败走整行兜底解析
            _, dir_raw = _match_text_in_row(close_ctrl, close_rect, text_ctrls, header_map["direction"])
            direction_text = _normalize_direction(dir_raw)
            if not direction_text:
                direction_text = _normalize_direction(row_all_text)

            # 合约代码：优先整行文本提取，取不到兜底全局当前代码
            ts_code_text = _parse_ts_code_from_text(row_all_text) or shared_data.ts_code or ""

            row_data = {
                "close_ctrl": close_ctrl,
                "pnl": pnl_value,
                "variety": variety_text,
                "direction": direction_text,
                "ts_code": ts_code_text
            }
            result[idx] = row_data
            print_context(
                f"[lock_position_profit] 第 {idx} 行：全平 top={close_rect.top} "
                f"整行=[{row_all_text}] 盈亏={profit_text}({pnl_value}) | 品种={variety_text} | 代码={ts_code_text} | 多空={direction_text}"
            )

        # 同步持仓行快照到全局 position_data_dict（加锁，供其他线程读取）
        snapshot = {
            k: {
                "close_ctrl": v["close_ctrl"],
                "pnl": v["pnl"],
                "variety": v["variety"],
                "direction": v["direction"],
                "ts_code": v.get("ts_code")
            }
            for k, v in result.items()
        }
        with shared_data.dict_rlock:
            shared_data.position_data_dict.clear()
            shared_data.position_data_dict.update(snapshot)

        return result

    except Exception as e:
        print_context(f"[lock_position_profit] 定位全平/盈亏异常：{repr(e)}")
        return None

def is_lock_position():
    """
    锁仓状态轮询线程函数
    循环检测持仓面板是否同时存在【手多仓】、【手空仓】文本
    - 同时存在 → 锁仓：开启锁仓监控线程，关闭普通监控
    - 不同时存在 → 非锁仓：开启普通监控线程，关闭锁仓监控
    循环间隔 1s，依赖 shared_data 两个flag控制线程启停
    """
    from public import shared_data
    print_context("[is_lock_position] 锁仓状态轮询线程已启动")
    print_flag = True
    while True:
        try:
            # 窗口读取加锁
            with shared_data.ctrl_rlock:
                window = shared_data.trade_window
            if window is None or not is_win_valid(window):
                sleep(1)
                continue
            with shared_data.ctrl_rlock:
                text_ctrls = shared_data.ths_common_control["盈亏"][0].window_text().strip()
                # print(f"\r读取到的盈亏控件文本：{text_ctrls}", flush=True, end="")
            has_duo = False
            has_kong = False
            try:
                if "手多仓" in text_ctrls:
                    has_duo = True
                if "手空仓" in text_ctrls:
                    has_kong = True
            except Exception:
                continue

            # 判定锁仓：两个文本同时出现
            if has_duo and has_kong:
                # 锁仓状态：启动锁仓监控，关闭普通监控
                with shared_data.ctrl_rlock:
                    if print_flag:
                        print_context("[is_lock_position] 检测到锁仓，切换至锁仓监控线程")
                        print_flag = False
                    shared_data.monitor_thread_flag = False
                    shared_data.monitor_lock_position_thread_flag = True
            else:
                # 【修复之前bug】非锁仓：开启普通监控，关闭锁仓监控
                with shared_data.ctrl_rlock:
                    if print_flag:
                        print_context("[is_lock_position] 未检测到锁仓，切换至普通监控线程")
                        print_flag = False
                    shared_data.monitor_thread_flag = True
                    shared_data.monitor_lock_position_thread_flag = False

        except Exception as e:
            print_context(f"[is_lock_position] 轮询异常：{repr(e)}")
        sleep(1)


def monitor_lock_position_profit_loss():
    """
    锁仓状态的监控操作
    常驻线程，flag=False时空转；flag=True读取两行持仓，本行独立全平控件平仓
    本轮完整扫描所有持仓行，收集命中候选，最多平一行，避免后行饿死
    锁仓平仓不设置冷却、不重置YAML临时参数
    """
    print_flag = True
    print_context("LockMonitorThread 锁仓盈亏监控线程已启动")
    while True:
        try:
            # 非锁仓状态：空转
            if not shared_data.monitor_lock_position_thread_flag:
                if print_flag:
                    print_context(f"现在是非锁仓状态 - 【{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}】")
                    print_flag = False
                sleep(1)
                continue
            print_flag = True

            # 开市校验
            if not shared_data.trade_flag():
                print(f"\r锁仓监控：未开市，等待开市 [{datetime.now().strftime('%H:%M:%S')}]", flush=True, end="")
                sleep(1)
                continue

            # 读取止盈止损阈值
            with shared_data.variables_rlock:
                pre_profit = shared_data.pre_profit
                pre_loss = shared_data.pre_loss

            ths_win_data = match_close_and_profit()
            if ths_win_data is None:
                sleep(1)
                continue

            # 第一步：完整遍历全部行，收集命中候选，不提前break
            candidate_list = []
            for idx, row in ths_win_data.items():
                try:
                    pnl = float(row["pnl"])
                    close_ctrl = row["close_ctrl"]
                    variety = row["variety"]
                    direction = row["direction"]
                    lots = shared_data.tscode_lots_dict.get(variety, 1)
                    strategy_id = shared_data.trade_menu_dict.get("rule_id", "unknow")
                    trade_period = shared_data.trade_menu_dict.get("trade_period", "")
                    total_pre_profit = pre_profit * lots
                    total_pre_loss = pre_loss * lots

                    close_reason = ""
                    hit = False
                    # 止盈触发
                    if pre_profit > 0 and pnl >= total_pre_profit - 0.02:
                        close_reason = f"【锁仓行{idx}-{direction}】止盈平仓，单手目标{pre_profit:.2f}，{lots}手合计目标{total_pre_profit:.2f}\n当前浮动盈利：{pnl:.2f}元"
                        hit = True
                    # 止损触发
                    elif pre_loss < 0 and pnl <= total_pre_loss + 0.02:
                        close_reason = f"【锁仓行{idx}-{direction}】止损平仓，单手目标{pre_loss:.2f}，{lots}手合计目标{total_pre_loss:.2f}\n当前浮动亏损：{pnl:.2f}元"
                        hit = True

                    if hit:
                        candidate_list.append({
                            "idx": idx,
                            "row": row,
                            "close_reason": close_reason,
                            "pnl": pnl,
                            "variety": variety,
                            "direction": direction,
                            "lots": lots,
                            "strategy_id": strategy_id,
                            "trade_period": trade_period
                        })
                except Exception as row_err:
                    print_context(f"锁仓单行读取异常，跳过该行：{str(row_err)}")
                    continue

            # 第二步：本轮只处理第一个命中的候选，最多平一行
            if candidate_list:
                first_hit = candidate_list[0]
                row = first_hit["row"]
                close_ctrl = row["close_ctrl"]
                variety = first_hit["variety"]
                pnl = first_hit["pnl"]
                close_reason = first_hit["close_reason"]
                lots = first_hit["lots"]
                strategy_id = first_hit["strategy_id"]
                trade_period = first_hit["trade_period"]

                # UI操作加锁
                with shared_data.ctrl_rlock:
                    close_ctrl.click_input()
                print_context(f"锁仓监控触发平仓：{close_reason}")

                # 手续费、统计、推送
                fut_info = get_future_info(variety, 0)
                per_lot_two_way_fee = fut_info.get('fee', 0) * 2
                total_fee = per_lot_two_way_fee * lots
                net_profit = pnl - total_fee
                ut = getattr(shared_data, "user_type", 0)
                append_close_record(user_type=ut, pnl=pnl, ts_code=variety, strategy_id=strategy_id, trade_period=trade_period)
                stat = get_today_trade_stat()
                sim_cnt, sim_pnl = stat["sim_user"]
                real_cnt, real_pnl = stat["real_user"]
                full_msg = (
                    f"{close_reason}\n"
                    f"本次平仓手数：{lots}手\n"
                    f"市值盈亏（涨跌差价）：{pnl:.2f}元\n"
                    f"本次双边手续费：{total_fee:.2f}元\n"
                    f"✅纯利润：{net_profit:.2f}元\n"
                    f"------------ 今日平仓汇总 ------------\n"
                    f"【模拟账户】平仓次数：{sim_cnt}，累计毛盈亏：{sim_pnl:.2f}元\n"
                    f"【实盘账户】平仓次数：{real_cnt}，累计毛盈亏：{real_pnl:.2f}元"
                )
                send_msg(f"【锁仓监控】自动平仓成功 - 品种：{variety}\n{full_msg}")

            sleep(1)
        except Exception as top_err:
            err_msg = f"【锁仓监控顶层异常】{str(top_err)}"
            print_context(err_msg)
            send_msg(err_msg)
            sleep(1)
            continue


def close_single_position(window=None) -> bool:
    """
    单持仓平仓函数（非锁仓场景）：
    - 调用 match_close_and_profit 扫描持仓行；
    - 仅当持仓记录恰好 1 条时，按 shared_data.pre_profit / pre_loss 判断止盈止损；
    - 命中则点击该行“全平”控件平仓，随后计算手续费、写入平仓记录、汇总统计并推送消息；
    - 多条持仓（锁仓 / 多持仓）交由 monitor_lock_position_profit_loss 处理，本函数不平。

    :param window: 可选交易主窗口，为空取 shared_data.trade_window
    :return: True=已触发平仓；False=无持仓 / 非单条 / 未命中 / 平仓失败
    """
    ths_win_data = match_close_and_profit(window)
    if not ths_win_data:
        return False

    # 仅处理单条持仓；多条交锁仓监控
    if len(ths_win_data) != 1:
        return False

    row = next(iter(ths_win_data.values()))
    close_ctrl = row.get("close_ctrl")
    pnl_raw = row.get("pnl")
    variety = row.get("variety")
    direction = row.get("direction")
    ts_code = (row.get("ts_code")
               or shared_data.trade_menu_dict.get("ts_code")
               or shared_data.trade_menu_dict.get("产品代码")
               or shared_data.ts_code or "")

    if close_ctrl is None or pnl_raw is None:
        print_context("[close_single_position] 单条持仓缺少平仓控件或盈亏值，跳过")
        return False

    try:
        pnl = float(pnl_raw)
    except (ValueError, TypeError):
        print_context(f"[close_single_position] 盈亏值无法解析：{pnl_raw}，跳过")
        return False

    # 读取止盈止损阈值
    with shared_data.variables_rlock:
        pre_profit = shared_data.pre_profit
        pre_loss = shared_data.pre_loss

    # 手数：优先按合约代码查，兜底品种名，最后默认 1 手
    lots = shared_data.tscode_lots_dict.get(ts_code)
    if lots is None:
        lots = shared_data.tscode_lots_dict.get(variety, 1)
    lots = lots or 1

    strategy_id = shared_data.trade_menu_dict.get("rule_id", "unknow")
    trade_period = shared_data.trade_menu_dict.get("trade_period", "")
    total_pre_profit = pre_profit * lots
    total_pre_loss = pre_loss * lots

    close_reason = ""
    hit = False
    # 止盈触发
    if pre_profit > 0 and pnl >= total_pre_profit - 0.02:
        close_reason = (f"【单持仓-{direction}】止盈平仓，单手目标{pre_profit:.2f}，"
                        f"{lots}手合计目标{total_pre_profit:.2f}\n当前浮动盈利：{pnl:.2f}元")
        hit = True
    # 止损触发
    elif pre_loss < 0 and pnl <= total_pre_loss + 0.02:
        close_reason = (f"【单持仓-{direction}】止损平仓，单手目标{pre_loss:.2f}，"
                        f"{lots}手合计目标{total_pre_loss:.2f}\n当前浮动亏损：{pnl:.2f}元")
        hit = True

    if not hit:
        return False

    try:
        # UI 操作加锁：聚焦窗口后点击该行全平控件
        with shared_data.ctrl_rlock:
            shared_data.trade_window.maximize()
            shared_data.trade_window.set_focus()
            sleep(0.5)
            close_ctrl.click_input()
        print_context(f"close_single_position 触发平仓：{close_reason}")

        # 手续费、净利
        fut_info = get_future_info(ts_code, 0) if ts_code else None
        per_lot_two_way_fee = (fut_info.get('fee', 0) * 2) if fut_info else 0
        total_fee = per_lot_two_way_fee * lots
        net_profit = pnl - total_fee

        # 平仓成功后设置冷却，避免立即复购
        with shared_data.variables_rlock:
            shared_data.valid_time = datetime.now() + timedelta(minutes=shared_data.valid_trade_interval)
            print_context(f"【平仓点击成功，设置冷却】下次交易有效时间起点：{shared_data.valid_time}")

        # 存档 + 今日汇总
        ut = getattr(shared_data, "user_type", 0)
        append_close_record(user_type=ut, pnl=pnl, ts_code=ts_code or variety,
                            strategy_id=strategy_id, trade_period=trade_period)
        stat = get_today_trade_stat()
        sim_cnt, sim_pnl = stat["sim_user"]
        real_cnt, real_pnl = stat["real_user"]
        full_msg = (
            f"{close_reason}\n"
            f"本次平仓手数：{lots}手\n"
            f"市值盈亏（涨跌差价）：{pnl:.2f}元\n"
            f"本次双边手续费：{total_fee:.2f}元\n"
            f"✅纯利润：{net_profit:.2f}元\n"
            f"------------ 今日平仓汇总 ------------\n"
            f"【模拟账户】平仓次数：{sim_cnt}，累计毛盈亏：{sim_pnl:.2f}元\n"
            f"【实盘账户】平仓次数：{real_cnt}，累计毛盈亏：{real_pnl:.2f}元"
        )
        send_msg(f"【单持仓监控】自动平仓成功 - 品种：{variety or ts_code}\n{full_msg}")

        # 重置 YAML 临时参数（对齐普通监控平仓动作）
        reset_temp_params_in_yaml()
        return True

    except Exception as e:
        err_msg = f"【单持仓平仓异常】{str(e)}"
        print_context(err_msg)
        send_msg(err_msg)
        return False


if __name__ == "__main__":
    # 独立调试入口：直接连接当前已登录的同花顺主窗口跑一遍
    local_control()
    res = match_close_and_profit()
    print("匹配结果：", res)
    is_lock_position()