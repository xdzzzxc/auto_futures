# -*- coding: utf-8 -*-
"""
多仓（原锁仓）持仓行：全平控件 <-> 同行实时盈亏数值 一一对应定位模块

业务背景（同花顺期货通 WPF 持仓面板）：
- 持仓每一行是一个 DataRowView，行内包含：方向(多/空)、合约、手数、价格、盈亏数值、“全平”按钮等 TextBlock。
- “逐笔浮盈”是表头文本，盈亏数值行位于该表头下方，与“全平”处于同一行（top 相同，可能 ±1 像素抖动）。
- 同一行所有控件 hwnd 相同（外层容器），不能用 hwnd 区分行；行绑定依据：top 坐标对齐 + 共同祖先 DataRowView。

仓型判定（按“全平”控件行数，不再依赖“手多仓/手空仓”文本）：
- 全平控件 == 1  → 单仓：普通监控 / close_single_position 处理
- 全平控件 >= 2  → 多仓（锁仓 / 多持仓）：多仓监控线程逐行独立全平处理

返回约定：
- 只要扫描到 >=1 个“全平”控件（1 个单仓 / 2 个及以上多仓），逐行绑定：
    {
        1: {"close_ctrl": 全平控件对象, "pnl": 盈亏值, "variety": "中文品种名", "direction": "多/空", "ts_code": "合约代码"},
        2: { ... }
    }
- “全平”控件数量为 0（或窗口无效 / 扫描异常）：返回 None。
- 每次扫描结果会同步快照到 shared_data.position_data_dict；无持仓时清空该字典。

性能优化（控件句柄缓存）：
- 首次 / 行数变化 / 控件失效时，做一次全量 UIA 定位，把每行的 全平、盈亏、品种、方向 控件句柄缓存起来；
- 后续轮次不再全量遍历 descendants、不再逐控件算 rectangle 匹配，直接复用缓存句柄只读 .window_text() 刷新盈亏；
- 每 RESCAN_INTERVAL 轮强制做一次全量行数核对，兜底发现中途开仓 / 平仓导致的行数变化；
- 单行连续 STALE_LIMIT 次读取失效（stale element）后，触发全量重扫。

注意：pywinauto UIA 的 RECT 属性为 .left / .top / .right / .bottom（不是 .T/.L/.R/.B）。
"""

import re
import threading
from time import sleep
from datetime import datetime, timedelta

from core.connect_ths import local_control, is_win_valid, is_around
from pywinauto.controls.uiawrapper import UIAWrapper

from public import shared_data
from public.print_context import print_context
from sendmsg.pushplus import send_msg
from core.private import append_close_record
from core.trade import reset_temp_params_in_yaml
from public.jiaoyisuo import get_future_info
from core.monitor import get_today_trade_stat


# 缓存轮询参数
RESCAN_INTERVAL = 2      # 每 N 轮做一次全量行数核对；中间轮次纯读缓存控件3-4秒比较合适
STALE_LIMIT = 2          # 单行连续读取失效次数阈值，达到后触发全量重扫3次比较合适

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


# ----------------------------------------------------------------------------
# 控件句柄缓存
# ----------------------------------------------------------------------------
class _PosControlCache:
    """
    持仓行控件缓存：
    - rows: {idx: {"close_ctrl", "pnl_ctrl", "variety_ctrl", "dir_ctrl",
                    "variety", "direction", "ts_code", "top"}}
    - 仅缓存控件句柄与稳定字段（品种/方向/代码），盈亏每轮从句柄实时读取，不缓存盈亏结果。
    """

    def __init__(self):
        self.lock = threading.RLock()
        self.window = None
        self.rows = {}
        self.row_count = 0
        self.stale_cnt = {}
        self.round = 0

    def reset(self):
        self.window = None
        self.rows = {}
        self.row_count = 0
        self.stale_cnt = {}
        self.round = 0


_POS_CACHE = _PosControlCache()


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


# 界面按钮 / 状态词，不属于品种名，兜底解析时需排除
_UI_WORDS = {"全平", "反手", "止", "盈", "亏", "多", "空", "买", "卖",
             "多仓", "空仓", "手", "仓", "普通交易", "投机", "交易", "平仓"}


