from time import sleep

from datetime import datetime
from data.data_from_sina import bin_analyzer
from core.market_ctx import get_market_ctx
import pandas as pd
from public.jiaoyisuo import get_future_info
from public import shared_data
from public.print_context import print_context
from sendmsg.weichat_push import send_msg
from public.shared_data import click_position, is_trade_status, trade_flag
from log.trade_log import setup_trade_loggers
from data.get_quote import get_open_price
from data.data_from_sina import fetch_future_data
from data.db_price import read_db
from public.shared_data import get_data_cache_dir
import signal
logger = setup_trade_loggers()
stop_flag = False
# 为本程序注册一个程序：收到退出程序时发出信号以安全停止；
def sig_handler(signum, frame):
    global stop_flag
    stop_flag = True
signal.signal(signal.SIGINT, sig_handler)


def order(ts_code=None):
    global stop_flag

    while not stop_flag:
        # trade_period = trade_flag()  # 检测是否在交易时段
        # if not trade_period:
        #     sleep(1)
        #     logger.info(f"目前处于合法交易时段，等待交易的期货品种 - {ts_code}")
        #     continue
        # trade_status = is_trade_status()  # 检测目前是否有品种交易中
        # if trade_status:
        #     sleep(1)
        #     continue
        # ts_code = shared_data.ts_code if ts_code is None else ts_code
        eval_ctx = get_market_ctx(ts_code)  # 获取命名空间字典供后续eval()使用
        print(eval("open==pre_close", eval_ctx))
        logger.info(f"目前处于合法交易时段，等待交易的期货品种 - {ts_code}")
        # 运行检查条件配置池中的相关函数以确定下单参数下单这个参数怎么写？




        sleep(5)



# ===================== 启动 =====================
if __name__ == "__main__":
    order(ts_code="m2609")

