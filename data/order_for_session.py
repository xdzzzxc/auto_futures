from data.data_from_sina import fetch_future_data
from public.print_context import print_context
from collections import deque
import pandas as pd
import numpy as np
from public import shared_data

from data.get_quote import get_open_price
import test

def order_for_session(price_deque: deque, ts_code=None):
    # ===================== 1. 数据格式化 =====================
    # 把 deque 转成 DataFrame 方便计算
    df = pd.DataFrame(price_deque, columns=["time_str", "price"])
    df["price"] = df["price"].astype(float)           # 价格转数字
    df["time"] = pd.to_datetime(df["time_str"], format="%Y%m%d%H%M%S")



if __name__ == '__main__':
    deque = test.deque_price
    # print(deque)
    order_for_session(price_deque=deque, ts_code="c2609")




