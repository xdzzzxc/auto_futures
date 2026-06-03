from public import shared_data
import pandas as pd
import akshare as ak
from time import sleep
import random


# 配置pandas打印格式（全局生效）
def setup_pandas_display():
    pd.set_option('display.max_rows', None)
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

def collect_current_price(ts_code=None):
    if ts_code is None:
        print("请输入合法的期货品种代码，如黄金期货：au2609")
        return
    ts_code = ts_code if shared_data.ts_code == "" else shared_data.ts_code
    while True:
        real_min_df = ak.futures_zh_minute_sina(symbol=ts_code, period="1")
        if real_min_df.empty:
            print("新浪限流预警，请慎重操作以免IP被封！")
            sleep(random.uniform(2, 5))
            continue
        print(f'\r{real_min_df}', end='', flush=True)
        sleep(random.uniform(1.5, 3))




# ------------------- 示例调用 -------------------
if __name__ == "__main__":
    collect_current_price(ts_code="c2609")
