# -*- coding: utf-8 -*-
"""
开盘价获取模块（get_quote.py 整合版）

整合说明（合并原 get_quote.py 与 reget_open_price.py）：
1. 对外核心函数名保持不变：``get_open_price(ts_code=None)``，其他模块原有调用不受影响；
2. 本模块不启动常驻线程，``get_open_price`` 为单次执行，由外部主循环 / 巡检周期调用；
3. 取价优先级：当日本地缓存 → 历史最新缓存兜底 → 网络拉取 → 人工手动录入兜底；
4. 冷启动兜底：进程内首次取某品种、本地又无任何缓存时，不受时段窗口限制必须拉一次网络，
   保证开机后下游模块能拿到开盘价继续运行；网络失败再退历史缓存，仍无数据则转人工录入；
5. 到点强制刷新：日盘 08:59、夜盘 20:59 进入对应窗口后，当日首次调用强制重取一次，
   覆盖当日缓存；同一窗口当日只刷一次，标记按日期 + 会话记录，跨天自动失效；
6. 网络拉取 / 手动录入成功后顺手清理过期缓存：每个合约只保留日期最新的一份，更早日期
   （含周末 / 节假日休市遗留、两天前及以上）的文件自动删除。

缓存目录：``get_data_cache_dir()/open_price/``
缓存文件：``{合约小写}_{YYYYMMDD}_openprice.json``  例：``m2701_20261118_openprice.json``
"""

import os
import re
import json
import random
from datetime import datetime
from time import sleep

import requests
from http.client import RemoteDisconnected

from public.jiaoyisuo import futures_info, get_future_info
from public.agent import get_headers
from public import shared_data
from public.print_context import print_context
from public.shared_data import get_data_cache_dir


# 交易所 -> 东方财富 secids 市场代码
EXCHANGE_CODE = {
    "上期所": 113,
    "大商所": 114,
    "郑商所": 115,
    "能源中心": 142,
    "中金所": 220,
}

QUOTE_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"

# 拉取窗口（一天内的秒数）
DAY_WINDOW_START = 8 * 3600 + 59 * 60      # 08:59
DAY_WINDOW_END = 15 * 3600                 # 15:00
NIGHT_WINDOW_START = 20 * 3600 + 59 * 60   # 20:59
NIGHT_WINDOW_END = 2 * 3600                # 02:00

# 缓存文件名：{合约小写}_{YYYYMMDD}_openprice.json
CACHE_FILE_RE = re.compile(r"^([a-z]+\d{3,4})_(\d{8})_openprice\.json$")

# 本进程内已成功取过开盘价的品种集合（重启后自动清空，用于冷启动判断）
_BOOTSTRAP_DONE = set()


# ----------------------------------------------------------------------------
# 时段 / 缓存工具
# ----------------------------------------------------------------------------
def _current_session(now: datetime = None) -> str:
    """
    返回当前会话标识：
    - ``day``   日盘 08:59~15:00
    - ``night`` 夜盘 20:59~次日02:00
    - ``closed`` 其余时段
    """
    now = now or datetime.now()
    total_sec = now.hour * 3600 + now.minute * 60 + now.second
    if total_sec >= NIGHT_WINDOW_START or total_sec < NIGHT_WINDOW_END:
        return "night"
    if DAY_WINDOW_START <= total_sec < DAY_WINDOW_END:
        return "day"
    return "closed"


def _cache_folder() -> str:
    folder = os.path.join(get_data_cache_dir(), "open_price")
    os.makedirs(folder, exist_ok=True)
    return folder


def _cache_path(target_code: str, date_str: str) -> str:
    return os.path.join(_cache_folder(), f"{target_code}_{date_str}_openprice.json")


def _find_latest_cache(target_code: str):
    """
    查找指定合约日期最新的一份缓存文件（兜底用）。
    当日文件不存在时，凌晨夜盘 / 刚开机等场景可读上一交易日缓存容灾。
    :return: 缓存文件绝对路径；未找到返回 None
    """
    folder = _cache_folder()
    latest_name = None
    latest_date = ""
    try:
        names = os.listdir(folder)
    except Exception as e:
        print_context(f"[WARN] 扫描缓存目录失败: {e}")
        return None

    for name in names:
        m = CACHE_FILE_RE.match(name)
        if not m:
            continue
        code, date_str = m.group(1), m.group(2)
        if code != target_code:
            continue
        if date_str > latest_date:
            latest_date, latest_name = date_str, name

    return os.path.join(folder, latest_name) if latest_name else None


