# future_news_trend.py
import re
import time
from datetime import datetime
import chardet
import requests
from lxml import etree
from typing import Dict, Optional, List, Tuple
from playwright.sync_api import sync_playwright, TimeoutError, Browser, Page
import threading
from tools.write_yaml import set_temp_param
from public import shared_data
from public.agent import get_headers
from public.print_context import print_context
from public.shared_data import direction_dict, dict_rlock

# ===================== 配置常量 =====================
# 预编译正则
RE_FUTURE_CN = re.compile(r"-\s*([^\s，。；]+?)期货")
RE_CODE_EXTRACT = re.compile(r'[a-zA-Z]+')

futures_type = {0: "", 1: "宏观金融", 2: "农林产品", 3: "能源化工", 4: "资产配置", 5: "黑色成材", 6: "绿色金融",
                7: "贵金属有色", 8: "策略研究", 9: "金融工程", 10: "战略"}

# 期货白名单
TARGET_WHITE_LIST = ["m", "c", "ma", "rb", "jd", "sa", "ta"]

# 品种中英文映射
FUTURES_MAP = {
    "c": "玉米", "cs": "玉米淀粉", "m": "豆粕", "jd": "鸡蛋",
    "eg": "乙二醇", "eb": "苯乙烯", "pg": "液化石油气", "pk": "花生",
    "b": "豆二", "a": "豆一", "sm": "锰硅", "fg": "玻璃",
    "sa": "纯碱", "rm": "菜粕", "ma": "甲醇", "ta": "PTA",
    "pf": "短纤", "ur": "尿素", "cy": "棉纱", "sf": "硅铁",
    "rb": "螺纹钢", "hc": "热轧卷板", "wr": "线材", "ss": "不锈钢",
    "al": "铝", "pb": "铅", "zn": "锌", "nr": "20号胶"
}

# 品种别名扩充
FUTURES_ALIAS = {
    "豆粕": ["豆粕", "连粕"],
    "玉米": ["玉米"],
    "鸡蛋": ["鸡蛋"],
    "甲醇": ["甲醇", "郑醇"],
    "纯碱": ["纯碱"],
    "PTA": ["PTA", "精对苯二甲酸"],
    "螺纹钢": ["螺纹", "螺纹钢"]
}
CN_TO_CODE = {v: k for k, v in FUTURES_MAP.items()}

# ===================== 全局Playwright单例（复用浏览器，避免频繁启动） =====================
class PlaywrightSingleton:
    _instance = None
    _browser: Optional[Browser] = None
    _pw = None

    @classmethod
    def get_browser(cls) -> Browser:
        if cls._instance is None:
            cls._pw = sync_playwright().start()
            cls._browser = cls._pw.chromium.launch(headless=True)
            cls._instance = True
        return cls._browser

    @classmethod
    def close(cls):
        if cls._browser:
            cls._browser.close()
        if cls._pw:
            cls._pw.stop()
        cls._instance = None