def _parse_variety_from_text(raw: str):
    """从整行文本提取中文品种名；取不到则用代码映射"""
    if not raw:
        return None
    # 优先提取中文
    chinese_list = re.findall(r"[\u4e00-\u9fa5]+", raw)
    variety_set = set(CODE_TO_VARIETY.values())
    # 1) 优先命中品种字典里的标准中文名（如 玉米 / 豆粕）
    for item in chinese_list:
        if item in variety_set:
            return item
    # 2) 其次取第一个非界面词的中文片段
    for item in chinese_list:
        if item not in _UI_WORDS:
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


# ----------------------------------------------------------------------------
# 全量定位（仅在首次 / 行数变化 / 控件失效时调用）
# ----------------------------------------------------------------------------
def _full_scan(window):
    """
    全量遍历 UIA 定位全部持仓行，绑定同行 盈亏 / 品种 / 多空 / 合约代码，并缓存控件句柄。
    :return: (result, rows_cache)；无持仓 / 窗口无效 / 异常时返回 (None, None)
    """
    try:
        text_ctrls = _iter_text_controls(window)
        if not text_ctrls:
            print_context("[lock_position_profit] 未扫描到任何 Text 控件，返回 None")
            return None, None

        # 表头别名池，自动匹配，不用反复改
        header_alias = {
            "pnl": ["逐笔浮盈"],
            "variety": ["品种", "合约名称", "名称"],
            "direction": ["多空", "买卖", "方向"]
        }
        header_map = {"pnl": None, "variety": None, "direction": None}

        for c in text_ctrls:
            try:
                txt = (c.window_text() or "").strip()
                rect = c.rectangle()
                if txt in header_alias["pnl"]:
                    header_map["pnl"] = rect.left
                elif txt in header_alias["variety"]:
                    header_map["variety"] = rect.left
                elif txt in header_alias["direction"]:
                    header_map["direction"] = rect.left
            except Exception:
                continue

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

        # 数量校验：0 个判定无持仓，清空持仓快照并返回 None
        if len(close_list) == 0:
            with shared_data.dict_rlock:
                shared_data.position_data_dict.clear()
            print_context("[lock_position_profit] 未定位到“全平”控件，当前无持仓，返回 None")
            return None, None

        result = {}
        rows_cache = {}

        for idx, (_, close_ctrl, close_rect) in enumerate(close_list, start=1):
            # 逐笔浮盈（沿用原有盈亏匹配函数）
            if header_map["pnl"] is not None:
                profit_ctrl, profit_text = _match_profit_in_row(
                    close_ctrl, close_rect, text_ctrls, header_map["pnl"]
                )
            else:
                profit_ctrl, profit_text = None, None
            pnl_value = _parse_pnl(profit_text) if profit_text is not None else None

            # 品种：优先列匹配，失败走整行兜底解析
            variety_ctrl, variety_text = _match_text_in_row(
                close_ctrl, close_rect, text_ctrls, header_map["variety"]
            )
            row_all_text = _collect_row_all_text(close_ctrl, close_rect, text_ctrls)
            # 列匹配抓到的若是合约代码（如 c2701 / m2701），说明该列是合约代码列，丢弃后走整行文本兜底取中文品种名
            if variety_text and re.match(r"^[a-zA-Z]+\d{3,4}$", variety_text.strip()):
                variety_text = None
            if not variety_text:
                variety_text = _parse_variety_from_text(row_all_text)

            # 多空：优先列匹配，失败走整行兜底解析
            dir_ctrl, dir_raw = _match_text_in_row(
                close_ctrl, close_rect, text_ctrls, header_map["direction"]
            )
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

            rows_cache[idx] = {
                "close_ctrl": close_ctrl,
                "pnl_ctrl": profit_ctrl,
                "variety_ctrl": variety_ctrl,
                "dir_ctrl": dir_ctrl,
                "variety": variety_text,
                "direction": direction_text,
                "ts_code": ts_code_text,
                "top": close_rect.top,
            }

        return result, rows_cache

    except Exception as e:
        print_context(f"[lock_position_profit] 定位全平/盈亏异常：{repr(e)}")
        return None, None