def _cleanup_old_cache_files() -> None:
    """
    清理过期开盘价缓存：按合约分组，每组只保留日期最新的一份，
    删除更早日期的残留文件（覆盖两天前、周末 / 节假日休市遗留）。
    非本模块命名规则的文件不动。
    """
    folder = _cache_folder()
    try:
        names = os.listdir(folder)
    except Exception as e:
        print_context(f"[WARN] 扫描缓存目录失败，跳过旧缓存清理: {e}")
        return

    groups = {}
    for name in names:
        m = CACHE_FILE_RE.match(name)
        if not m:
            continue
        code, date_str = m.group(1), m.group(2)
        groups.setdefault(code, []).append((date_str, name))

    removed = 0
    for code, items in groups.items():
        if len(items) <= 1:
            continue
        # 日期降序，保留第 1 份（最新），其余删除
        items.sort(key=lambda x: x[0], reverse=True)
        for _, old_name in items[1:]:
            try:
                os.remove(os.path.join(folder, old_name))
                removed += 1
            except Exception as e:
                print_context(f"[WARN] 删除旧缓存失败 {old_name}: {e}")

    if removed:
        print_context(f"[INFO] 已清理 {removed} 个过期开盘价缓存文件")


def _get_variables_lock():
    return getattr(shared_data, "variables_rlock", None)


def _update_shared_open_price(target_code: str, data_item: dict) -> None:
    """加锁增量写入 shared_data.open_price，避免整体覆盖造成并发脏读。"""
    lock = _get_variables_lock()
    if lock is not None:
        with lock:
            if not isinstance(getattr(shared_data, "open_price", None), dict):
                shared_data.open_price = {}
            shared_data.open_price[target_code] = data_item
    else:
        if not isinstance(getattr(shared_data, "open_price", None), dict):
            shared_data.open_price = {}
        shared_data.open_price[target_code] = data_item


def _resolve_current_ts(ts_code=None) -> str:
    if ts_code:
        current_ts = ts_code
    else:
        current_ts = (shared_data.ts_code or "").strip() or getattr(
            shared_data, "default_tscode", ""
        )
    return current_ts.strip().lower()


def _get_trigger_map() -> dict:
    """当日到点刷新标记容器（key 带日期 + 会话，跨天自动失效）。"""
    if not hasattr(shared_data, "open_price_trigger_done") or shared_data.open_price_trigger_done is None:
        shared_data.open_price_trigger_done = {}
    return shared_data.open_price_trigger_done


def _has_night_session(target_code: str) -> bool:
    """查询品种是否有夜盘；查询失败按无夜盘处理。"""
    try:
        info = get_future_info(symbol=target_code) or {}
        return bool(info.get("night_trading", False))
    except Exception as e:
        print_context(f"[{target_code}] 获取夜盘信息失败，判定为无夜盘, err:{str(e)}")
        return False


