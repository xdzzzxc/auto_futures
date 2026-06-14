# 交易所代码映射
from typing import Any, Dict


EXCHANGE_CODES = {
    '上期所': 'SHF',
    '大商所': 'DCE',
    '郑商所': 'CZC',
    '中金所': 'CFX',
    '广期所': 'GFE',
    '上能源': 'INE'
}
futures_info = {
    # ===================== 上期所（SHF） =====================
    'au': {'exchange': '上期所', 'name': '黄金', 'ext': 'SHF', 'margin': 0.10, 'leverage': 10.0, 'commission': 100, 'night_trading': True, 'min_price_change': 0.02, 'one_tick_profit': 20},
    'ag': {'exchange': '上期所', 'name': '白银', 'ext': 'SHF', 'margin': 0.12, 'leverage': 8.33, 'commission_rate': 0.00004, 'night_trading': True, 'min_price_change': 1, 'one_tick_profit': 15},
    'cu': {'exchange': '上期所', 'name': '沪铜', 'ext': 'SHF', 'margin': 0.09, 'leverage': 11.11, 'commission_rate': 0.00005, 'night_trading': True, 'min_price_change': 10, 'one_tick_profit': 50},
    'al': {'exchange': '上期所', 'name': '沪铝', 'ext': 'SHF', 'margin': 0.08, 'leverage': 12.5, 'commission': 3, 'night_trading': True, 'min_price_change': 5, 'one_tick_profit': 25},
    'zn': {'exchange': '上期所', 'name': '沪锌', 'ext': 'SHF', 'margin': 0.11, 'leverage': 9.09, 'commission': 3, 'night_trading': True, 'min_price_change': 5, 'one_tick_profit': 25},
    'pb': {'exchange': '上期所', 'name': '沪铅', 'ext': 'SHF', 'margin': 0.11, 'leverage': 9.09, 'commission': 3, 'night_trading': True, 'min_price_change': 5, 'one_tick_profit': 25},
    'ni': {'exchange': '上期所', 'name': '沪镍', 'ext': 'SHF', 'margin': 0.13, 'leverage': 7.69, 'commission_rate': 0.00005, 'night_trading': True, 'min_price_change': 10, 'one_tick_profit': 100},
    'sn': {'exchange': '上期所', 'name': '沪锡', 'ext': 'SHF', 'margin': 0.10, 'leverage': 10.0, 'commission_rate': 0.00005, 'night_trading': True, 'min_price_change': 10, 'one_tick_profit': 100},
    'rb': {'exchange': '上期所', 'name': '螺纹钢', 'ext': 'SHF', 'margin': 0.09, 'leverage': 11.11, 'commission_rate': 0.0001, 'night_trading': True, 'min_price_change': 1, 'one_tick_profit': 10},
    'hc': {'exchange': '上期所', 'name': '热卷', 'ext': 'SHF', 'margin': 0.09, 'leverage': 11.11, 'commission_rate': 0.0001, 'night_trading': True, 'min_price_change': 1, 'one_tick_profit': 10},
    'bu': {'exchange': '上期所', 'name': '沥青', 'ext': 'SHF', 'margin': 0.10, 'leverage': 10.0, 'commission_rate': 0.0001, 'night_trading': True, 'min_price_change': 1, 'one_tick_profit': 10},
    'ru': {'exchange': '上期所', 'name': '天然橡胶', 'ext': 'SHF', 'margin': 0.10, 'leverage': 10.0, 'commission_rate': 0.0001, 'night_trading': True, 'min_price_change': 5, 'one_tick_profit': 25},
    'fu': {'exchange': '上期所', 'name': '燃料油', 'ext': 'SHF', 'margin': 0.10, 'leverage': 10.0, 'commission_rate': 0.0001, 'night_trading': True, 'min_price_change': 1, 'one_tick_profit': 10},
    'sp': {'exchange': '上期所', 'name': '纸浆', 'ext': 'SHF', 'margin': 0.10, 'leverage': 10.0, 'commission_rate': 0.0001, 'night_trading': True, 'min_price_change': 2, 'one_tick_profit': 20},
    'ss': {'exchange': '上期所', 'name': '不锈钢', 'ext': 'SHF', 'margin': 0.09, 'leverage': 11.11, 'commission': 2, 'night_trading': True, 'min_price_change': 5, 'one_tick_profit': 25},

    # ===================== 郑商所（CZC） =====================
    'sr': {'exchange': '郑商所', 'name': '白糖', 'ext': 'CZC', 'margin': 0.07, 'leverage': 14.29, 'commission': 3, 'night_trading': True, 'min_price_change': 1, 'one_tick_profit': 10},
    'ta': {'exchange': '郑商所', 'name': 'PTA', 'ext': 'CZC', 'margin': 0.07, 'leverage': 14.29, 'commission': 3, 'night_trading': True, 'min_price_change': 2, 'one_tick_profit': 10},
    'cf': {'exchange': '郑商所', 'name': '棉花', 'ext': 'CZC', 'margin': 0.08, 'leverage': 12.5, 'commission': 4.3, 'night_trading': True, 'min_price_change': 5, 'one_tick_profit': 25},
    'ma': {'exchange': '郑商所', 'name': '甲醇', 'ext': 'CZC', 'margin': 0.08, 'leverage': 12.5, 'commission_rate': 0.0001, 'night_trading': True, 'min_price_change': 1, 'one_tick_profit': 10},
    'fg': {'exchange': '郑商所', 'name': '玻璃', 'ext': 'CZC', 'margin': 0.10, 'leverage': 10.0, 'commission': 6, 'night_trading': True, 'min_price_change': 1, 'one_tick_profit': 20},
    'sa': {'exchange': '郑商所', 'name': '纯碱', 'ext': 'CZC', 'margin': 0.10, 'leverage': 10.0, 'commission_rate': 0.0002, 'night_trading': True, 'min_price_change': 1, 'one_tick_profit': 20},
    'zc': {'exchange': '郑商所', 'name': '动力煤', 'ext': 'CZC', 'margin': 0.15, 'leverage': 6.67, 'commission': 6, 'night_trading': False, 'min_price_change': 0.2, 'one_tick_profit': 20},
    'oi': {'exchange': '郑商所', 'name': '菜油', 'ext': 'CZC', 'margin': 0.08, 'leverage': 12.5, 'commission': 3, 'night_trading': True, 'min_price_change': 2, 'one_tick_profit': 10},
    'rm': {'exchange': '郑商所', 'name': '菜粕', 'ext': 'CZC', 'margin': 0.07, 'leverage': 14.29, 'commission': 1.5, 'night_trading': True, 'min_price_change': 1, 'one_tick_profit': 10},
    'cy': {'exchange': '郑商所', 'name': '棉纱', 'ext': 'CZC', 'margin': 0.08, 'leverage': 12.5, 'commission': 4.3, 'night_trading': True, 'min_price_change': 5, 'one_tick_profit': 25},
    'ap': {'exchange': '郑商所', 'name': '苹果', 'ext': 'CZC', 'margin': 0.10, 'leverage': 10.0, 'commission': 5, 'night_trading': False, 'min_price_change': 1, 'one_tick_profit': 10},
    'jr': {'exchange': '郑商所', 'name': '粳稻', 'ext': 'CZC', 'margin': 0.05, 'leverage': 20.0, 'commission': 3, 'night_trading': False, 'min_price_change': 1, 'one_tick_profit': 20},
    'lr': {'exchange': '郑商所', 'name': '晚籼稻', 'ext': 'CZC', 'margin': 0.05, 'leverage': 20.0, 'commission': 3, 'night_trading': False, 'min_price_change': 1, 'one_tick_profit': 20},
    'pg': {'exchange': '大商所', 'name': '液化石油气', 'ext': 'DCE', 'margin': 0.12, 'leverage': 8.33, 'commission': 6, 'night_trading': True, 'min_price_change': 1, 'one_tick_profit': 20},

    # ===================== 大商所（DCE） =====================
    'lh': {'exchange': '大商所', 'name': '生猪', 'ext': 'DCE', 'margin': 0.07, 'leverage': 14.29, 'commission': 1.5, 'night_trading': False, 'min_price_change': 1, 'one_tick_profit': 10},
    'jd': {'exchange': '大商所', 'name': '鸡蛋', 'ext': 'DCE', 'margin': 0.07, 'leverage': 14.29, 'commission': 1.5, 'night_trading': False, 'min_price_change': 1, 'one_tick_profit': 10},
    'm': {'exchange': '大商所', 'name': '豆粕', 'ext': 'DCE', 'margin': 0.07, 'leverage': 14.29, 'commission': 1.5, 'night_trading': True, 'min_price_change': 1, 'one_tick_profit': 10},
    'y': {'exchange': '大商所', 'name': '豆油', 'ext': 'DCE', 'margin': 0.08, 'leverage': 12.5, 'commission': 2.5, 'night_trading': True, 'min_price_change': 2, 'one_tick_profit': 10},
    'p': {'exchange': '大商所', 'name': '棕榈油', 'ext': 'DCE', 'margin': 0.08, 'leverage': 12.5, 'commission': 2.5, 'night_trading': True, 'min_price_change': 2, 'one_tick_profit': 10},
    'c': {'exchange': '大商所', 'name': '玉米', 'ext': 'DCE', 'margin': 0.05, 'leverage': 20.0, 'commission': 1.2, 'night_trading': False, 'min_price_change': 1, 'one_tick_profit': 10},
    'i': {'exchange': '大商所', 'name': '铁矿石', 'ext': 'DCE', 'margin': 0.12, 'leverage': 8.33, 'commission_rate': 0.0001, 'night_trading': True, 'min_price_change': 0.5, 'one_tick_profit': 50},
    'j': {'exchange': '大商所', 'name': '焦炭', 'ext': 'DCE', 'margin': 0.20, 'leverage': 5.0, 'commission_rate': 0.0001, 'night_trading': True, 'min_price_change': 0.5, 'one_tick_profit': 50},
    'jm': {'exchange': '大商所', 'name': '焦煤', 'ext': 'DCE', 'margin': 0.15, 'leverage': 6.67, 'commission_rate': 0.0001, 'night_trading': True, 'min_price_change': 0.5, 'one_tick_profit': 30},
    'l': {'exchange': '大商所', 'name': '塑料', 'ext': 'DCE', 'margin': 0.08, 'leverage': 12.5, 'commission': 2, 'night_trading': True, 'min_price_change': 1, 'one_tick_profit': 5},
    'pp': {'exchange': '大商所', 'name': '聚丙烯', 'ext': 'DCE', 'margin': 0.08, 'leverage': 12.5, 'commission': 2, 'night_trading': True, 'min_price_change': 1, 'one_tick_profit': 5},
    'v': {'exchange': '大商所', 'name': 'PVC', 'ext': 'DCE', 'margin': 0.08, 'leverage': 12.5, 'commission': 2, 'night_trading': True, 'min_price_change': 1, 'one_tick_profit': 5},
    'eg': {'exchange': '大商所', 'name': '乙二醇', 'ext': 'DCE', 'margin': 0.08, 'leverage': 12.5, 'commission': 2, 'night_trading': True, 'min_price_change': 1, 'one_tick_profit': 10},
    'eb': {'exchange': '大商所', 'name': '苯乙烯', 'ext': 'DCE', 'margin': 0.10, 'leverage': 10.0, 'commission': 2, 'night_trading': True, 'min_price_change': 1, 'one_tick_profit': 5},
    'b': {'exchange': '大商所', 'name': '豆二', 'ext': 'DCE', 'margin': 0.07, 'leverage': 14.29, 'commission': 1.5, 'night_trading': False, 'min_price_change': 1, 'one_tick_profit': 10},
    'bb': {'exchange': '大商所', 'name': '胶合板', 'ext': 'DCE', 'margin': 0.10, 'leverage': 10.0, 'commission': 3, 'night_trading': False, 'min_price_change': 0.05, 'one_tick_profit': 50},
    'fb': {'exchange': '大商所', 'name': '纤维板', 'ext': 'DCE', 'margin': 0.10, 'leverage': 10.0, 'commission': 3, 'night_trading': False, 'min_price_change': 0.05, 'one_tick_profit': 50},
    'cs': {'exchange': '大商所', 'name': '玉米淀粉', 'ext': 'DCE', 'margin': 0.07, 'leverage': 14.29, 'commission': 1.5, 'night_trading': False, 'min_price_change': 1, 'one_tick_profit': 10},

    # ===================== 中金所（CFFEX） =====================
    'if': {'exchange': '中金所', 'name': '沪深300股指', 'ext': 'CFFEX', 'margin': 0.12, 'leverage': 8.33, 'commission_rate': 0.000092, 'night_trading': False, 'min_price_change': 0.2, 'one_tick_profit': 60},
    'ih': {'exchange': '中金所', 'name': '上证50股指', 'ext': 'CFFEX', 'margin': 0.12, 'leverage': 8.33, 'commission_rate': 0.000092, 'night_trading': False, 'min_price_change': 0.2, 'one_tick_profit': 60},
    'ic': {'exchange': '中金所', 'name': '中证500股指', 'ext': 'CFFEX', 'margin': 0.12, 'leverage': 8.33, 'commission_rate': 0.000092, 'night_trading': False, 'min_price_change': 0.2, 'one_tick_profit': 100},
    'im': {'exchange': '中金所', 'name': '中证1000股指', 'ext': 'CFFEX', 'margin': 0.12, 'leverage': 8.33, 'commission_rate': 0.000092, 'night_trading': False, 'min_price_change': 0.2, 'one_tick_profit': 100},
    'ts': {'exchange': '中金所', 'name': '2年期国债', 'ext': 'CFFEX', 'margin': 0.01, 'leverage': 100.0, 'commission': 3, 'night_trading': False, 'min_price_change': 0.005, 'one_tick_profit': 125},
    'tf': {'exchange': '中金所', 'name': '5年期国债', 'ext': 'CFFEX', 'margin': 0.01, 'leverage': 100.0, 'commission': 3, 'night_trading': False, 'min_price_change': 0.005, 'one_tick_profit': 500},
    't': {'exchange': '中金所', 'name': '10年期国债', 'ext': 'CFFEX', 'margin': 0.015, 'leverage': 66.67, 'commission': 3, 'night_trading': False, 'min_price_change': 0.005, 'one_tick_profit': 500},
    'tl': {'exchange': '中金所', 'name': '30年期国债', 'ext': 'CFFEX', 'margin': 0.02, 'leverage': 50.0, 'commission': 3, 'night_trading': False, 'min_price_change': 0.005, 'one_tick_profit': 500},

    # ===================== 上期能源（INE） =====================
    'sc': {'exchange': '上期能源', 'name': '原油', 'ext': 'INE', 'margin': 0.15, 'leverage': 6.67, 'commission_rate': 0.0001, 'night_trading': True, 'min_price_change': 0.1, 'one_tick_profit': 100},
    'lu': {'exchange': '上期能源', 'name': '低硫燃料油', 'ext': 'INE', 'margin': 0.10, 'leverage': 10.0, 'commission_rate': 0.0001, 'night_trading': True, 'min_price_change': 1, 'one_tick_profit': 10},
    'nr': {'exchange': '上期能源', 'name': '20号胶', 'ext': 'INE', 'margin': 0.10, 'leverage': 10.0, 'commission_rate': 0.0001, 'night_trading': True, 'min_price_change': 5, 'one_tick_profit': 50},

    # ===================== 广期所（GAFEX） =====================
    'si': {'exchange': '广期所', 'name': '工业硅', 'ext': 'GAFEX', 'margin': 0.10, 'leverage': 10.0, 'commission': 6, 'night_trading': True, 'min_price_change': 5, 'one_tick_profit': 25},
    'lc': {'exchange': '广期所', 'name': '碳酸锂', 'ext': 'GAFEX', 'margin': 0.15, 'leverage': 6.67, 'commission_rate': 0.00032, 'night_trading': True, 'min_price_change': 10, 'one_tick_profit': 500},
}
# ==========================
# 有夜盘的期货品种（官方 2025）
# ==========================
FUTURES_HAVE_NIGHT = {
    # 大连商品交易所 DCE
    "m", "y", "a", "b", "c", "cs", "pp", "v", "l", "eg", "eb", "pg", "j", "jm", "i", "fb", "bb",

    # 郑州商品交易所 ZCE
    "ta", "fg", "oi", "rm", "cf", "zc", "ur", "sa", "pf", "pk", "ma",

    # 上海期货交易所 SHFE
    "cu", "al", "zn", "pb", "ni", "sn", "au", "ag", "rb", "hc", "wr", "fu", "bu", "ru", "sp",

    # 中国金融期货交易所 CFFEX 无夜盘
    # 广州期货交易所 GFEX
    "lc", "si",
}

