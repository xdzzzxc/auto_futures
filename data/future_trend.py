import re
import time
from datetime import datetime
import chardet
import requests
from lxml import etree
from typing import Dict, Optional, List, Tuple
import akshare as ak
from public.agent import get_headers
from playwright.sync_api import sync_playwright, TimeoutError

from public.print_context import print_context

# --------------------------主力合约缓存--------------------------
_main_contract_cache: Dict[str, str] = {}
_CACHE_EXPIRE_SEC = 60 * 15  # 15分钟缓存，不要高频请求接口

# ========== 预编译正则，性能优化 ==========
RE_FUTURE_CN = re.compile(r"-\s*([^\s，。；]+?)期货")
RE_CODE_EXTRACT = re.compile(r'[a-zA-Z]+')
futures_type = {0: "", 1: "宏观金融", 2: "农林产品", 3: "能源化工", 4: "资产配置", 5: "黑色成材", 6: "绿色金融",
                7: "贵金属有色", 8: "策略研究", 9: "金融工程", 10: "战略"}
# ==========期货白名单【只获取下面这些品种资讯】===========
TARGET_WHITE_LIST = ["m", "c", "ma", "rb", "jd", "sa", "ta"]

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
CN_TO_CODE = {v: k for k, v in FUTURES_MAP.items()}

# ===================== 涨跌关键词（去重，每个关键词唯一归属） =====================
TREND_KEYWORD = {
    "Rise": ["上行", "上涨", "反弹", "走高", "拉升", "偏强", "震荡偏强", "走强", "低库存", "利多", "提振", "利好", "大涨", "冲高", "领涨", "强势", "供不应求"],
    "Fall": ["下跌", "回落", "走低", "偏弱", "走弱", "库存高", "利空", "压力", "大跌", "跳水", "拖累", "抛压", "供过于求", "需求差", "下滑", "领跌", "弱势", "现货转弱"],
    "Sideways": ["震荡", "波动", "整理", "盘整", "横盘", "窄幅", "区间运行", "持稳", "平稳"],
    "Cautious": ["谨慎", "待定"],
    "Ease": ["缓和"]
}
# 否定词：出现这些词时反转情感判断
NEG_WORDS = {"未", "没有", "并未", "难", "难以", "不会", "不大可能"}

def _fallback_main_contract(tscode) -> Optional[str]:
    """原有的月份推演，仅作为降级兜底，不要直接调用"""
    now = datetime.now()
    year = str(now.year)[-2:]
    if now.month < 5:
        return tscode + year + "05"
    if now.month < 9:
        return tscode + year + "09"
    year = str(now.year + 1)[-2:]
    return tscode + year + "10"

def get_main_contract(tscode) -> str | None:
    """
    获取真实主力合约
    :param tscode: 品种短代码 如 ma rb c m jd
    :return: 完整合约字符串 ma2609 / rb2610；失败返回None
    """
    tscode = tscode.lower().strip()
    now_ts = time.time()

    cache_item = _main_contract_cache.get(tscode)
    if cache_item is not None:
        cache_val, expire_at = cache_item
        if now_ts < expire_at:
            return cache_val

    try:
        df = ak.futures_zh_realtime(symbol=tscode)
        main_df = df[df["主力合约标志"] == "主力"]
        if main_df.empty:
            raise ValueError("接口返回无主力合约标记")
        contract_code = main_df.iloc[0]["合约代码"]
        _main_contract_cache[tscode] = (contract_code, now_ts + _CACHE_EXPIRE_SEC)
        return contract_code
    except Exception:
        return _fallback_main_contract(tscode)

# 只生成白名单对应的主力合约
white_contract_list = [get_main_contract(code) for code in TARGET_WHITE_LIST]

# ===================== 工具：中文名查代码 =====================
def get_code_by_cn_name(cn_name: str) -> Optional[str]:
    return CN_TO_CODE.get(cn_name, None)


