import sys
from public import shared_data
import tushare as ts
import os
from datetime import datetime, timedelta
import pandas as pd
from public.jiaoyisuo import futures_info
import re
from functools import lru_cache
import akshare as ak


# 配置pandas打印格式（全局生效）
def setup_pandas_display():
    # 核心对齐配置
    pd.set_option('display.unicode.ambiguous_as_wide', True)  # 处理模糊字符宽度
    pd.set_option('display.unicode.east_asian_width', True)   # 处理中文字符宽度
    # 其他优化配置
    pd.set_option('display.max_columns', None)                # 显示所有列
    pd.set_option('display.width', None)                      # 自动适配宽度
    pd.set_option('display.max_colwidth', None)               # 列宽不截断
    pd.set_option('display.float_format', '{:.2f}'.format)    # 浮点数统一保留1位小数（可选）


# 执行配置
setup_pandas_display()


def init_tushare():
    """初始化Tushare接口，读取本地环境变量中的token"""
    tushare_stoken = os.getenv("TUSHARE_TOKEN")
    if not tushare_stoken:
        raise ValueError(
            "未找到TUSHARE_TOKEN环境变量！\n"
            "Windows配置：set TUSHARE_TOKEN=你的stoken\n"
            "Mac/Linux配置：export TUSHARE_TOKEN=你的stoken"
        )
    pro = ts.pro_api(tushare_stoken)
    return pro


@lru_cache(maxsize=None)
def get_effective_trade_data(ts_code=shared_data.ts_code, target_days=shared_data.target_days, start_date=None):
    """
    获取指定期货合约的有效交易数据（过滤非交易日）
    """
    # ts_code = "au2604" if shared_data.ts_code == "" else shared_data.ts_code
    pro = init_tushare()
    if "." not in ts_code:
        # print(f'请使用带扩展名的期货名称')
        prefix = re.match(r'[a-zA-Z]+', ts_code).group()
        ext = futures_info[prefix]['ext']
        ts_code = ".".join([ts_code, ext])
        # print(f'标准期货名称：{ts_code}')
    if start_date is None:
        start_date = datetime.now().strftime("%Y%m%d")
    else:
        try:
            datetime.strptime(start_date, "%Y%m%d")
        except ValueError:
            raise ValueError("日期格式错误！请使用YYYYMMDD格式（如20251010）")
    start_dt = datetime.strptime(start_date, "%Y%m%d")
    end_dt = start_dt - timedelta(days=target_days * 2)
    end_date = end_dt.strftime("%Y%m%d")
    # 仅保留免费会员100%可获取的核心字段（移除原生change字段）
    try:
        df = ak.futures_main_sina(symbol="lu2605")  # 低硫燃油2605
        print(f'[{ts_code}交易信息（来自新浪财经网）]\n{df.tail(10)}')

        df = pro.fut_daily(
            ts_code=ts_code,
            start_date=end_date,
            end_date=start_date,
            fields="trade_date,high,low,open,close,pre_close"
        )
    except Exception as e:
        raise Exception(f"获取数据失败：{e}\n提示：免费会员积分不足/合约代码错误/接口限制可能导致此问题")

    if df.empty:
        raise ValueError(f"{ts_code}在{end_date}~{start_date}期间无交易数据")
    if df.isna().any().any():  # df.isnull().any().any()等价
        print("获取的数据中存在空值，请检查数据质量！")
        return
    # 调试：打印实际返回的字段（方便排查）
    # print(f"Tushare返回数据索引：{df.columns.tolist()}")
    # 手动计算涨跌额（收盘价 - 昨收盘价），避免依赖原生change字段
    # df["high_low_change"] = df.apply(
    #     lambda row: row["high"] - row["low"] if pd.notna(row["high"]) and pd.notna(row["low"]) else None,
    #     axis=1
    # )
    df["high_low_change"] = (df["high"] - df["low"]).round(2)  # 每日峰差值（最高价-最低价）
    df["change"] = (df["open"] - df["pre_close"]).round(2)  # 当日开盘价-上交易日
    df['high_open'] = (df['high'] - df['open']).round(2)  # 每日最高价与开盘价的差值
    df['low_open'] = (df['open'] - df['low']).round(2)  # 每日开盘价与最低价的差值
    df = df.sort_values("trade_date", ascending=False).reset_index(drop=True)
    print(f"已从tushare官网获取[{ts_code}]的历史交易数据：\n{df}")
    if len(df) < target_days:
        print(f'已获取[{ts_code}]到{len(df)}天有效数据：\n{df}')
        return df
        # raise ValueError(f"仅获取到{len(df)}天有效数据，不足{target_days}天（非交易日已过滤）")
    else:
        return df.head(target_days)