# ==========================
# 无夜盘的期货品种（官方 2025）
# ==========================
FUTURES_NO_NIGHT = {
    "jd",  # 鸡蛋
    "rr",  # 粳米
    "lm",  # 锰硅
    "pm",  # 普麦
    "wh",  # 强麦
    "ri",  # 早籼稻
    "lr",  # 晚籼稻
    "sr",  # 白糖
    "ap",  # 苹果
    "cj",  # 红枣
    "ss",  # 不锈钢
    "ec",  # 集运指数
    "bc",  # 铜 BC
    "c"
}
# 数据说明：
# 元组结构：(交易所, 品种名称, 代码, 保证金(元), 每波动价值(元), 最新手续费(元), 是否有夜盘(True/False))
# 手续费为交易所基础标准，实际交易可能包含期货公司佣金
# 夜盘信息基于2024年交易所最新交易时间安排
# 新增品种包括原油、低硫燃料油、纯碱、硅铁、锰硅、烧碱等
select_future_dict = {
    "c": ["玉米", 2600, "大商所", "DCE"],
    "cs": ["玉米淀粉", 3000, "大商所", "DCE"],
    "m": ["豆粕", 3800, "大商所", "DCE"],
    "jd": ["鸡蛋", 4100, "大商所", "DCE"],
    "eg": ["乙二醇", 4400, "大商所", "DCE"],
    "eb": ["苯乙烯", 4500, "大商所", "DCE"],
    "pg": ["液化石油气", 4800, "大商所", "DCE"],
    "pk": ["花生", 4900, "大商所", "DCE"],
    "b": ["豆二", 5200, "大商所", "DCE"],
    "a": ["豆一", 5600, "大商所", "DCE"],
    "sm": ["锰硅", 5500, "大商所", "DCE"],
    "fg": ["玻璃", 4300, "郑商所", "ZCE"],
    "sa": ["纯碱", 4500, "郑商所", "ZCE"],
    "rm": ["菜粕", 4500, "郑商所", "ZCE"],
    "ma": ["甲醇", 3000, "郑商所", "ZCE"],
    "ta": ["PTA", 3500, "郑商所", "ZCE"],
    "pf": ["短纤", 3800, "郑商所", "ZCE"],
    "ur": ["尿素", 4000, "郑商所", "ZCE"],
    "cy": ["绵纱", 4200, "郑商所", "ZCE"],
    "sf": ["硅铁", 4900, "郑商所", "ZCE"],
    "rb": ["螺纹钢", 4400, "上期所", "SHFE"],
    "hc": ["热轧卷板", 4700, "上期所", "SHFE"],
    "wr": ["线材", 4800, "上期所", "SHFE"],
    "ss": ["不锈钢", 5000, "上期所", "SHFE"],
    "al": ["铝", 5200, "上期所", "SHFE"],
    "pb": ["铅", 5500, "上期所", "SHFE"],
    "zn": ["锌", 5800, "上期所", "SHFE"],
    "nr": ["20号胶", 5800, "上能源", "INE"]
}


def get_future_info(symbol: str) -> Dict[str, Any] | None:
    symbol = symbol.strip().lower()
    code = ''.join([c for c in symbol if c.isalpha()])
    info_dict: Dict[str, Any] = {"ts_code": symbol, "code": code}
    try:
        d = futures_info[code]
    except KeyError:
        return None
    info_dict.update(d)
    return info_dict


if __name__ == "__main__":
    print(get_future_info("jd2609"))