# ----------------------------------------------------------------------------
# 网络拉取
# ----------------------------------------------------------------------------
def _fetch_remote_open_price(target_code: str) -> dict:
    """请求东方财富行情接口，返回单品种开盘价数据；失败抛异常。"""
    prefix = target_code[:-4]
    try:
        exchange = futures_info[prefix]["exchange"]
    except Exception as e:
        raise Exception(f"品种 {target_code} 未配置交易所信息: {e}")

    # 郑商所合约代码需转大写前缀 + 三位合约；其余交易所保持原代码
    if exchange == "郑商所":
        req_code = target_code[:-4].upper() + target_code[-3:]
    else:
        req_code = target_code

    resp = None
    last_err = None
    for r in range(3):
        try:
            sleep(random.uniform(0.5, 1.5))
            sess = requests.Session()
            resp = sess.get(
                url=QUOTE_URL,
                params={
                    "fltt": 2,
                    "invt": 2,
                    "secids": f"{EXCHANGE_CODE[exchange]}.{req_code}",
                    "fields": "f12,f28,f17,f18,f3,f4",
                },
                headers=get_headers() | {"Accept": "*/*", "Connection": "close"},
                timeout=12,
            )
            sess.close()
            break
        except (
            RemoteDisconnected,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ) as e:
            last_err = e
            print(f"\r[WARN] 获取开盘价错误[{r + 1}/3]:{str(e)}", flush=True, end="")
            sleep(random.uniform(1.5, 3.0))

    if resp is None:
        raise Exception(f"三次网络请求全部失败: {last_err}")

    ret_json = resp.json()
    diff_list = (ret_json.get("data") or {}).get("diff") or []
    if not diff_list:
        raise Exception("行情接口返回 diff 为空，无合约数据")
    item = diff_list[0]

    data_item = {
        "ts_code": target_code,
        "交易所": exchange,
        "今日开盘价": item.get("f17", 0.0),
        "昨日结算价": item.get("f28", 0.0),
        "昨日收盘价": item.get("f18", 0.0),
    }

    if float(data_item["今日开盘价"]) <= 0:
        raise Exception("返回开盘价为 0，数据无效")

    return data_item


