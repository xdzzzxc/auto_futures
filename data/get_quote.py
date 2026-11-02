import random
import requests
import json
import os
from datetime import datetime, timedelta
from time import sleep
from public.jiaoyisuo import futures_info
from public.agent import get_headers
from public import shared_data, print_context
from public.shared_data import get_data_cache_dir
import ctypes
from ctypes import wintypes
from http.client import RemoteDisconnected   # ✅ 修正导入位置
from tools.play_warn_sound import (play_warn_sound, play_warn_sound_win, play_warn_sound_tts)
from tools.play_alert import sound_warn
# 调用系统 MessageBox 弹窗（无第三方库，纯系统自带，任意线程安全）
def message_box(text, title="提示", buttons=0, icon=64):
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.MessageBoxW.argtypes = (wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT)
    return user32.MessageBoxW(None, text, title, buttons | icon)

MB_OKCANCEL = 1
MB_ICONEXCLAMATION = 48
IDOK = 1
IDCANCEL = 2


def is_in_restrict_time() -> bool:
    """判断当前时间是否在 02:00 - 09:00 之间"""
    now = datetime.now().hour
    return 1 < now < 9


def get_trade_day_str() -> tuple[bool, str, str]:
    """
    判断当前是否夜盘跨日；返回 (is_night_session, sys_date_str, trade_date_str)
    is_night_session: True=当前是夜盘，行情归属下一个交易日
    sys_date_str: 本机系统当前 YYYYMMDD
    trade_date_str: 该段行情真实归属交易日 YYYYMMDD
    规则：21:00 ~ 23:59:59 属于次日交易日；00:00~02:00也属于前一晚的次日交易日
    """
    now = datetime.now()
    sys_date_str = now.strftime("%Y%m%d")
    hour = now.hour
    # 21点之后：夜盘，交易日=明天
    if 21 <= hour <= 23:
        trade_dt = now + timedelta(days=1)
        return True, sys_date_str, trade_dt.strftime("%Y%m%d")
    # 0点~2点：还是夜盘，归属前一晚的次日
    elif 0 <= hour < 2:
        trade_dt = now + timedelta(days=1)
        return True, sys_date_str, trade_dt.strftime("%Y%m%d")
    else:
        # 日盘，交易日=本机今天
        return False, sys_date_str, sys_date_str


def get_network_fetch_window() -> tuple[bool, bool, str]:
    now = datetime.now()
    total_sec = now.hour * 3600 + now.minute * 60 + now.second
    DAY_WINDOW_START = 8 * 3600 + 59 * 60
    DAY_WINDOW_END = 15 * 3600
    NIGHT_WINDOW_START = 20 * 3600 + 58 * 60
    NIGHT_WINDOW_END = 2 * 3600

    if total_sec >= NIGHT_WINDOW_START or total_sec < NIGHT_WINDOW_END:
        return True, True, "夜盘拉取窗口 >=20:58，拉取后同时保存当日+下一交易日缓存"
    elif DAY_WINDOW_START <= total_sec < DAY_WINDOW_END:
        return True, False, "日盘拉取窗口 08:59~15:00"
    else:
        return False, False, "禁止拉取时段 15:00~20:58 / 02:00~08:59"

def get_next_trade_day(base_date_str: str) -> str:
    """
    你已有 get_trade_day_str，这里假设它返回 %Y%m%d 格式交易日；
    此函数仅示意：输入交易日，返回下一个交易日字符串；
    【重要】你要替换成你系统里真正获取下一交易日的函数，不能简单+1天（要跳过周末节假日）
    """
    # 示例占位，务必替换成你自己的交易日历逻辑
    dt = datetime.strptime(base_date_str, "%Y%m%d")
    next_dt = dt + timedelta(days=1)
    return next_dt.strftime("%Y%m%d")