# ----------------------------------------------------------------------------
# 增量刷新：复用缓存控件句柄，只读文本，不再全量遍历
# ----------------------------------------------------------------------------
def _refresh_from_cache(cache: _PosControlCache):
    """
    基于缓存控件句柄读取最新盈亏文本。
    :return: 对外结构 result；若整行失效 / 行数对不上则返回 None，交由全量重扫。
    """
    with cache.lock:
        rows_snapshot = {k: dict(v) for k, v in cache.rows.items()}
        cached_count = cache.row_count
        stale_cnt = dict(cache.stale_cnt)

    result = {}
    alive = 0

    for idx, item in rows_snapshot.items():
        try:
            # 盈亏：实时读盈亏控件文本
            pnl_ctrl = item.get("pnl_ctrl")
            pnl_value = None
            if pnl_ctrl is not None:
                pnl_text = (pnl_ctrl.window_text() or "").strip()
                pnl_value = _parse_pnl(pnl_text)

            # 品种：优先复用缓存中文品种名；若品种句柄可读且不是代码列，则刷新
            variety = item.get("variety")
            variety_ctrl = item.get("variety_ctrl")
            if variety_ctrl is not None:
                try:
                    vt = (variety_ctrl.window_text() or "").strip()
                    if vt and not re.match(r"^[a-zA-Z]+\d{3,4}$", vt):
                        variety = vt
                except Exception:
                    pass

            # 多空：优先读方向句柄，失败沿用缓存方向
            direction = item.get("direction")
            dir_ctrl = item.get("dir_ctrl")
            if dir_ctrl is not None:
                try:
                    dt = _normalize_direction(dir_ctrl.window_text())
                    if dt:
                        direction = dt
                except Exception:
                    pass

            ts_code = item.get("ts_code") or ""

            result[idx] = {
                "close_ctrl": item["close_ctrl"],
                "pnl": pnl_value,
                "variety": variety,
                "direction": direction,
                "ts_code": ts_code,
            }
            alive += 1
            stale_cnt[idx] = 0
        except Exception:
            stale_cnt[idx] = stale_cnt.get(idx, 0) + 1
            if stale_cnt[idx] >= STALE_LIMIT:
                print_context(f"[lock_position_profit] 第 {idx} 行控件连续 {STALE_LIMIT} 次读取失效，触发全量重扫")
                with cache.lock:
                    cache.stale_cnt = stale_cnt
                return None
            continue

    # 一行都没读到，或存活行数与缓存不一致（中途平仓 / 新开），交全量核对
    if alive == 0 or alive != cached_count:
        return None

    with cache.lock:
        cache.stale_cnt = stale_cnt
    return result


def _snapshot_position_data(result: dict) -> None:
    """把本轮持仓结果快照到全局 position_data_dict（加锁，供其他线程读取）。"""
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


# ----------------------------------------------------------------------------
# 对外主入口（函数名 / 签名 / 返回结构保持不变）
# ----------------------------------------------------------------------------
def match_close_and_profit(window=None):
    """
    主入口：扫描全部“全平”持仓行（1 个单仓 / 2 个及以上多仓），逐一绑定同行：盈亏、品种(中文)、多空、合约代码。

    控件缓存策略：
    - 缓存命中且行数未变：复用缓存句柄只读文本，不再全量 UIA 遍历；
    - 首次 / 每 RESCAN_INTERVAL 轮核对 / 行数变化 / 控件连续失效：全量重新定位并刷新缓存。

    :param window: 可选，传入交易主窗口；为空则取 shared_data.trade_window
    :return:
        {
            1: {"close_ctrl": 全平控件对象, "pnl": 盈亏值, "variety": "玉米 / 豆粕 中文品种名",
                "direction": "多 / 空", "ts_code": "合约代码"},
            2: { ... }
        }
        全平数量为 0 / 窗口无效 / 扫描异常时返回 None。
    """
    # 1. 取窗口（加锁，避免与其他线程并发读写 trade_window）
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

    cache = _POS_CACHE
    with cache.lock:
        # 窗口对象切换（重连 / 换窗）：清空旧缓存
        if cache.window is not None and cache.window is not window:
            cache.reset()
        cache.window = window
        cache.round += 1
        need_rescan = (cache.row_count == 0) or (cache.round % RESCAN_INTERVAL == 0)

    # 2. 缓存命中：增量读文本
    if not need_rescan:
        result = _refresh_from_cache(cache)
        if result is not None:
            _snapshot_position_data(result)
            return result

    # 3. 全量定位并刷新缓存
    result, rows_cache = _full_scan(window)
    with cache.lock:
        if result is None:
            cache.reset()
        else:
            cache.rows = rows_cache
            cache.row_count = len(rows_cache)
            cache.stale_cnt = {k: 0 for k in rows_cache}

    if result is not None:
        _snapshot_position_data(result)
    return result


