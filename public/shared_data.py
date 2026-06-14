import threading
from collections import deque
from datetime import datetime
from pywinauto import mouse
from chinese_calendar import is_holiday  # 纯本地节假日库，一次安装永久用

user_type = 0  # 0-模拟用户  1-国泰君安期货用户
user_name = ""  # 模拟交易-1811889418 国泰君安_CTP85415809
trade_window = None  # 同花顺交易平台桌面对象
current_price_dict = {}  # 即时行情中的期货商品买卖价格
cur_price_deque = deque(maxlen=20000)
deque_lock = threading.Lock()
interval = 5  # 从同花顺窗口读取即时价格的时间间隔，默认为5秒
login_control = {}  # 登录期货通交易软件
ths_common_control = {}  # 交易平台常用控件字典,此处为多进程管理模式，以便进程数据共享
condition_control = {}  # 条件单窗口控件映射字典
logger = None  # 根据用户选择的日志器
ths_lock = threading.Lock()  # 创建名称为ths_lock的进程锁
dict_lock = threading.Lock()  # 创建字典读写线程安全锁
ths_future_edit_lock = False  # 期货名称输入（edit）框是否锁定，默认是False，亦即可以输入、编辑
ts_code = ""  # 期货商品代码（如au2601)
search_future_list = []  # 待搜索的期货商品代码列表
open_price = {}  # 交易品种开盘价信息：trade.order()
pre_profit = 0.0  # 手动设置固定止盈值
pre_loss = 0.0  # 手动设置固定止损值
target_days = 10  # 从tu_share获取ts_code历史行情数据（天数）
lot_size = 1  # 期货买卖手数，默认值1，不同商品规定必须最少多少手
direction = ""  # 如果有专业推荐，直接写买多-Rise、卖空-Fall，否则由历史数据与今日开盘价来确定多空方向
history_trade_df = None  # 期货品种历史交易原始数据，dataframe格式；
history_data_analysis = {}  # 期货商品历史交易数据，来源于future_data模块
order_param_dict = {}  # 期货商品行情下单参数：字典键顺序-"建仓交易时间", "平仓交易时间", "用户", "期货品种",
future_quote_dict = {}  # 期货行情 https://push2.eastmoney.com/api/qt/ulist.np/get
future_info_dict = {}  # 期货资讯行情
# "交易方向", "交易价", "止损价", "止盈价", "交易前总额", "交易后总额", "利润"
trade_menu_dict = {}  # 成交后的交易参数,在trade.py模块中产生
ts_code_attribute_dict = {}  # 交易品种的基本属性
# min_price_change = 0.00  # 最小跳点数
# commission = 0.0  # 期货商品的每一手的手续费
# leverage = 0.0  # 盈利杠杆,用来计算实时盈亏：差价 * 杠杆比例
# margin = 0.0  # 期货商品保证金(与即时价位有关）

total_balance = 0.0  # 账户总金额
available_balance = 0.0  # 账户可用资金
quote_list = ["m2609", "c2609", "jd2609"]  # 默认要从东方财富网获取开盘价等信息的期货品种

trade_time_table = [(9, 0, 10, 15), (10, 30, 11, 30), (13, 30, 15, 0), (21, 0, 23, 0), (0, 0, 1, 30)]  # 交易时间表, 最后一个用测试。
# tradeoff = False  # 只是检测是不是在交易时间段
start_trade_date = None  # 期货开始交易时间（下单日期）


# ===================== 核心函数 =====================
def is_trade_statue() -> bool:
    """
    判断是否持仓或是否在交易状态中：权益 != 可用资金 → 有持仓、交易中、返回True
    返回：True=有持仓 / False=无持仓
    """
    valid_chars = {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", ".", "-"}

    try:
        with ths_lock:
            equity_ctrl = ths_common_control["权益"][0]
            available_ctrl = ths_common_control["可用资金"][0]

            equity_text = equity_ctrl.window_text().strip()
            available_text = available_ctrl.window_text().strip()

        # 提取数字
        def get_num(text):
            s = "".join(c for c in text if c in valid_chars)
            return float(s) if s else 0.0

        equity = get_num(equity_text)  # 权益资金即用户总资金
        available = get_num(available_text)  # 可用资金（如果在交易中则可用资金就会小于总资金）

        # 差异 > 1 元判定为有持仓
        return abs(equity - available) > 1.0

    except:
        return False


def trade_flag() -> bool:  # 判断是否在合法的交易时间段内
    now = datetime.now()
    hour = now.hour
    minute = now.minute
    second = now.second
    # 1. 周末休市
    if now.weekday() in [5, 6]:
        return False

    # 2. 节假日休市
    if is_holiday(now):
        return False

    # 3. 交易时间段判断,不在交易时段内休市
    current_seconds = hour * 3600 + minute * 60 + second
    for (sh, sm, eh, em) in trade_time_table:
        start = sh * 3600 + sm * 60
        end = eh * 3600 + em * 60
        if start <= current_seconds <= end:
            return True
    return False


# ===================== 测试 =====================

def is_around(checked_value, target_value, error_range=5):  # 检测坐标位置函数,定位窗口控件时需用
    return (target_value - error_range) <= checked_value <= (target_value + error_range)


def click_position(rect_tuple):

    x = rect_tuple[0] + (rect_tuple[2] - rect_tuple[0])//2
    y = rect_tuple[1] + (rect_tuple[3] - rect_tuple[1])//2
    return mouse.click(button='left', coords=(x, y))




if __name__ == "__main__":
    # print_context(f"今天是：{datetime.now().strftime('%Y/%m/%d %H:%M:%S')},期货交易：{is_trade_period}")
    # print(default_futures)
    pass