def convert_to_target_dict(df):
    """
    将DataFrame转换为指定字典格式：
    键：交易日期（如20251218），值：[最高价, 最低价, 开盘价, 收盘价, ......]
    """
    if df is None or df.empty:
        print("可能是tushare接口问题，未获取到期货交易历史数据，程序即将退出！")
        return None
    result = {}
    for idx, row in df.iterrows():
        # 核心修改：以交易日期作为字典键
        trade_date = row["trade_date"]
        # 字段兜底：避免字段缺失导致KeyError
        result[trade_date] = [
            row.get("high", None),
            row.get("low", None),
            row.get("open", None),
            row.get("close", None),
            row.get("pre_close", None),
            row.get("high_low_change", None),  # 使用手动计算的日峰值差
            row.get("change", None),  # 使用手动计算的涨跌额
            row.get("high_open", None),
            row.get("low_open", None)
        ]
    return result


def get_futures_daily_data(ts_code=shared_data.ts_code, target_days=shared_data.target_days, start_date=None):
    """主函数：获取期货日交易数据并返回指定格式字典（键为交易日期）"""
    # pro = init_tushare()

    df = get_effective_trade_data(ts_code, target_days, start_date)
    result_dict = convert_to_target_dict(df)
    save_folder = os.path.join(os.path.dirname(__file__), "futures_data")
    if not os.path.exists(save_folder):
        os.makedirs(save_folder)
    pkl_file = os.path.join(save_folder, f"{ts_code}{start_date}.pkl")
    # print(f"保存数据文件：{pkl_file}")
    pd.to_pickle(result_dict, pkl_file)  # 保存为pickle文件
    # with open(pkl_file, "wb") as f:
    #     pickle.dump(result_dict, f)  # 保存为pickle文件
    # print(f'期货日交易数据：{result_dict}')
    return result_dict


def fetch_data(ts_code=shared_data.ts_code, target_days=shared_data.target_days, start_date=None):  # 模块核心函数
    # future_data = None
    if start_date is None:
        start_date = datetime.now().strftime("%Y%m%d")
    save_folder = os.path.join(os.path.dirname(__file__), "futures_data")
    pkl_file = os.path.join(save_folder, f"{ts_code}{start_date}.pkl")
    if os.path.exists(pkl_file):
        print(f'数据来源： {pkl_file}--collecte_history_data.py')
        future_data = pd.read_pickle(pkl_file)  # 读取pickle文件, 以下注释部分是另一种读取方式
        # with open(pkl_file, "rb") as f:
        #     future_data = pickle.load(f)  # 直接读取pickle文件
        # print(f"本地数据读取成功并以字典形式返回!")
    else:
        # print(f"数据来源： tushare官网\n读取后的数据保存位置：{pkl_file}--collecte_history_data.py")
        future_data = get_futures_daily_data(ts_code, target_days, start_date)
    df_data = []
    for k, v in future_data.items():
        row = [k] + v
        df_data.append(row)
    columns = ["日期", "最高价", "最低价", "开盘价", "收盘价", "上收盘价", "峰差", "涨幅", "高开差", "低开差"]
    future_data = pd.DataFrame(df_data, columns=columns)

    # print(f"[{ts_code}]期货日交易数据文件来源----{os.path.abspath(__file__)}\n{future_data}")
    return future_data