# ===================== 观点分类器 =====================
class FutureViewJudge:
    def __init__(self):
        self.bull_words = {
            "偏紧", "紧缺", "去库", "支撑", "上涨", "走强", "利多", "看涨", "反弹", "提振",
            "供不应求", "惜售", "减产", "停检", "库存低位", "回暖", "上行", "偏强", "强势",
            "冲高", "领涨", "低库存", "利好", "拉升", "走高"
        }
        self.bear_words = {
            "宽松", "过剩", "累库", "承压", "下行", "走弱", "利空", "看跌", "回落", "压制",
            "供大于求", "增产", "到港增加", "库存高企", "偏弱", "下行压力", "下跌",
            "走低", "库存高", "压力", "跳水", "拖累", "抛压", "需求差", "下滑", "领跌", "弱势", "现货转弱"
        }
        self.shock_words = {
            "震荡", "区间", "波动", "多空交织", "分歧", "中性", "难有趋势", "方向不明",
            "宽幅震荡", "窄幅波动", "整理", "盘整", "横盘", "窄幅", "区间运行", "持稳", "平稳"
        }
        self.reverse_words = {
            "利空出尽": "bull",
            "利多兑现": "bear",
            "利好落地": "bear"
        }
        self.short_term = {"短期", "日内", "近月", "本周", "短线"}
        self.long_term = {"中长期", "远期", "长线", "后市", "长期"}
        self.neg_words = {"不", "难", "难以", "并未", "没有", "未", "不会", "不大可能"}

    def judge(self, text: str) -> Dict:
        raw_text = text.strip()
        # 反转词优先
        for phrase, tag in self.reverse_words.items():
            if phrase in raw_text:
                direction = "多" if tag == "bull" else "空"
                return {
                    "raw_text": raw_text,
                    "direction": direction,
                    "confidence": 0.90,
                    "term": "未知",
                    "hit_words": [phrase],
                    "note": "反转词命中"
                }
        bull_hits = [w for w in self.bull_words if w in raw_text]
        bear_hits = [w for w in self.bear_words if w in raw_text]
        shock_hits = [w for w in self.shock_words if w in raw_text]

        # 修正：双向判断否定词，不管否定词在前还是在后
        for neg in self.neg_words:
            neg_pos = raw_text.find(neg)
            if neg_pos == -1:
                continue
            for w in bull_hits.copy():
                w_pos = raw_text.find(w)
                if w_pos != -1 and abs(w_pos - neg_pos) < 12:
                    bull_hits.remove(w)
            for w in bear_hits.copy():
                w_pos = raw_text.find(w)
                if w_pos != -1 and abs(w_pos - neg_pos) < 12:
                    bear_hits.remove(w)

        term = "未知"
        if any(w in raw_text for w in self.short_term):
            term = "短期"
        elif any(w in raw_text for w in self.long_term):
            term = "中长期"

        b_cnt = len(bull_hits)
        be_cnt = len(bear_hits)
        s_cnt = len(shock_hits)

        if s_cnt > 0 and b_cnt == 0 and be_cnt == 0:
            return {
                "raw_text": raw_text,
                "direction": "震荡",
                "confidence": 0.80,
                "term": term,
                "hit_words": shock_hits,
                "note": ""
            }
        elif b_cnt > be_cnt and b_cnt > 0:
            return {
                "raw_text": raw_text,
                "direction": "多",
                "confidence": round(min(0.6 + 0.1 * b_cnt, 0.95), 2),
                "term": term,
                "hit_words": bull_hits,
                "note": ""
            }
        elif be_cnt > b_cnt and be_cnt > 0:
            return {
                "raw_text": raw_text,
                "direction": "空",
                "confidence": round(min(0.6 + 0.1 * be_cnt, 0.95), 2),
                "term": term,
                "hit_words": bear_hits,
                "note": ""
            }
        else:
            return {
                "raw_text": raw_text,
                "direction": "无法判断",
                "confidence": 0.0,
                "term": term,
                "hit_words": [],
                "note": "关键词不足或多空同时存在"
            }


judge_ins = FutureViewJudge()
DIR_MAP = {"多": "rise", "空": "fall", "震荡": "sideways", "无法判断": "sideways"}

# ===================== 工具函数 =====================
def get_code_by_cn_name(cn_name: str) -> Optional[str]:
    return CN_TO_CODE.get(cn_name, None)

# ------------------------------ 金投网抓取 ------------------------------
def _query_cngold_single(short_code: str) -> Tuple[Optional[str], str, Dict]:
    url = "https://futures.cngold.org/qsyw/"
    req_headers = get_headers()
    all_news = []
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
        print_context(f"金投网请求异常: {e}")
        return None, "", {}
    except Exception as e:
        print_context(f"金投网解析异常: {e}")
        return None, "", {}

    cn_name = FUTURES_MAP.get(short_code)
    if not cn_name:
        return None, "", {}
    alias_list = FUTURES_ALIAS.get(cn_name, [cn_name])
    for dt, ct, tt, full in all_news:
        for alias in alias_list:
            if alias in full:
                res = judge_ins.judge(full)
                trend = DIR_MAP[res["direction"]]
                return trend, full, res
    return None, "", {}

# ------------------------------ 国泰君安抓取 ------------------------------
def _query_gtja_single(short_code: str, fut_type=0) -> Tuple[Optional[str], str, Dict]:
    url = f"https://www.gtjaqh.com/pc/report?page=1&catType={futures_type[fut_type]}"
    text_node_name = "ListReport_list_item_text__q3vke"
    date_node_name = "ListReport_list_item_date__E9q2p"
    html = ""
    try:
        browser = PlaywrightSingleton.get_browser()
        page: Page = browser.new_page()
        page.goto(url, timeout=20000)
        page.wait_for_selector(f'span[class*="{text_node_name}"]', timeout=8000)
        html = page.content()
        page.close()
    except TimeoutError:
        html = ""
    except Exception as e:
        print_context(f"国泰君安页面异常: {e}")
        html = ""
    if not html:
        return None, "", {}

    tree = etree.HTML(html)
    text_nodes = tree.xpath(f'//span[contains(@class,"{text_node_name}")]')
    date_nodes = tree.xpath(f'//span[contains(@class,"{date_node_name}")]')
    raw_bundle = []
    for t_node, d_node in zip(text_nodes, date_nodes):
        txt = t_node.xpath("string(.)").strip()
        pub_dt = d_node.xpath("string(.)").strip()
        if txt:
            raw_bundle.append((txt, pub_dt))

    # 日期标准化清洗，横杠/斜杠统一
    today_str = datetime.now().strftime("%Y%m%d")
    valid_bundle = []
    for txt, pub_dt in raw_bundle:
        clean_dt = re.sub(r"[-/]", "", pub_dt.strip())
        if clean_dt == today_str:
            valid_bundle.append((txt, pub_dt))

    cn_name = FUTURES_MAP.get(short_code)
    if not cn_name:
        return None, "", {}
    alias_list = FUTURES_ALIAS.get(cn_name, [cn_name])
    for content_text, pub_time in valid_bundle:
        for alias in alias_list:
            if alias in content_text:
                out_text = f"国泰君安简讯 - {pub_time} - {content_text}"
                res = judge_ins.judge(out_text)
                trend = DIR_MAP[res["direction"]]
                return trend, out_text, res
    return None, "", {}

