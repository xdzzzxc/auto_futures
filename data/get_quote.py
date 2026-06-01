import random
import requests
import json
import os
from datetime import datetime, timedelta
from time import sleep
from public.jiaoyisuo import futures_info
from public.agent import get_headers
from public import shared_data, print_context


def get_open_price():
    # ==================== 配置区 ====================
    EXCHANGE_CODE = {
        "上期所": 113,
        "大商所": 114,
        "郑商所": 115,
        "能源中心": 142,
        "中金所": 220
    }

    # 日期配置
    now = datetime.now()
    today_str = now.strftime("%Y%m%d")
    two_days_ago_str = (now - timedelta(days=2)).strftime("%Y%m%d")
    current_hour = now.hour
    cache_folder = os.path.join(os.getcwd(), "futures_data")
    os.makedirs(cache_folder, exist_ok=True)
    # print_context.print_context(f"cache folder : {cache_folder}")
    # 目标品种（只处理这一个）
    target_code = shared_data.ts_code.strip()
    # print_context.print_context(f"target_code:{target_code}")

    # ==================== 第一步：清理2天前的所有缓存文件 ====================
    print("\r正在清理2天前的缓存文件...", flush=True, end="")
    for filename in os.listdir(cache_folder):
        file_path = os.path.join(cache_folder, filename)
        if os.path.isfile(file_path) and filename.endswith("_openprice.json"):
            try:
                # 提取文件名中的日期 格式：品种_日期_openprice.json
                file_date = filename.split("_")[-2]
                if file_date < two_days_ago_str:
                    os.remove(file_path)
            except:
                continue
    # print("\r缓存清理完成 ✅\n")

    # ==================== 第二步：优先从本地文件夹查找当前品种的所有有效文件 ====================
    result_data = {}
    found_local_file = False

    for filename in os.listdir(cache_folder):
        # 只匹配当前品种 + 正确后缀的文件
        if filename.startswith(f"{target_code}_") and filename.endswith("_openprice.json"):
            # print(filename, flush=True, end="")
            sleep(2)

            try:
                file_path = os.path.join(cache_folder, filename)
                with open(file_path, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                # 组装成 {ts_code: {}} 格式
                result_data[target_code] = data
                found_local_file = True
                print_context.print_context(f"✅ 从本地成功加载数据文件：{filename}")
                break  # 找到一个就停止
            except:
                continue
    # 本地找到 → 直接存入共享变量并返回，绝不走网络
    if found_local_file:
        shared_data.open_price = result_data
        return result_data

    # ==================== 第三步：完全无本地文件 → 才网络获取 ====================
    print_context.print_context(f"🚀 本地无缓存，开始网络获取：{target_code}")
    tomorrow_str = (now + timedelta(days=1)).strftime("%Y%m%d")

    try:
        code_lower = target_code.lower()
        prefix = code_lower[:-4]
        exchange = futures_info[prefix]["exchange"]
        has_night = futures_info[prefix]["night_trading"]

        # 郑商所代码特殊处理
        req_code = code_lower[:-4].upper() + code_lower[-3:] if exchange == "郑商所" else code_lower

        # 网络请求
        sleep(random.uniform(2, 4))
        res = requests.get(
            url="https://push2.eastmoney.com/api/qt/ulist.np/get",
            params={
                "fltt": 2, "invt": 2,
                "secids": f"{EXCHANGE_CODE[exchange]}.{req_code}",
                "fields": "f12,f28,f17,f18,f3,f4"
            },
            headers=get_headers() | {"Accept": "*/*", "Connection": "keep-alive"},
            timeout=12
        )
        item = res.json()["data"]["diff"][0]

        # 组装数据
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

        # ==================== 保存文件 ====================
        today_file = os.path.join(cache_folder, f"{target_code}_{today_str}_openprice.json")
        # 1. 必存：今日文件
        with open(today_file, "w", encoding="utf-8") as fp:
            json.dump(data_item, fp, ensure_ascii=False, indent=4)

        # 2. 夜盘 21:00 ~ 00:00 → 额外保存明天文件
        if has_night and 21 <= current_hour < 24:
            tomorrow_file = os.path.join(cache_folder, f"{target_code}_{tomorrow_str}_openprice.json")
            with open(tomorrow_file, "w", encoding="utf-8") as fp:
                json.dump(data_item, fp, ensure_ascii=False, indent=4)
            print_context.print_context(f"✅ 夜盘时段：已同步保存明日文件 {target_code}_{tomorrow_str}_openprice.json")

        print(f"✅ 成功获取并保存{target_code} 开盘价等数据！")

    except Exception as e:
        print(f"❌ {target_code} 获取失败：{str(e)}")
        result_data = {}

    shared_data.open_price = result_data
    return result_data


if __name__ == '__main__':
    shared_data.ts_code = "m2609"
    print(get_open_price())