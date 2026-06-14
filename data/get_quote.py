import random
import requests
import json
import os
from datetime import datetime, timedelta
from time import sleep
from public.jiaoyisuo import futures_info
from public.agent import get_headers
from public import shared_data, print_context

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
    # print(now)
    return 2 < now < 9

def get_open_price(ts_code=None, url="https://push2.eastmoney.com/api/qt/ulist.np/get"):
    target_code = shared_data.ts_code.strip() if ts_code is None else ts_code
    no_print = True
    while True:
        cur_time = datetime.now().strftime("%H:%M:%S")
        if is_in_restrict_time():
            if no_print:
                print_context.print_context(f"\r未到开市时间，暂不能获取期货品种的开盘信息，请等待！  当前时间：{cur_time}", end="", flush=True)
                no_print = False
            sleep(1)
            continue
        else:
            # print_context.print_context(f"开始获取期货品种[{target_code}]的今日开盘信息")
            break
    # ==================== 配置区 ====================
    EXCHANGE_CODE = {
        "上期所": 113,
        "大商所": 114,
        "郑商所": 115,
        "能源中心": 142,
        "中金所": 220
    }

    # 日期配置 → 只保留今日
    now = datetime.now()
    today_str = now.strftime("%Y%m%d")
    two_days_ago_str = (now - timedelta(days=2)).strftime("%Y%m%d")

    cache_folder = os.path.join(os.getcwd(), "futures_data")
    os.makedirs(cache_folder, exist_ok=True)

    # ==================== 第一步：清理2天前的缓存 ====================
    # print("\r正在清理2天前的缓存文件...", flush=True, end="")
    for filename in os.listdir(cache_folder):
        file_path = os.path.join(cache_folder, filename)
        if os.path.isfile(file_path) and filename.endswith("_openprice.json"):
            try:
                file_date = filename.split("_")[-2]
                if file_date < two_days_ago_str:
                    os.remove(file_path)
            except:
                continue

    # ==================== 第二步：只加载【今日】的缓存 ====================
    result_data = {}
    found_local_file = False

    for filename in os.listdir(cache_folder):
        if filename.startswith(f"{target_code}_") and filename.endswith("_openprice.json"):
            try:
                file_date = filename.split("_")[-2]

                # 只认今天
                if file_date != today_str:
                    continue

                file_path = os.path.join(cache_folder, filename)
                with open(file_path, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                result_data[target_code] = data
                found_local_file = True
                print_context.print_context(f"✅ 从本地成功加载数据文件：{file_path}")
                break
            except:
                continue

    if found_local_file:
        shared_data.open_price = result_data
        return result_data

    # ==================== 第三步：无今日缓存 → 网络获取 ====================
    # print_context.print_context(f"🚀 本地无今日缓存，开始网络获取：{target_code}")

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
            "tscode": target_code,
            "exchange": exchange,
            "open": item.get("f17", 0.0),
            "pre_settle": item.get("f28", 0.0),
            "pre_close": item.get("f18", 0.0),
            "change": item.get("f4", 0.0),
            "percent": item.get("f3", 0.0)
        }
        result_data[target_code] = data_item
        # 如未获取开盘价的处理方式
        open_price = data_item.get("open", 0.0)
        if open_price == 0.0 or open_price is None:
            # 未获取到有效开盘价 → 弹出对话框
            choice = message_box(
                f"未获取到 {target_code} 的有效开盘价！\n\n确定 = 手动输入\n取消 = 退出程序",
                title="开盘价获取失败",
                buttons=MB_OKCANCEL,
                icon=MB_ICONEXCLAMATION
            )
            if choice == IDOK:
                # ✅ 点【确定】：跳去执行 except 里的手动输入
                print("⚠️ 用户选择手动输入开盘价")
                raise Exception("开盘价为0，进入手动输入模式")
            else:
                # ❌ 点【取消】：直接退出
                print("⚠️ 用户选择取消，程序终止")
                exit()

        # ==================== 只保存今日文件，无任何多余 ====================
        today_file = os.path.join(cache_folder, f"{target_code}_{today_str}_openprice.json")
        with open(today_file, "w", encoding="utf-8") as fp:
            json.dump(data_item, fp, ensure_ascii=False, indent=4)

        print(f"✅ 已从网络[{url}]成功获取并保存 <{target_code}> 期货品种的今日开盘价等相关数据>>>\n{data_item}")

    except Exception as e:
        print(f"❌ {target_code}今日开盘信息： 获取失败：\n{str(e)}\n网络来源——{url}\n{'>>'*20} 请手动输入开盘价 {'<<'*20}")
        import tkinter as tk
        from tkinter import simpledialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)  # 窗口总是置顶
        open_price_input = simpledialog.askfloat(f"{url}", f"期货品种: {target_code}")
        if open_price_input is None:
            print("用户取消输入，程序退出！")
            root.destroy()
            exit()
        pre_settle_input = simpledialog.askfloat(f"{url}", f"请手动查询{target_code}品种的昨日结算价 >>>")
        if pre_settle_input is None:
            print("用户取消输入，程序退出！")
            root.destroy()
            exit()
        pre_close_input = simpledialog.askfloat(f"{url}", f"请手动查询{target_code}品种的前日收盘价 >>>")
        if pre_close_input is None:
            print("用户取消输入，程序退出！")
            root.destroy()
            exit()

        result_data[target_code] = {
            "tscode": target_code,
            "open": float(open_price_input),
            "pre_settle": float(pre_settle_input),
            "pre_close": float(pre_close_input),
            "change": 0.0,
            "percent": 0.0
        }
        today_file = os.path.join(cache_folder, f"{target_code}_{today_str}_openprice.json")
        with open(today_file, "w", encoding="utf-8") as fp:
            json.dump(result_data[ts_code], fp, ensure_ascii=False, indent=4)
        # print(f"✅ 已使用手动输入开盘价：{float(open_price_input)}")

    shared_data.open_price = result_data
    return result_data


if __name__ == '__main__':
    print(get_open_price(ts_code="c2609"))
    # print(is_in_restrict_time())