def get_open_price(ts_code = None):
    """
    常驻线程函数，内部while True，轮询间隔30s，永不主动退出
    逻辑：
    1. 每轮读取shared_data当前交易品种
    2. 优先读取缓存（当前交易日缓存存在就直接用，不请求网络）
    3. 窗口允许拉取、缓存不存在时才请求接口
    4. 拉取成功：同时写入【当日交易日】、【下一交易日】两份json
    5. 同品种+同目标交易日成功后标记，避免重复刷接口
    """
    EXCHANGE_CODE = {
        "上期所": 113,
        "大商所": 114,
        "郑商所": 115,
        "能源中心": 142,
        "中金所": 220
    }
    url = "https://push2.eastmoney.com/api/qt/ulist.np/get"
    cache_folder = get_data_cache_dir()
    cache_folder = os.path.join(cache_folder, "open_price")
    os.makedirs(cache_folder, exist_ok=True)

    # 已拉取记录：key = f"{ts}_{td}"，防止同一个品种同一个交易日反复请求
    fetched_map = dict()
    print_once = True
    while True:
        try:
            # 1. 获取当前品种、交易日信息
            if ts_code is None:
                current_ts = shared_data.ts_code.strip() or shared_data.default_tscode
            else:
                current_ts = ts_code
            if not current_ts:
                print_context.print_context("[WARN] shared_data品种为空，跳过本轮")
                sleep(30)
                continue
            target_code = current_ts.lower()

            is_night_session, sys_today_str, real_td_str = get_trade_day_str()
            next_td_str = get_next_trade_day(real_td_str)

            file_td = os.path.join(cache_folder, f"{target_code}_{real_td_str}_openprice.json")
            file_next = os.path.join(cache_folder, f"{target_code}_{next_td_str}_openprice.json")
            map_key = f"{target_code}_{real_td_str}"

            # 2. 优先读当前交易日缓存，命中直接赋值shared_data，跳过网络
            if os.path.exists(file_td):
                try:
                    with open(file_td, "r", encoding="utf-8") as fp:
                        data = json.load(fp)
                    shared_data.open_price = {target_code: data}
                    if print_once:
                        print_context.print_context(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ 命中缓存 {os.path.basename(file_td)}")
                        print_once = False
                    sleep(30)
                    continue
                except Exception as e:
                    print_context.print_context(f"[WARN] 缓存读取损坏 {file_td}, err:{str(e)}")

            # 3. 缓存不存在，判断是否允许网络拉取
            allow_fetch, _, window_msg = get_network_fetch_window()
            if not allow_fetch:
                print_context.print_context(f"[INFO] {window_msg}，无缓存，跳过网络请求")
                sleep(30)
                continue
            if map_key in fetched_map:
                print_context.print_context(f"[INFO] {target_code} 交易日{real_td_str}已经拉取成功，不再重复请求")
                sleep(30)
                continue

            print_context.print_context(f"[INFO] 开始网络拉取 {target_code} | 交易日:{real_td_str} | {window_msg}")
            prefix = target_code[:-4]
            exchange = futures_info[prefix]["exchange"]
            req_code = target_code[:-4].upper() + target_code[-3:] if exchange == "郑商所" else target_code

            resp = None
            for r in range(3):
                try:
                    s = random.uniform(2, 4)
                    sleep(s)
                    sess = requests.Session()
                    resp = sess.get(
                        url=url,
                        params={
                            "fltt": 2,
                            "invt": 2,
                            "secids": f"{EXCHANGE_CODE[exchange]}.{req_code}",
                            "fields": "f12,f28,f17,f18,f3,f4"
                        },
                        headers=get_headers() | {"Accept": "*/*", "Connection": "close"},
                        timeout=12
                    )
                    sess.close()
                    break
                except (RemoteDisconnected, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                    print_context.print_context(f"[WARN] 拉取重试 {r+1}/3 err:{str(e)}")
                    sleep(random.uniform(1.5, 3.0))
            if resp is None:
                raise Exception("三次网络请求全部失败")

            item = resp.json()["data"]["diff"][0]
            data_item = {
                "日期": datetime.now().strftime("%Y%m%d %H:%M:%S"),
                "ts_code": target_code,
                "交易所": exchange,
                "今日开盘价": item.get("f17", 0.0),
                "昨日结算价": item.get("f28", 0.0),
                "昨日收盘价": item.get("f18", 0.0),
            }
            open_price_val = data_item.get("今日开盘价", 0.0)
            if open_price_val <= 0:
                raise Exception("返回开盘价为0，数据无效")

            # ========= 核心：同时写入【当前交易日】、【下一交易日】两份json =========
            with open(file_td, "w", encoding="utf-8") as fp:
                json.dump(data_item, fp, ensure_ascii=False, indent=4)
            with open(file_next, "w", encoding="utf-8") as fp:
                json.dump(data_item, fp, ensure_ascii=False, indent=4)

            fetched_map[map_key] = True
            shared_data.open_price = {target_code: data_item}
            print_context.print_context(f"✅ 拉取成功，已保存：{os.path.basename(file_td)} 和 {os.path.basename(file_next)}")

        except Exception as err:
            print_context.print_context(f"[ERROR] 本轮异常，丢弃本轮，继续循环: {err}")
            return None
        # 固定放循环尾部，本轮全部逻辑走完之后休眠30秒
        sleep(30)
    return shared_data.open_price


if __name__ == '__main__':
    print(get_open_price())