def is_lock_position():
    """
    持仓结构轮询线程函数
    仓型判定依据：持仓面板上“全平”控件的行数（同一行 hwnd 相同，按 top 对齐绑定），
    不再读取“手多仓 / 手空仓”文本：
    - 全平控件 == 1  → 单仓：开启普通监控线程（monitor_thread_flag=True），关闭多仓监控
    - 全平控件 >= 2  → 多仓（锁仓 / 多持仓）：开启多仓监控线程（monitor_multi_position_thread_flag=True），关闭普通监控
    - 0 个 / 窗口无效 / 扫描异常（match_close_and_profit 返回 None）：保持当前两个 flag 不变，等待下一轮自愈
    循环间隔 1s；flag 名称沿用历史命名（lock_position 即多仓监控），其他线程仍按原名读取。
    """
    from public import shared_data
    print_context("[is_lock_position] 持仓结构轮询线程已启动（单仓 / 多仓判定）")
    last_state = None  # None / "single" / "multi"

    while True:
        try:
            win_data = match_close_and_profit()

            # 扫描不到持仓（无持仓 / 窗口无效 / 控件遍历异常）：不翻动监控 flag，避免短暂丢控件导致监控线程被误切
            if not win_data:
                if last_state is not None:
                    print_context("[is_lock_position] 本轮未扫描到持仓行，保持当前监控状态，等待下一轮自愈")
                    last_state = None
                sleep(1)
                continue

            row_count = len(win_data)

            if row_count >= 2:
                # 多仓（锁仓 / 多持仓）：逐行独立全平，交多仓监控线程处理
                with shared_data.ctrl_rlock:
                    shared_data.monitor_thread_flag = False
                    shared_data.monitor_multi_position_thread_flag = True
                if last_state != "multi":
                    print_context(f"[is_lock_position] 检测到 {row_count} 个持仓行（多仓/锁仓），切换至多仓监控线程")
                    last_state = "multi"
            else:
                # 单仓：交普通监控 / close_single_position 处理
                with shared_data.ctrl_rlock:
                    shared_data.monitor_thread_flag = True
                    shared_data.monitor_multi_position_thread_flag = False
                if last_state != "single":
                    print_context(f"[is_lock_position] 检测到 1 个持仓行（单仓），切换至普通监控线程")
                    last_state = "single"

        except Exception as e:
            print_context(f"[is_lock_position] 轮询异常：{repr(e)}")
        sleep(1)


