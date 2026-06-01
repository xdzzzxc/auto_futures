import re
from datetime import datetime
import chardet
import requests
from lxml import etree

from public import shared_data
from public.agent import get_headers
from public.jiaoyisuo import futures_info

# ===================== 期货品种英文代码 =====================
ts_code_en = [
    'c', 'cs', 'm', 'jd', 'eg', 'eb', 'pg', 'pk', 'b', 'a', 'sm',
    'fg', 'sa', 'rm', 'ma', 'ta', 'pf', 'ur', 'cy', 'sf',
    'rb', 'hc', 'wr', 'ss', 'al', 'pb', 'zn', 'nr'
]

def get_main_contract(tscode) -> str | None:
    now = datetime.now()
    year = str(now.year)[-2:]
    if now.month < 5:
        return tscode + year + "05"
    if now.month < 9:
        return tscode + year + "09"
    year = str(now.year + 1)[-2:]
    return tscode + year + "10"

search_future_list = [get_main_contract(tscode) for tscode in ts_code_en]
futures_info_dict = {}

# ===================== 品种中英文映射 =====================
FUTURES_MAP = {
    "c": "玉米", "cs": "玉米淀粉", "m": "豆粕", "jd": "鸡蛋",
    "eg": "乙二醇", "eb": "苯乙烯", "pg": "液化石油气", "pk": "花生",
    "b": "豆二", "a": "豆一", "sm": "锰硅", "fg": "玻璃",
    "sa": "纯碱", "rm": "菜粕", "ma": "甲醇", "ta": "PTA",
    "pf": "短纤", "ur": "尿素", "cy": "棉纱", "sf": "硅铁",
    "rb": "螺纹钢", "hc": "热轧卷板", "wr": "线材", "ss": "不锈钢",
    "al": "铝", "pb": "铅", "zn": "锌", "nr": "20号胶"
}

# ===================== 涨跌关键词 =====================
TREND_KEYWORD = {
    "Rise": ["上行", "上涨", "反弹", "走高", "拉升", "偏强", "震荡偏强", "走强", "低库存", "利多", "提振", "利好", "大涨", "冲高", "领涨", "强势", "供不应求"],
    "Fall": ["下跌", "回落", "走低", "偏弱", "走弱", "库存高", "利空", "压力", "大跌", "跳水", "拖累", "抛压", "供过于求", "需求差", "下滑", "领跌", "弱势"],
    "Sideways": ["震荡", "波动", "整理", "盘整", "横盘", "窄幅", "观望", "区间运行", "持稳", "平稳"],
    "Cautious": ["谨慎", "观望", "待定"],
    "Ease": ["缓和", "平稳"]
}

def analyze_title(title, cn_name):
    if cn_name not in title:
        return None
    for trend, keys in TREND_KEYWORD.items():
        for k in keys:
            if k in title:
                return [trend, title]
    return None

# ===================== 工具：中文名查代码 =====================
def get_code_by_cn_name(cn_name):
    for code, info in futures_info.items():
        if info.get("name") == cn_name:
            return code
    return None

# ===================== 转换合约+合并资讯，区分前后排序 =====================
def merge_contract_info(raw_dict):
    main_dict = {}
    other_dict = {}

    for key, value in raw_dict.items():
        trend, text = value
        final_key = key

        # 转换other键为真实合约
        if key.startswith("other_"):
            match = re.search(r"-\s*([^\s]+?)期货", text)
            if match:
                cn_name = match.group(1).strip()
                code = get_code_by_cn_name(cn_name)
                if code:
                    real_contract = get_main_contract(code)
                    if real_contract:
                        final_key = real_contract

        # 判定归类：原有主力合约靠前，剩余other后置
        if not final_key.startswith("other_"):
            if final_key in main_dict:
                old_trend, old_text = main_dict[final_key]
                main_dict[final_key] = [old_trend, f"{old_text}；{text}"]
            else:
                main_dict[final_key] = value
        else:
            if final_key in other_dict:
                old_trend, old_text = other_dict[final_key]
                other_dict[final_key] = [old_trend, f"{old_text}；{text}"]
            else:
                other_dict[final_key] = value

    # 拼接结果：主力合约在前，未知other在后
    merge_res = {}
    merge_res.update(main_dict)
    merge_res.update(other_dict)
    return merge_res

# ===================== 主爬取函数 =====================
def query_future_info(url="https://futures.cngold.org/qsyw/"):
    global futures_info_dict
    futures_info_dict.clear()
    all_news = []

    try:
        resp = requests.get(url, headers=get_headers(), timeout=10)
        encoding = chardet.detect(resp.content)["encoding"]
        text = resp.content.decode(encoding, errors="ignore")
        tree = etree.HTML(text)
        li_list = tree.xpath("//ul/li")

        for li in li_list:
            date = li.xpath('./span[@class="fr date"]/text()')
            cate = li.xpath('./a[1]/@title')
            title = li.xpath('./a[2]/@title')

            if not date or not cate or not title:
                continue

            dt = date[0].strip()
            ct = cate[0].strip()
            tt = title[0].strip()

            if any(k in ct for k in ["期货", "外盘速递", "内盘播报"]):
                full_content = f"{dt} - {ct} - {tt}"
                all_news.append((dt, ct, tt, full_content))

    except:
        return {}

    # 匹配预设主力合约
    matched = {}
    for contract in search_future_list:
        try:
            code = re.findall(r'[a-zA-Z]+', contract)[0].lower()
        except:
            continue
        if code not in FUTURES_MAP:
            continue
        cn_name = FUTURES_MAP[code]

        for dt, ct, tt, full in all_news:
            res = analyze_title(tt, cn_name)
            if res:
                matched[contract] = [res[0], full]
                break

    # 存入剩余未匹配资讯
    temp_dict = matched.copy()
    idx = 1
    for dt, ct, tt, full in all_news:
        used = any(full in v[1] for v in matched.values())
        if not used:
            temp_dict[f"other_{idx:02d}"] = ["Sideways", full]
            idx += 1

    # 转换合约并排序
    futures_info_dict = merge_contract_info(temp_dict)
    shared_data.future_quote_dict = futures_info_dict
    return futures_info_dict

# ===================== 测试运行 =====================
if __name__ == "__main__":
    res = query_future_info()
    print("\n========== 查询结果 ==========")
    print("futures_info_dict =", res)