# ===================== 对外主入口：单品种资讯查询 =====================
def fetch_future_trend(ts_code: str) -> Tuple[str, str, Dict]:
    """
    :param ts_code: m2711 / ma2701
    :return: (trend, info_text, judge_dict)
    trend: rise / fall / sideways
    """
    code_match = RE_CODE_EXTRACT.findall(ts_code)
    if not code_match:
        return ("sideways", f"合约{ts_code}无法提取品种短码", {})
    short_code = code_match[0].lower()
    # 白名单校验
    if short_code not in FUTURES_MAP:
        return ("sideways", f"品种短码{short_code}不在品种映射表内", {})
    if short_code not in TARGET_WHITE_LIST:
        return ("sideways", f"品种{short_code}不在资讯白名单，跳过", {})

    trend1, text1, dict1 = _query_cngold_single(short_code)
    trend2, text2, dict2 = _query_gtja_single(short_code)

    if trend1 is not None:
        final_trend = trend1
        final_text = text1
        final_dict = dict1
    elif trend2 is not None:
        final_trend = trend2
        final_text = text2
        final_dict = dict2
    else:
        final_trend = "sideways"
        final_text = "暂无资讯"
        final_dict = {}

    return (final_trend, final_text, final_dict)

# ===================== 轮询全局停止信号 =====================
poll_stop_event = threading.Event()

def in_trade_window(now: datetime, mode: str) -> bool:
    """
    mode: split / full
    split: 09:00-11:20, 13:30-15:00, 21:00-22:50
    full: 09:00 ~ 22:50
    """
    t = now.time()
    if mode == "full":
        s = datetime.strptime("09:00:00", "%H:%M:%S").time()
        e = datetime.strptime("22:50:00", "%H:%M:%S").time()
        return s <= t <= e
    else:
        s1s = datetime.strptime("09:00:00", "%H:%M:%S").time()
        s1e = datetime.strptime("11:20:00", "%H:%M:%S").time()
        s2s = datetime.strptime("13:30:00", "%H:%M:%S").time()
        s2e = datetime.strptime("15:00:00", "%H:%M:%S").time()
        s3s = datetime.strptime("21:00:00", "%H:%M:%S").time()
        s3e = datetime.strptime("22:50:00", "%H:%M:%S").time()
        return (s1s <= t <= s1e) or (s2s <= t <= s2e) or (s3s <= t <= s3e)

# ===================== 轮询函数（直接丢进子线程） =====================
def trend_poll_loop(interval_min: int = 5, mode: str = "split"):
    """
    :param interval_min: 轮询间隔，单位分钟
    :param mode: split / full
    输出打印：{"m2701":"rise"}
    """
    print_context(f"【资讯轮询线程启动】mode={mode} interval={interval_min}min")
    try:
        while not poll_stop_event.is_set():
            now = datetime.now()
            with shared_data.variables_rlock:
                ts_code = shared_data.ts_code or shared_data.default_tscode
            result_map: Dict[str, str] = {}
            if in_trade_window(now, mode):
                try:
                    trend, info_text, judge_dict = fetch_future_trend(ts_code)
                except Exception as e:
                    print_context(f"[{now.strftime('%H:%M:%S')}]【资讯拉取异常】{ts_code}, err={str(e)}")
                    poll_stop_event.wait(timeout=interval_min * 60)
                    continue
                # 只写一次共享变量
                with shared_data.variables_rlock:
                    shared_data.direction = trend
                with dict_rlock:
                    direction_dict[ts_code] = trend
                result_map[ts_code] = trend
                # 写入对应合约yaml
                set_temp_param("temp_direction", trend, ts_code=None, skip_if_same=True)
                print_context(
                    f"[{datetime.now().strftime('%H:%M:%S')}]【资讯轮询结果】{result_map} | trend={trend} | {info_text}"
                )
            poll_stop_event.wait(timeout=interval_min * 60)
    finally:
        # 线程退出时关闭浏览器
        PlaywrightSingleton.close()
        print_context("【资讯轮询线程退出】")

if __name__ == '__main__':
    trend_poll_loop(mode='full', interval_min=1)