def monitor_multi_position_profit_loss():
    """
    多仓（锁仓 / 多持仓）状态的监控操作
    常驻线程，flag=False时空转；flag=True读取全部持仓行，本行独立全平控件平仓
    本轮完整扫描所有持仓行，收集命中候选，最多平一行，避免后行饿死
    多仓平仓不设置冷却、不重置YAML临时参数
    """
    print_flag = True
    pending_close = set()
    print_context("LockMonitorThread 多仓盈亏监控线程已启动")
    while True:
        try:
            # 非多仓状态：空转
            if not shared_data.monitor_multi_position_thread_flag:
                if print_flag:
                    print_context(f"现在是单仓/无持仓状态 - 【{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}】")
                    print_flag = False
                sleep(1)
                continue
            print_flag = True

            # 开市校验
            if not shared_data.trade_flag():
                print(f"\r多仓监控：未开市，等待开市 [{datetime.now().strftime('%H:%M:%S')}]", flush=True, end="")
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

            # 多仓交易状态信息显示
            status_parts = []
            for idx, row in ths_win_data.items():
                pnl = float(row["pnl"])
                variety = row["variety"]
                direction = row["direction"]
                status_parts.append(f"{variety}-{direction} [{pnl:.2f}]")
            status_str = " | ".join(status_parts)
            print(f"\r【多仓监控】 {datetime.now().strftime('%H:%M:%S')} | {status_str}", flush=True, end="")

            # 第一步：完整遍历全部行，收集命中候选，不提前break
            candidate_list = []
            for idx, row in ths_win_data.items():
                try:
                    pnl = float(row["pnl"])
                    close_ctrl = row["close_ctrl"]
                    variety = row["variety"]
                    direction = row["direction"]
                    ts_code = row.get("ts_code") or ""
                    # 手数：优先完整合约代码，其次合约前缀，再次品种名，最后默认 1 手
                    lots = shared_data.tscode_lots_dict.get(ts_code)
                    if lots is None and ts_code:
                        lots = shared_data.tscode_lots_dict.get(ts_code[:-4])
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
                        close_reason = f"【多仓行{idx}-{direction}】止盈平仓，单手目标{pre_profit:.2f}，{lots}手合计目标{total_pre_profit:.2f}\n当前浮动盈利：{pnl:.2f}元"
                        hit = True
                    # 止损触发
                    elif pre_loss < 0 and pnl <= total_pre_loss + 0.02:
                        close_reason = f"【多仓行{idx}-{direction}】止损平仓，单手目标{pre_loss:.2f}，{lots}手合计目标{total_pre_loss:.2f}\n当前浮动亏损：{pnl:.2f}元"
                        hit = True

                    if hit:
                        candidate_list.append({
                            "idx": idx,
                            "row": row,
                            "close_reason": close_reason,
                            "pnl": pnl,
                            "variety": variety,
                            "ts_code": ts_code,
                            "direction": direction,
                            "lots": lots,
                            "strategy_id": strategy_id,
                            "trade_period": trade_period
                        })
                except Exception as row_err:
                    print_context(f"多仓单行读取异常，跳过该行：{str(row_err)}")
                    continue

            # 第二步：遍历本轮所有命中候选，多仓满足条件全部平仓（不再只取第一个）
            if candidate_list:
                for hit_item in candidate_list:
                    row = hit_item["row"]
                    close_ctrl = row["close_ctrl"]
                    variety = hit_item["variety"]
                    ts_code = hit_item.get("ts_code") or ""
                    direction = hit_item["direction"]
                    pnl = hit_item["pnl"]
                    close_reason = hit_item["close_reason"]
                    lots = hit_item["lots"]
                    strategy_id = hit_item["strategy_id"]
                    trade_period = hit_item["trade_period"]

                    key = (ts_code or variety, direction)
                    if key in pending_close:
                        print_context(f"【多仓】{variety} {direction} 已触发平仓，等待界面刷新，跳过本轮")
                        continue

                    # UI操作加锁：对齐单仓，最大化+前置窗口+聚焦
                    with shared_data.ctrl_rlock:
                        trade_win = getattr(shared_data, "trade_window", None)
                        if trade_win is not None:
                            try:
                                trade_win.maximize()
                                trade_win.set_focus()
                                sleep(0.5)
                            except Exception as focus_err:
                                print_context(f"多仓监控窗口前置/聚焦异常：{str(focus_err)}")
                        try:
                            close_ctrl.set_focus()
                        except Exception:
                            pass
                        close_ctrl.click_input()
                    # 标记该持仓进入待刷新保护，防止下一轮重复点击
                    pending_close.add(key)
                    print_context(f"多仓监控触发平仓：{close_reason}")

                    # 手续费、统计、推送
                    fut_info = get_future_info(ts_code or variety, 0)
                    per_lot_two_way_fee = fut_info.get('fee', 0) * 2 if fut_info else 0
                    total_fee = per_lot_two_way_fee * lots
                    net_profit = pnl - total_fee
                    ut = getattr(shared_data, "user_type", 0)
                    append_close_record(user_type=ut, pnl=pnl, ts_code=ts_code or variety, strategy_id=strategy_id,
                                        trade_period=trade_period)
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
                    send_msg(f"【多仓监控】自动平仓成功 - 品种：{variety or ts_code}\n{full_msg}")
                    # 多个品种连续点击，增加间隔，给同花顺界面响应时间，避免连续点击失效
                    sleep(0.6)

            sleep(1)
        except Exception as top_err:
            err_msg = f"【多仓监控顶层异常】{str(top_err)}"
            print_context(err_msg)
            send_msg(err_msg)
            sleep(1)
            continue


