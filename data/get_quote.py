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


def get_open_price(ts_code=None, url="https://push2.eastmoney.com/api/qt/ulist.np/get"):
    # ==========【批量分支】ts_code=None 代表读取 shared_data.quote_list 批量获取全部品种 ==========
    if ts_code is None:
        current_ts = shared_data.ts_code.strip()
        quote_list = shared_data.quote_list
        if current_ts and current_ts not in quote_list:
            quote_list.add(current_ts)
            print_context.print_context(f"[INFO] 当前交易品种[{current_ts}]不在quote_list，自动添加进列表")

        quote_list = list(quote_list)
        total_result = {}

        print_context.print_context("[INFO] 开始休市时段检测，02:00~09:00将阻塞等待开盘...")
        while True:
            cur_time = datetime.now().strftime("%H:%M:%S")
            if is_in_restrict_time():
                print(f"\r[WARN - get_open_price] [{cur_time}] - [日市开盘： 上午9:00  夜市开盘： 21:00]，休市等待中...", end="", flush=True)
                sleep(1)
            else:
                print("\n[INFO] 退出休市等待，时间满足，可以开始拉取数据")
                break

        print_context.print_context("[INFO] 开始清理过期缓存文件")
        one_days_ago_str = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        cache_folder = get_data_cache_dir()
        cache_folder = os.path.join(cache_folder, "open_price")
        os.makedirs(cache_folder, exist_ok=True)
        del_count = 0
        for filename in os.listdir(cache_folder):
            file_path = os.path.join(cache_folder, filename)
            if os.path.isfile(file_path) and filename.endswith("_openprice.json"):
                try:
                    file_date = filename.split("_")[-2]
                    if file_date < one_days_ago_str:
                        os.remove(file_path)
                        del_count += 1
                except Exception as e:
                    print_context.print_context(f"[WARN] 删除缓存失败 {filename}, err:{str(e)}")
        print_context.print_context(f"[INFO] 缓存清理完成，本次清理过期文件数量：{del_count}")

        for idx, code in enumerate(quote_list):
            try:
                sub_res = get_open_price(ts_code=code, url=url)
                if sub_res:
                    total_result.update(sub_res)
                    print_context.print_context(f"[INFO] 品种【{code}】处理完成，已合并结果")
            except Exception as e:
                print_context.print_context(f"[ERROR] 品种【{code}】处理异常: {str(e)}")
            sleep(random.uniform(1.2, 2.5))

        shared_data.open_price = total_result
        return total_result

    # ===================== 下面全部是【单品种】逻辑 =====================
    print_context.print_context(f"[INFO] ---- 进入单品种模式，目标品种：{ts_code} ----")
    target_code = ts_code.lower()

    EXCHANGE_CODE = {
        "上期所": 113,
        "大商所": 114,
        "郑商所": 115,
        "能源中心": 142,
        "中金所": 220
    }

    is_night_session, sys_today_str, real_trade_day_str = get_trade_day_str()
    cache_folder = get_data_cache_dir()
    cache_folder = os.path.join(cache_folder, "open_price")
    os.makedirs(cache_folder, exist_ok=True)

    now_hour = datetime.now().hour
    force_network = False
    trade_cache_file = os.path.join(cache_folder, f"{target_code}_{real_trade_day_str}_openprice.json")
    if 21 <= now_hour <= 23:
        if os.path.exists(trade_cache_file):
            print_context.print_context(f"[INFO] 🌙21‑23点：检测到已存在交易日缓存 {trade_cache_file}，跳过删除与网络请求")
        else:
            day_cache_file = os.path.join(cache_folder, f"{target_code}_{sys_today_str}_openprice.json")
            if os.path.exists(day_cache_file):
                try:
                    os.remove(day_cache_file)
                    print_context.print_context(f"[INFO] 🌙21‑23点时段：删除白天开盘缓存 {day_cache_file}")
                except Exception as e:
                    print_context.print_context(f"[WARN] 删除白天缓存失败 {day_cache_file}, err:{str(e)}")
            force_network = True
            print_context.print_context(f"[INFO] 🌙21‑23点：force_network 置为True，需要网络拉取数据")

    result_data = {}
    found_local_file = False

    if not force_network:
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
                        break
                    except Exception as e:
                        print_context.print_context(f"[WARN] 读取缓存文件异常 {filename}, err:{str(e)}")
                        continue
            if found_local_file:
                break
    else:
        print_context.print_context(f"[INFO] force_network=True，跳过缓存读取，直接走网络请求")

    if found_local_file:
        print_context.print_context(f"[INFO] 缓存命中成功")
        if is_night_session:
            if not os.path.exists(trade_cache_file):
                print_context.print_context(f"[INFO] 夜盘：需要复制缓存生成交易日缓存文件")
                data_item = result_data[target_code]
                with open(trade_cache_file, "w", encoding="utf-8") as fp:
                    json.dump(data_item, fp, ensure_ascii=False, indent=4)
        shared_data.open_price = result_data
        print_context.print_context(f"[INFO] 【{target_code}】缓存读取完毕，返回结果")
        return result_data

    print_context.print_context(f"[INFO] 缓存未命中，准备发起网络请求拉取【{target_code}】")
    try:
        code_lower = target_code.lower()
        prefix = code_lower[:-4]
        exchange = futures_info[prefix]["exchange"]
        print_context.print_context(f"[INFO] 品种解析：prefix={prefix}, exchange={exchange}")

        req_code = code_lower[:-4].upper() + code_lower[-3:] if exchange == "郑商所" else code_lower
        print_context.print_context(f"[INFO] 组装secid请求代码: {req_code}")

        # ========== 增加网络重试，专门处理 RemoteDisconnected 断连 ==========
        retry_times = 3
        resp = None
        for r in range(retry_times):
            try:
                sleep_sec = random.uniform(2, 4)
                print_context.print_context(f"[INFO] 网络请求前置休眠 {sleep_sec:.2f}s 防风控，第{r+1}/{retry_times}次尝试")
                sleep(sleep_sec)
                resp = requests.get(
                    url=url,
                    params={
                        "fltt": 2, "invt": 2,
                        "secids": f"{EXCHANGE_CODE[exchange]}.{req_code}",
                        "fields": "f12,f28,f17,f18,f3,f4"
                    },
                    headers=get_headers() | {"Accept": "*/*", "Connection": "keep-alive"},
                    timeout=12
                )
                break
            except (RemoteDisconnected, requests.exceptions.ConnectionError) as e:
                print_context.print_context(f"[WARN] 【{target_code}】连接被远端关闭，重试 {r+1}/{retry_times}, err:{str(e)}")
                sleep(random.uniform(1.5,3.0))
                continue
        if resp is None:
            raise Exception("多次请求均被远端断开，获取失败")

        print_context.print_context(f"[INFO] http请求返回状态码: {resp.status_code}")
        item = resp.json()["data"]["diff"][0]

        data_item = {
            "日期": datetime.now().strftime("%Y%m%d %H:%M:%S"),
            "ts_code": target_code,
            "交易所": exchange,
            "今日开盘价": item.get("f17", 0.0),
            "昨日结算价": item.get("f28", 0.0),
            "昨日收盘价": item.get("f18", 0.0),
        }
        result_data[target_code] = data_item
        open_price = data_item.get("今日开盘价", 0.0)
        print_context.print_context(f"[INFO] 解析行情：open={open_price}, settle={data_item['昨日结算价']}, close={data_item['昨日收盘价']}")
        if open_price == 0.0 or open_price is None:
            print_context.print_context(f"[WARN] 【{target_code}】今日开盘价为0，弹出确认弹窗")
            choice = message_box(
                f"未获取到 {target_code} 的有效开盘价！\n\n按[确定]键手动输入，按[取消]键将退出程序！",
                title="❌警告          ",
                buttons=MB_OKCANCEL,
                icon=MB_ICONEXCLAMATION
            )
            if choice == IDOK:
                raise Exception("开盘价为0，进入手动输入模式")
            else:
                print_context.print_context(f"[ERROR] 用户选择取消，程序终止")
                exit()

        sys_file = os.path.join(cache_folder, f"{target_code}_{sys_today_str}_openprice.json")
        with open(sys_file, "w", encoding="utf-8") as fp:
            json.dump(data_item, fp, ensure_ascii=False, indent=4)
        print_context.print_context(f"[INFO] 写入系统日期缓存文件：{sys_file}")

        if is_night_session:
            with open(trade_cache_file, "w", encoding="utf-8") as fp:
                json.dump(data_item, fp, ensure_ascii=False, indent=4)
            print_context.print_context(f"[INFO] 🌙夜盘模式，额外写入交易日缓存：{trade_cache_file}")

        print(f"✅ 已从网络[{url}]成功获取并保存 <{target_code}> 期货品种的今日开盘价等相关数据>>>\n{data_item}")

    except Exception as e:
        print_context.print_context(f"[ERROR] 【{target_code}】网络拉取异常: {str(e)}")
        print(f"❌ {target_code}今日开盘信息： 获取失败：\n{str(e)}\n网络来源——{url}\n{'>>'*20} 请手动输入开盘价 {'<<'*20}")

        # ========= 【重点改动：删掉tk，改用控制台input，message_box做提示】 =========
        choice = message_box(
            f"【{target_code}】行情拉取失败！\n需要你在控制台输入开盘、结算、收盘价格。\n确认后看控制台输入，取消则退出程序",
            title="行情获取失败",
            buttons=MB_OKCANCEL,
            icon=MB_ICONEXCLAMATION
        )
        if choice != IDOK:
            print_context.print_context(f"[INFO] 用户取消手动输入，退出程序")
            exit()

        # 控制台循环输入，校验浮点数
        def input_float(prompt):
            while True:
                s = input(prompt).strip()
                try:
                    return float(s)
                except ValueError:
                    print("输入非法，请输入数字！")

        open_price_input = input_float(f"请输入[{target_code}]开盘价: ")
        pre_settle_input = input_float(f"请输入[{target_code}]前日结算价 >>>")
        pre_close_input = input_float(f"请输入[{target_code}]前日收盘价 >>>")

        data_item = {
            "日期": datetime.now().strftime("%Y%m%d %H:%M:%S"),
            "ts_code": target_code,
            "今日开盘价": float(open_price_input),
            "昨日结算价": float(pre_settle_input),
            "昨日收盘价": float(pre_close_input),
        }
        result_data[target_code] = data_item
        print_context.print_context(f"[INFO] 手动输入完成，数据已录入")

        sys_file = os.path.join(cache_folder, f"{target_code}_{sys_today_str}_openprice.json")
        with open(sys_file, "w", encoding="utf-8") as fp:
            json.dump(data_item, fp, ensure_ascii=False, indent=4)
        print_context.print_context(f"[INFO] 写入系统日期缓存文件：{sys_file}")

        if is_night_session:
            with open(trade_cache_file, "w", encoding="utf-8") as fp:
                json.dump(data_item, fp, ensure_ascii=False, indent=4)
            print_context.print_context(f"[INFO] 🌙夜盘模式，手动输入，额外写入交易日缓存：{trade_cache_file}")

    shared_data.open_price = result_data
    print_context.print_context(f"[INFO] 【{target_code}】单品种处理流程全部结束，返回结果")
    return result_data


if __name__ == '__main__':
    # print(get_open_price(ts_code="fg2611"))
    print(get_open_price())