def _load_cache_to_shared(cache_file: str, target_code: str, tag: str) -> bool:
    """读取指定缓存文件并回填 shared_data；成功返回 True。"""
    try:
        with open(cache_file, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        _update_shared_open_price(target_code, data)
        _BOOTSTRAP_DONE.add(target_code)
        print_context(
            f"[{datetime.now().strftime('%H:%M:%S')}] ✅ {tag} >>> "
            f"{os.path.basename(cache_file)}"
        )
        return True
    except Exception as e:
        print_context(f"[WARN] 缓存读取损坏 {cache_file}, err:{str(e)}")
        return False


def _parse_price_text(text, field: str, required: bool) -> float:
    """
    解析价格输入文本。
    - required=True：不能为空且必须 >0；
    - required=False：留空返回 0.0；
    解析失败抛 ValueError。
    """
    if text is None:
        return 0.0
    t = str(text).strip().replace(",", "")
    if t == "":
        if required:
            raise ValueError(f"{field}不能为空")
        return 0.0
    val = float(t)
    if required and val <= 0:
        raise ValueError(f"{field}必须大于0")
    return val


# ----------------------------------------------------------------------------
# 人工手动录入兜底（网络失败且无本地缓存时使用）
# ----------------------------------------------------------------------------
def manual_input_open_price(ts_code=None, open_price=None, pre_settle=None, pre_close=None):
    """
    网络拉取失败且无本地缓存时的人工兜底录入。

    仅需录入：今日开盘价、昨日结算价、昨日收盘价；其余字段（交易所、会话、日期、
    来源标记）自动补默认值。录入成功后写入当日缓存并回填 shared_data.open_price。

    :param ts_code: 合约代码；为空取 shared_data 当前品种
    :param open_price: 今日开盘价（外部预填，可跳过控制台交互）；必填且 >0
    :param pre_settle: 昨日结算价；可留空 / 传 None，默认 0.0
    :param pre_close: 昨日收盘价；可留空 / 传 None，默认 0.0
    :return: 成功返回 data_item 字典；用户放弃 / 录入失败返回 None
    """
    target_code = _resolve_current_ts(ts_code)
    if not target_code:
        print_context("[WARN] 手动录入：品种为空，无法录入")
        return None

    now = datetime.now()
    session = _current_session(now)

    # 交易所自动取配置，取不到默认“未知”
    prefix = target_code[:-4]
    try:
        exchange = futures_info[prefix]["exchange"]
    except Exception:
        exchange = "未知"

    def _read_input(prompt: str):
        """控制台读取一行；EOF / 中断视为放弃，返回 None。"""
        try:
            return input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return None

    # 1. 开盘价（必填，>0）
    if open_price is None:
        print_context(
            f"[手动录入] 网络与本地缓存均不可用，请手动录入品种 {target_code} 行情（输入 q 放弃）"
        )
        raw_open = _read_input(f"请输入 {target_code} 今日开盘价：")
        if raw_open is None or raw_open.lower() in ("q", "quit", "exit"):
            print_context("[手动录入] 用户放弃录入")
            return None
        open_price = raw_open

    try:
        open_price_val = _parse_price_text(open_price, "今日开盘价", required=True)
    except Exception as e:
        print_context(f"[ERROR] 开盘价录入无效: {e}")
        return None

    # 2. 昨结 / 昨收（可留空默认 0.0）
    def _ask_optional(label: str, value):
        if value is not None:
            return _parse_price_text(value, label, required=False)
        raw = _read_input(f"请输入 {target_code} {label}（可留空默认 0）：")
        if raw is None or raw.lower() in ("q", "quit", "exit"):
            return None
        return _parse_price_text(raw, label, required=False)

    try:
        pre_settle_val = _ask_optional("昨日结算价", pre_settle)
        if pre_settle_val is None:
            print_context("[手动录入] 用户放弃录入")
            return None
        pre_close_val = _ask_optional("昨日收盘价", pre_close)
        if pre_close_val is None:
            print_context("[手动录入] 用户放弃录入")
            return None
    except Exception as e:
        print_context(f"[ERROR] 昨结 / 昨收录入无效: {e}")
        return None

    data_item = {
        "ts_code": target_code,
        "交易所": exchange,
        "今日开盘价": open_price_val,
        "昨日结算价": pre_settle_val,
        "昨日收盘价": pre_close_val,
        "会话": session,
        "日期": now.strftime("%Y%m%d %H:%M:%S"),
        "来源": "手动录入",
    }

    today_str = now.strftime("%Y%m%d")
    today_file = _cache_path(target_code, today_str)
    try:
        with open(today_file, "w", encoding="utf-8") as fp:
            json.dump(data_item, fp, ensure_ascii=False, indent=4)
    except Exception as e:
        print_context(f"[ERROR] 手动录入缓存写入失败 {today_file}: {e}")
        return None

    _update_shared_open_price(target_code, data_item)
    _BOOTSTRAP_DONE.add(target_code)
    trigger_map = _get_trigger_map()
    trigger_map[f"{target_code}_{today_str}_{session}"] = True
    _cleanup_old_cache_files()
    print_context(f"✅ 手动录入完成，已保存：{os.path.basename(today_file)}")
    return data_item


# ----------------------------------------------------------------------------
# 对外核心函数（函数名保持不变）
# ----------------------------------------------------------------------------
def get_open_price(ts_code=None, force_refresh: bool = False):
    """
    获取当前品种开盘价（单次执行，不开线程）。

    取价 / 刷新规则：
    1. 读取当前品种（传入 ts_code 优先，否则取 shared_data.ts_code / default_tscode）；
    2. 非强制刷新时，优先读当日缓存，当日缺失再兜底读该合约历史最新缓存；
    3. 到点强制刷新：日盘 08:59 后、夜盘 20:59 后（仅夜盘品种）当日首次调用，
       绕过缓存重取网络，覆盖当日文件；
    4. 冷启动兜底：本进程首次取该品种、本地无任何缓存时，即便处于禁止拉取时段
       也必须拉一次网络；网络失败退历史缓存，仍无数据则转人工手动录入兜底；
    5. 其余窗口外场景且本地已有缓存：不请求网络，直接用缓存；
    6. 拿到有效数据后顺手清理各合约更早日期的过期缓存。

    :param ts_code: 指定合约代码；为空取 shared_data 当前品种
    :param force_refresh: True 时绕过本地缓存直接拉网络（外部主动重取用）
    :return: 成功返回 shared_data.open_price 字典；无任何可用数据返回 None
    """
    target_code = _resolve_current_ts(ts_code)
    if not target_code:
        print_context("[WARN] shared_data 品种为空，跳过本轮开盘价获取")
        return None

    now = datetime.now()
    session = _current_session(now)
    today_str = now.strftime("%Y%m%d")
    today_file = _cache_path(target_code, today_str)
    in_window = session in ("day", "night")

    trigger_map = _get_trigger_map()
    mark_key = f"{target_code}_{today_str}_{session}"
    cold_start = target_code not in _BOOTSTRAP_DONE

    # 判断到点强制刷新：窗口内、本会话当日首次触发；夜盘窗口仅对有夜盘品种强制刷新
    need_force = False
    if in_window and not trigger_map.get(mark_key):
        if session == "night" and not _has_night_session(target_code):
            need_force = False
        else:
            need_force = True

    # 1. 非强制刷新：先读本地缓存（当日优先，历史兜底）
    if not need_force and not force_refresh:
        cache_file = today_file if os.path.exists(today_file) else _find_latest_cache(target_code)
        if cache_file:
            tag = "本地缓存获取开盘信息"
            if os.path.basename(cache_file) != os.path.basename(today_file):
                tag = "历史缓存兜底获取开盘信息"
            if _load_cache_to_shared(cache_file, target_code, tag):
                _cleanup_old_cache_files()
                return shared_data.open_price

    # 2. 判断是否允许网络拉取：
    #    - 外部 force_refresh；
    #    - 窗口内到点强制刷新；
    #    - 冷启动（本进程首次取该品种）：不受窗口限制先拉一次当日价，拉失败再退历史缓存；
    #    - 其余窗口外场景不拉网络。
    allow_network = force_refresh or need_force or cold_start

    if not allow_network:
        if session == "closed":
            print_context("[INFO] 非拉取时段且本地已有缓存，跳过网络请求")
        return None

    # 3. 网络拉取
    try:
        data_item = _fetch_remote_open_price(target_code)
    except Exception as err:
        print_context(f"[ERROR] 开盘价网络拉取失败，尝试历史缓存兜底: {err}")
        fallback = _find_latest_cache(target_code)
        if fallback and _load_cache_to_shared(fallback, target_code, "网络失败，历史缓存兜底"):
            _cleanup_old_cache_files()
            return shared_data.open_price
        # 历史缓存也没有：转人工手动录入兜底，保证下游有开盘价可继续运行
        manual = manual_input_open_price(ts_code=target_code)
        if manual:
            return shared_data.open_price
        return None

    data_item["会话"] = session
    data_item["日期"] = now.strftime("%Y%m%d %H:%M:%S")

    with open(today_file, "w", encoding="utf-8") as fp:
        json.dump(data_item, fp, ensure_ascii=False, indent=4)

    _update_shared_open_price(target_code, data_item)
    _BOOTSTRAP_DONE.add(target_code)
    trigger_map[mark_key] = True
    print_context(f"✅ 开盘价拉取成功，已保存：{os.path.basename(today_file)}")

    # 拉取成功后清理过期缓存（同一合约仅保留最新日期一份）
    _cleanup_old_cache_files()
    return shared_data.open_price


# ----------------------------------------------------------------------------
# 夜盘重取入口（非阻塞，兼容旧调用；内部走 get_open_price 统一逻辑）
# ----------------------------------------------------------------------------
def refresh_night_open_price(ts_code=None):
    """
    夜盘开盘价重取入口（不开线程、内部不 sleep 轮询）。

    保留该函数仅为兼容外部旧调用；到点强制刷新逻辑已并入 ``get_open_price``，
    外部主循环周期调用 ``get_open_price()`` 即可自动完成 20:59 夜盘重取。

    :param ts_code: 指定合约代码；为空取 shared_data 当前品种
    :return: True=本轮已就绪 / 已重取；False=未触发
    """
    if getattr(shared_data, "stop_flag", False):
        return False

    target_code = _resolve_current_ts(ts_code)
    if not target_code:
        return False

    now = datetime.now()
    if _current_session(now) != "night":
        return False

    if not _has_night_session(target_code):
        return False

    data = get_open_price(ts_code=target_code, force_refresh=True)
    return data is not None


if __name__ == "__main__":
    # 独立调试入口：直接拉当前品种开盘价
    shared_data.open_price_trigger_done = {}
    shared_data.stop_flag = False
    print(get_open_price(ts_code="jd2701"))