def analyze_data():
    with shared_data.dict_lock:
        ts_code = "au2604" if shared_data.ts_code is None else shared_data.ts_code
        open_price = 1112 if shared_data.open_price == 0 else shared_data.open_price
        target_days = shared_data.target_days
        direction = shared_data.direction

    # if direction not in ["buy", "sell", None]:
    #     print(f"direction参数只能是列表中的参数-[None,'buy','sell'],当前设置值：{direction}", file=sys.stderr)
    #     sys.exit(1)
    if open_price is None and direction is None:
        print("today_open_price(今日开盘价)、direction(多空方向)不能同时为空！")
        sys.exit(1)
    ts_code_params = {"ts_code": ts_code}  # 定义期货商品下单参数字典
    prefix = re.match(r'[a-zA-Z]+', ts_code).group()
    chinese_name = futures_info[prefix]["name"]
    exchange = futures_info[prefix]["exchange"]
    # 根据ts_code传入合约单位
    min_price_change = futures_info[prefix]['min_price_change']
    # one_tick_profit = futures_info[prefix]['one_tick_profit']
    # shared_data.contract_unit = float(one_tick_profit / min_price_change)
    if "." not in ts_code:
        # print(f'请使用带扩展名的期货名称')
        ext = futures_info[prefix]['ext']
        ts_code = ".".join([ts_code, ext])
    df = fetch_data(ts_code, target_days=target_days, start_date=None)
    # 上一天交易日的收盘价、开盘价
    today = datetime.now().strftime("%Y%m%d")
    pre_day = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    df_index = df.set_index('日期')
    pre_close_price = df_index.loc[pre_day, "收盘价"]  # 获取前交易日的收盘价
    pre_open_price = df_index.loc[pre_day, "开盘价"]  # 获取前交易日的开盘价
    # print(f"期货商品[{ts_code}-{chinese_name}-{exchange}]下单参数：\n{'-' * 80}")
    # 根据今日开盘对比上一交易日收盘价预测今日期货价位的走势

    if direction is None:
        if open_price - pre_close_price > 0:
            direction = "buy"
        elif open_price - pre_close_price < 0:
            direction = "sell"
        elif open_price - pre_open_price > 0:
            direction = "buy"
        elif open_price - pre_open_price < 0:
            direction = "sell"
        # print(f"多空方向[direction](buy-买多，sell-卖空): {direction} [方向来源：交易数据分析]")
    else:
        pass
        # print(f"多空方向[direction](buy-买多，sell-卖空): {direction} [方向来源：专业推荐]")
    high_avg = round(df['最高价'].mean(), 0)  # 设定天数的最高价数组的平均价
    high_max = round(df['最高价'].max(), 0)  # 设定天数的最高价数组的最大值
    high_min = round(df['最高价'].min(), 0)  # 设定天数的最高价数组的最小值
    low_avg = round(df['最低价'].mean(), 0)
    low_max = round(df['最低价'].max(), 0)
    low_min = round(df['最低价'].min(), 0)
    change_avg = round(df['峰差'].mean(), 0)  # 设定天数的最高价与最低价差值的数组中的平均值
    change_max = round(df['峰差'].max(), 0)  # 设定天数的最高价与最低价差值的数组中的最大值
    change_min = round(df['峰差'].min(), 0)  # 设定天数的最高价与最低价差值的数组中的最小值
    high_open_avg = round(df['高开差'].mean(), 0)
    low_open_avg = round(df['低开差'].mean(), 0)
    #
    # 计算涨势的买入方案

    if direction == 'buy':  # 价格上涨走势确定买入信号
        trade_price = low_avg - low_avg % min_price_change
        profit_price = round((open_price + high_open_avg), 0)
        loss_price = low_min - low_open_avg

        if loss_price > trade_price:
            print(f'止损价设置不合理：止损价[{loss_price}]>交易价[{trade_price}]\n程序已自动退出，请重置！')
            sys.exit()
        elif profit_price < trade_price:
            print(f'止盈价设置不合理:止盈价[{profit_price}]>交易价[{trade_price}]\n程序已自动退出，请重置！')
            sys.exit()
        ts_code_params['buy_or_sell'] = direction
        ts_code_params['trade_price'] = trade_price
        ts_code_params['profit_price'] = profit_price
        ts_code_params['loss_price'] = loss_price
    elif direction == 'sell':
        trade_price = high_avg - high_avg % min_price_change
        profit_price = round((low_avg + low_open_avg), 0)
        loss_price = high_max + high_open_avg
        if loss_price < trade_price:
            print(f'止损价设置不合理：止损价[{loss_price}]>交易价[{trade_price}]\n程序已自动退出，请重置！')
            sys.exit()
        elif profit_price > trade_price:
            print(f'止盈价设置不合理:止盈价[{profit_price}]>交易价[{trade_price}]\n程序已自动退出，请重置！')
            sys.exit()
        ts_code_params['buy_or_sell'] = direction
        ts_code_params['trade_price'] = trade_price
        ts_code_params['profit_price'] = profit_price
        ts_code_params['loss_price'] = loss_price

    with shared_data.dict_lock:
        shared_data.order_pramas.clear()
        shared_data.order_pramas.update(ts_code_params)
    print(f'程序根据{shared_data.target_days}期的tushare数据分析出的下单参数：\n{shared_data.order_pramas}')
    return ts_code_params


# ------------------- 示例调用 -------------------
if __name__ == "__main__":
    # print(get_effective_trade_data())
    # fetch_data(ts_code="au2604", target_days=20, start_date=None)
    analyze_data()
    for k, (key, value) in enumerate(shared_data.order_pramas.items()):
        print(f"{k}.{key}:{value}")
    # get_futures_daily_data()
    # get_effective_trade_data()
