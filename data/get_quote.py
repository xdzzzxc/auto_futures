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

# 调用系统 MessageBox 弹窗（无第三方库，纯系统自带）
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
    return 2 < now < 9


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


def get_open_price(ts_code=None, url="https://push2.eastmoney.com/api/qt/ulist.np/get"):
    target_code = (shared_data.ts_code.strip() if ts_code is None else ts_code).lower()

    while True:
        cur_time = datetime.now().strftime("%H:%M:%S")
        if is_in_restrict_time():
            print(f"\r[ {cur_time} ] - [日市开盘： 上午9:00  夜市开盘： 21:00]，休市中······", end="", flush=True)
            sleep(1)
            continue
        else:
            print("")
            # print_context.print_context(f"开始获取期货品种[{target_code}]的今日开盘信息")
            break

    EXCHANGE_CODE = {
        "上期所": 113,
        "大商所": 114,
        "郑商所": 115,
        "能源中心": 142,
        "中金所": 220
    }

    is_night_session, sys_today_str, real_trade_day_str = get_trade_day_str()
    two_days_ago_str = (datetime.now() - timedelta(days=2)).strftime("%Y%m%d")

    cache_folder = get_data_cache_dir()
    cache_folder = os.path.join(cache_folder, "open_price")
    os.makedirs(cache_folder, exist_ok=True)

    # ====================【修复】21‑23点：仅当明日交易日缓存不存在，才删除白天缓存并强制网络 ====================
    now_hour = datetime.now().hour
    force_network = False
    trade_cache_file = os.path.join(cache_folder, f"{target_code}_{real_trade_day_str}_openprice.json")
    if 21 <= now_hour <= 23:
        if os.path.exists(trade_cache_file):
            # 已经存在明日交易日缓存，不删除，不强制网络，复用本地
            print_context.print_context(f"🌙21‑23点：检测到已存在交易日缓存 {trade_cache_file}，跳过删除与网络请求")
        else:
            # 明日缓存不存在，删除今日白天缓存，强制网络拉取
            day_cache_file = os.path.join(cache_folder, f"{target_code}_{sys_today_str}_openprice.json")
            if os.path.exists(day_cache_file):
                try:
                    os.remove(day_cache_file)
                    print_context.print_context(f"🌙21‑23点时段：删除白天开盘缓存 {day_cache_file}")
                except Exception as e:
                    print_context.print_context(f"⚠️ 删除白天缓存失败 {day_cache_file}, err:{str(e)}")
            force_network = True

    # ==================== 第一步：清理2天前的缓存 ====================
    for filename in os.listdir(cache_folder):
        file_path = os.path.join(cache_folder, filename)
        if os.path.isfile(file_path) and filename.endswith("_openprice.json"):
            try:
                file_date = filename.split("_")[-2]
                if file_date < two_days_ago_str:
                    os.remove(file_path)
            except Exception:
                continue

    result_data = {}
    found_local_file = False

    # force_network=False 才走本地缓存读取
    if not force_network:
        # ==================== 第二步：加载缓存：夜盘优先读取真实交易日，日盘读取系统今日 ====================
        check_dates = [real_trade_day_str, sys_today_str]
        for check_date in check_dates:
            for filename in os.listdir(cache_folder):
                if filename.startswith(f"{target_code}_") and filename.endswith("_openprice.json"):
                    try:
                        file_date = filename.split("_")[-2]
                        if file_date != check_date:
                            continue
                        file_path = os.path.join(cache_folder, filename)
                        with open(file_path, "r", encoding="utf-8") as fp:
                            data = json.load(fp)
                        result_data[target_code] = data
                        found_local_file = True
                        print_context.print_context(f"✅ 程序成功加载本地数据文件：{file_path}")
                        break
                    except Exception:
                        continue
            if found_local_file:
                break

    if found_local_file:
        # 读取缓存命中，如果是夜盘，复制一份生成real_trade_day_str命名文件（不存在才写）
        if is_night_session:
            if not os.path.exists(trade_cache_file):
                data_item = result_data[target_code]
                with open(trade_cache_file, "w", encoding="utf-8") as fp:
                    json.dump(data_item, fp, ensure_ascii=False, indent=4)
                print_context.print_context(f"🌙夜盘模式(读取缓存复制)：生成交易日缓存 {trade_cache_file}")

        shared_data.open_price = result_data
        return result_data

    # ==================== 第三步：无缓存 / force_network强制网络获取 ====================
    try:
        code_lower = target_code.lower()
        prefix = code_lower[:-4]
        exchange = futures_info[prefix]["exchange"]

        # 郑商所代码处理
        req_code = code_lower[:-4].upper() + code_lower[-3:] if exchange == "郑商所" else code_lower

        sleep(random.uniform(2, 4))
        res = requests.get(
            url=url,
            params={
                "fltt": 2, "invt": 2,
                "secids": f"{EXCHANGE_CODE[exchange]}.{req_code}",
                "fields": "f12,f28,f17,f18,f3,f4"
            },
            headers=get_headers() | {"Accept": "*/*", "Connection": "keep-alive"},
            timeout=12
        )
        item = res.json()["data"]["diff"][0]

        data_item = {
            "日期": datetime.now().strftime("%Y%m%d %H:%M:%S"),
            "ts_code": target_code,
            "交易所": exchange,
            "今日开盘价": item.get("f17", 0.0),
            "昨日结算价": item.get("f28", 0.0),
            "昨日收盘价": item.get("f18", 0.0),
            # "change": item.get("f4", 0.0),
            # "percent": item.get("f3", 0.0)
        }
        result_data[target_code] = data_item
        open_price = data_item.get("今日开盘价", 0.0)
        if open_price == 0.0 or open_price is None:
            choice = message_box(
                f"未获取到 {target_code} 的有效开盘价！\n\n按[确定]键手动输入，按[取消]键将退出程序！",
                title="❌警告          ",
                buttons=MB_OKCANCEL,
                icon=MB_ICONEXCLAMATION
            )
            if choice == IDOK:
                raise Exception("开盘价为0，进入手动输入模式")
            else:
                print("⚠️ 用户选择取消，程序终止")
                exit()

        # ========== 保存文件：永远保存系统日期；夜盘额外保存一份真实交易日（明天日期） ==========
        sys_file = os.path.join(cache_folder, f"{target_code}_{sys_today_str}_openprice.json")
        with open(sys_file, "w", encoding="utf-8") as fp:
            json.dump(data_item, fp, ensure_ascii=False, indent=4)

        if is_night_session:
            with open(trade_cache_file, "w", encoding="utf-8") as fp:
                json.dump(data_item, fp, ensure_ascii=False, indent=4)
            print_context.print_context(f"🌙夜盘模式，网络获取，额外生成交易日缓存：{trade_cache_file}")

        print(f"✅ 已从网络[{url}]成功获取并保存 <{target_code}> 期货品种的今日开盘价等相关数据>>>\n{data_item}")

    except Exception as e:
        print(f"❌ {target_code}今日开盘信息： 获取失败：\n{str(e)}\n网络来源——{url}\n{'>>'*20} 请手动输入开盘价 {'<<'*20}")
        import tkinter as tk
        from tkinter import simpledialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        open_price_input = simpledialog.askfloat(f"{url}", f"请输入[{target_code}]开盘价: ")
        if open_price_input is None:
            print("用户取消输入，程序退出！")
            root.destroy()
            exit()
        pre_settle_input = simpledialog.askfloat(f"{url}", f"请输入[{target_code}]前日结算价 >>>")
        if pre_settle_input is None:
            print("用户取消输入，程序退出！")
            root.destroy()
            exit()
        pre_close_input = simpledialog.askfloat(f"{url}", f"请输入[{target_code}]前日收盘价 >>>")
        if pre_close_input is None:
            print("用户取消输入，程序退出！")
            root.destroy()
            exit()

        data_item = {
            "日期": datetime.now().strftime("%Y%m%d %H:%M:%S"),
            "ts_code": target_code,
            "今日开盘价": float(open_price_input),
            "昨日结算价": float(pre_settle_input),
            "昨日收盘价": float(pre_close_input),
            # "change": 0.0,
            # "percent": 0.0
        }
        result_data[target_code] = data_item

        # 手动输入分支同样处理双文件保存
        sys_file = os.path.join(cache_folder, f"{target_code}_{sys_today_str}_openprice.json")
        with open(sys_file, "w", encoding="utf-8") as fp:
            json.dump(data_item, fp, ensure_ascii=False, indent=4)

        if is_night_session:
            with open(trade_cache_file, "w", encoding="utf-8") as fp:
                json.dump(data_item, fp, ensure_ascii=False, indent=4)
            print_context.print_context(f"🌙夜盘模式，手动输入，额外生成交易日缓存：{trade_cache_file}")

    shared_data.open_price = result_data
    return result_data


if __name__ == '__main__':
    print(get_open_price(ts_code="fg2611"))