def analyze_text(title: str, cn_name: str, content: str = "") -> Optional[Tuple[str, int]]:
    """
    文本情感打分，支持标题+正文；处理否定词
    返回 (trend_type, score) 或者None
    """
    full_text = f"{title} {content}"
    if cn_name not in full_text:
        return None

    neg_flag = any(w in full_text for w in NEG_WORDS)
    trend_score: Dict[str, int] = {k: 0 for k in TREND_KEYWORD.keys()}

    for trend, keys in TREND_KEYWORD.items():
        for kw in keys:
            if kw in full_text:
                trend_score[trend] += 1

    total = sum(trend_score.values())
    if total == 0:
        return None

    best_trend = max(trend_score.items(), key=lambda x: x[1])
    trend_name, score = best_trend

    if neg_flag:
        if trend_name == "Rise":
            trend_name = "Fall"
        elif trend_name == "Fall":
            trend_name = "Rise"
    return trend_name, score


# ===================== 过滤字典，只保留白名单品种对应的合约key =====================
def filter_by_white_list(src_dict: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """仅保留TARGET_WHITE_LIST内品种的合约，过滤其他所有key"""
    keep_contracts = set()
    for code in TARGET_WHITE_LIST:
        c = get_main_contract(code)
        if c:
            keep_contracts.add(c)
    out = {k: v for k, v in src_dict.items() if k in keep_contracts}
    return out


# ===================== 主爬取函数 =====================
def query_future_info(url="https://futures.cngold.org/qsyw/", headers: dict = None):
    """
    :param url: 资讯页面
    :param headers: 请求头，如果传入None，简单默认UA，你可以继续用get_headers()
    :return: dict 结果，只包含白名单品种
    """
    all_news = []
    req_headers = get_headers()
    try:
        resp = requests.get(url, headers=req_headers, timeout=12)
        ctype = resp.headers.get("content-type", "")
        if "charset=" in ctype.lower():
            enc = ctype.split("charset=")[-1].strip()
        else:
            det = chardet.detect(resp.content)
            enc = det.get("encoding", "utf-8") or "utf-8"
        text = resp.content.decode(enc, errors="ignore")
        tree = etree.HTML(text)
        li_list = tree.xpath("//ul/li")

        for li in li_list:
            date = li.xpath('./span[@class="fr date"]/text()')
            cate = li.xpath('./a[1]/@title')
            title = li.xpath('./a[2]/@title')
            if not (date and cate and title):
                continue
            dt = date[0].strip()
            ct = cate[0].strip()
            tt = title[0].strip()
            if any(k in ct for k in ["期货", "外盘速递", "内盘播报"]):
                full_content = f"{dt} - {ct} - {tt}"
                all_news.append((dt, ct, tt, full_content))
        time.sleep(1.1)

    except requests.exceptions.RequestException as e:
        print(f"网络请求异常 {e}")
        return {}
    except Exception as e:
        print(f"解析页面异常 {e}")
        return {}

    matched = {}
    # 只循环白名单合约，不再处理全部ts_code_en
    for contract in white_contract_list:
        code_match = RE_CODE_EXTRACT.findall(contract)
        if not code_match:
            continue
        code = code_match[0].lower()
        if code not in FUTURES_MAP:
            continue
        cn_name = FUTURES_MAP[code]

        for dt, ct, tt, full in all_news:
            res = analyze_text(tt, cn_name)
            if res:
                trend, _score = res
                matched[contract] = [trend, full]
                break

    # 不再生成other_xx多余资讯，直接返回matched
    return matched


def get_data_from_ja(fut_type=0):
    url = f"https://www.gtjaqh.com/pc/report?page=1&catType={futures_type[fut_type]}"
    text_node_name = "ListReport_list_item_text__q3vke"
    date_node_name = "ListReport_list_item_date__E9q2p"

    result = {}
    start_time = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, timeout=20000)
            # 等待目标列表元素出现，最多8秒，等待JS渲染完成
            page.wait_for_selector(f'span[class*="{text_node_name}"]', timeout=8000)
            html = page.content()  # 拿到渲染完成后的完整HTML
        except TimeoutError:
            # 超时没等到列表，直接返回空字典
            html = ""
        finally:
            browser.close()

    if not html:
        # 页面拿失败，也要补全白名单占位
        for prefix in TARGET_WHITE_LIST:
            c = get_main_contract(prefix)
            if c:
                result[c] = ["NoInfo", f"暂无国泰君安资讯 - {c}"]
        end_time = time.time()
        print_context(f"获取国泰君安期货资讯耗时：{end_time - start_time:.2f}秒。")
        return result

    tree = etree.HTML(html)
    text_nodes = tree.xpath(f'//span[contains(@class,"{text_node_name}")]')
    date_nodes = tree.xpath(f'//span[contains(@class,"{date_node_name}")]')

    # 1.先zip捆绑：(资讯文本,发布时间)
    raw_bundle = []
    for t_node, d_node in zip(text_nodes, date_nodes):
        txt = t_node.xpath("string(.)").strip()
        pub_dt = d_node.xpath("string(.)").strip()
        if txt:
            raw_bundle.append((txt, pub_dt))

    # 获取今日日期，格式对齐国泰君安页面 2026/08/24
    today_str = datetime.now().strftime("%Y/%m/%d")
    valid_bundle = []
    for txt, pub_dt in raw_bundle:
        # 过滤非今日旧资讯，防止资讯时间错位
        if pub_dt.strip() != today_str:
            continue
        valid_bundle.append((txt, pub_dt))

    # 解析有效资讯
    for content_text, pub_time in valid_bundle:
        for code in TARGET_WHITE_LIST:
            cn_name = FUTURES_MAP.get(code)
            if not cn_name:
                continue
            if cn_name in content_text:
                contract = get_main_contract(code)
                if not contract:
                    continue
                ana_ret = analyze_text(title=content_text, cn_name=cn_name, content="")
                if ana_ret is not None:
                    trend, _score = ana_ret
                else:
                    # 无法识别关键词才标记Sideways
                    trend = "sideways"
                out_text = f"国泰君安简讯 - {pub_time} - {content_text}"
                result[contract] = [trend, out_text]

    # =========关键：对白名单全部品种补齐占位，缺失的填充NoInfo，保证7个全部存在=========
    for prefix in TARGET_WHITE_LIST:
        contract = get_main_contract(prefix)
        if contract and contract not in result:
            result[contract] = ["NoInfo", f"暂无国泰君安资讯 - {contract}({FUTURES_MAP[prefix]})"]

    end_time = time.time()
    print_context(f"获取国泰君安期货资讯耗时：{end_time - start_time:.2f}秒。")
    return result


def merge_two_info_dict() -> Dict[str, List[str]]:
    """
    合并两个资讯字典，不覆盖；同key时text用；拼接
    dict_a：金投网资讯（优先保留它的trend）
    dict_b：国泰君安资讯
    """
    dict_a = query_future_info()
    dict_b = get_data_from_ja()
    merged = dict(dict_a)
    for k, (trend_b, text_b) in dict_b.items():
        if k in merged:
            trend_a, text_a = merged[k]
            merged[k] = [trend_a, f"{text_a}；{text_b}"]
        else:
            merged[k] = [trend_b, text_b]
    return merged


# ===================== 测试运行 =====================
if __name__ == "__main__":
    ja_data = merge_two_info_dict()
    print(ja_data)
    exit()
    res_cngold = query_future_info()
    res_gtja = get_data_from_ja()
    print(f"res_gtja: {res_gtja}")
    final_result = merge_two_info_dict()
    # 最后再过滤一遍，确保只有白名单7个品种
    final_result = filter_by_white_list(final_result)

    print("\n==========合并后最终资讯结果（仅白名单品种）==========")
    for k, v in final_result.items():
        print(f"{k:12s} | {v[0]:10s} | {v[1]}")