def close_single_position(window=None) -> bool:
    """
    单仓平仓函数（仅 1 条持仓的场景）：
    - 调用 match_close_and_profit 扫描持仓行；
    - 仅当持仓记录恰好 1 条时，按 shared_data.pre_profit / pre_loss 判断止盈止损；
    - 命中则点击该行“全平”控件平仓，随后计算手续费、写入平仓记录、汇总统计并推送消息；
    - 多条持仓（多仓 / 锁仓 / 多持仓）交由 monitor_multi_position_profit_loss 处理，本函数不平。

    :param window: 可选交易主窗口，为空取 shared_data.trade_window
    :return: True=已触发平仓；False=无持仓 / 非单条 / 未命中 / 平仓失败
    """
    print(f"\r交易品种与窗口正在显示的品种代码不符，程序不能正确读取正在交易品种的盈亏，正在调用特殊方法监控交易状态！",
          flush=True, end="")
    ths_win_data = match_close_and_profit(window)
    if not ths_win_data:
        return False

    # 仅处理单条持仓；多条交多仓监控
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

    # 手数：优先完整合约代码，其次合约前缀，再次品种名，最后默认 1 手
    lots = shared_data.tscode_lots_dict.get(ts_code)
    if lots is None and ts_code:
        lots = shared_data.tscode_lots_dict.get(ts_code[:-4])
    if lots is None:
        lots = shared_data.tscode_lots_dict.get(variety, 1)
    lots = lots or 1

    strategy_id = shared_data.trade_menu_dict.get("rule_id", "unknow")
    trade_period = shared_data.trade_menu_dict.get("trade_period", "")
    total_pre_profit = pre_profit * lots
    total_pre_loss = pre_loss * lots

    # 巡检日志：未命中时可直接从日志看出当前盈亏与阈值差距，避免误判为“没读到持仓”
    print(
        f"\r[close_single_position] 单仓巡检：品种={variety} 代码={ts_code} 方向={direction} "
        f"手数={lots} 当前浮动盈亏={pnl:.2f} | 止盈阈值={total_pre_profit:.2f} 止损阈值={total_pre_loss:.2f}"
    , flush=True, end="")

    close_reason = ""
    hit = False
    # 止盈触发
    if pre_profit > 0 and pnl >= total_pre_profit - 0.02:
        close_reason = (f"【单仓-{direction}】止盈平仓，单手目标{pre_profit:.2f}，"
                        f"{lots}手合计目标{total_pre_profit:.2f}\n当前浮动盈利：{pnl:.2f}元")
        hit = True
    # 止损触发
    elif pre_loss < 0 and pnl <= total_pre_loss + 0.02:
        close_reason = (f"【单仓-{direction}】止损平仓，单手目标{pre_loss:.2f}，"
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

        # 手续费、净利（手续费按合约代码查，品种名仅用于展示）
        fut_info = get_future_info(ts_code or variety, 0) if (ts_code or variety) else None
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
        send_msg(f"【单仓监控】自动平仓成功 - 品种：{variety or ts_code}\n{full_msg}")

        # 重置 YAML 临时参数（对齐普通监控平仓动作）
        reset_temp_params_in_yaml()
        return True

    except Exception as e:
        err_msg = f"【单仓平仓异常】{str(e)}"
        print_context(err_msg)
        send_msg(err_msg)
        return False


if __name__ == "__main__":
    local_control()
    res = match_close_and_profit()
    print("匹配结果：", res)
