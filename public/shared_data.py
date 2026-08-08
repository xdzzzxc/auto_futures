import threading
from time import sleep
import random
from collections import deque
from datetime import datetime
import time
import pyperclip
from pywinauto import mouse
from chinese_calendar import is_holiday  # 纯本地节假日库，一次安装永久用
from public.print_context import print_context
import os
from pathlib import Path
from datetime import timedelta
from tushare import shibor_data


user_type = 0  # 0-模拟用户  1-国泰君安期货用户
user_name = {0: "模拟交易-1811889418", 1: "国泰君安_CTP85415809"}  # 模拟交易-1811889418 国泰君安_CTP85415809
trade_window = None  # 同花顺交易平台桌面对象
# 打印限制设置（1次）
print_on_off = True

# 期货品种即时行情价格缓冲区及相关安全配置
get_price_interval = 5  # 从同花顺窗口读取即时价格的时间间隔，默认为5秒
k_minutes = 5  # 设置指定时长的最后一根K线的时间
current_price_dict = {}  # 即时行情中的期货商品买卖价格
cur_price_deque = deque(maxlen=20000)
price_buffer = []  # 缓冲区
buffer_lock = threading.Lock()  # 缓冲锁
last_flush_ts = time.time()  # 上次写入的时间戳
analyze_interval = 60  # 读取数据库数据的频率
analyze_interval_lock = threading.Lock()  # 加锁
FLUSH_INTERVAL = analyze_interval - 5  # 批量写入数据的时间间隔，小于读取数据频率
MAX_BUFFER_COUNT = FLUSH_INTERVAL // get_price_interval  # 缓冲区最多存200条数据，否则强制入库
read_mode = True  # 读取期货品种的当日价格模式：默认是deque数据-True;db数据库数据-False;
deque_lock = threading.Lock()
# 鼠标锁：平仓点击鼠标、防屏保壁纸程序使用鼠标
mouse_lock = threading.Lock()
sideways_product_list = {"m", "c", "jd"}

# __________________________________________________
login_control = {}  # 登录期货通交易软件
ths_common_control = {}  # 交易平台常用控件字典,此处为多进程管理模式，以便进程数据共享
condition_control = {}  # 条件单窗口控件映射字典
logger = None  # 根据用户选择的日志器
ths_lock = threading.Lock()  # 创建名称为ths_lock的进程锁
dict_lock = threading.Lock()  # 创建字典读写线程安全锁
ths_future_edit_lock = False  # 期货名称输入（edit）框是否锁定，默认是False，亦即可以输入、编辑
ts_code = ""  # 期货商品代码（如au2601)
search_future_list = []  # 待搜索的期货商品代码列表
open_price = None  # 交易品种开盘价信息：trade.order()
pre_profit = 0.0  # 手动设置固定止盈值
pre_loss = 0.0  # 手动设置固定止损值
target_days = 20  # 从tu_share获取ts_code历史行情数据（天数）
lot_size = 1  # 期货买卖手数，默认值1，不同商品规定必须最少多少手
direction = "Sideways"  # 如果有专业推荐，直接写买多-Rise、卖空-Fall，否则由历史数据与今日开盘价来确定多空方向
history_trade_df = None  # 期货品种历史交易原始数据，dataframe格式；
history_data_analysis = None  # 期货商品历史交易数据，来源于future_data模块
order_param_dict = {"云止损单": 3120, "云止盈单": 3050, "云保本单": None}  # 对应止损止盈设置
future_quote_dict = {}  # 期货行情 https://push2.eastmoney.com/api/qt/ulist.np/get
future_info_dict = {}  # 期货资讯行情
# "交易方向", "交易价", "止损价", "止盈价", "交易前总额", "交易后总额", "利润"
trade_menu_dict = {}  # 成交后的交易参数,在trade.py模块中产生
ts_code_attribute_dict = {}  # 交易品种的基本属性
BIN_NUM = 8  # 配置参数：箱体数量，日内短线推荐8个等宽箱体

total_balance = 0.0  # 账户总金额
available_balance = 0.0  # 账户可用资金
quote_list = ["m2609", "c2609", "jd2609"]  # 默认要从东方财富网获取开盘价等信息的期货品种

trade_time_table = [(9, 0, 10, 15), (10, 30, 11, 30), (13, 30, 15, 0), (21, 0, 23, 0)]  # 交易时间表, 最后一个用测试。
start_trade_date = None  # 期货开始交易时间（下单日期）
threading_monitor_profit_loss = False  # 设置自动止损止盈开关

# ===================== 核心函数 =====================
def is_trade_status() -> bool:
    """
    判断是否持仓或是否在交易状态中：权益 != 可用资金 → 有持仓、交易中、返回True
    返回：True=有持仓 / False=无持仓
    """
    global print_on_off
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
        if print_on_off:
            print(f"权益：{equity} 可用资金：{available}")
            print_on_off = False
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
    with mouse_lock:
        x = rect_tuple[0] + (rect_tuple[2] - rect_tuple[0])//2
        y = rect_tuple[1] + (rect_tuple[3] - rect_tuple[1])//2
        return mouse.click(button='left', coords=(x, y))

def simulate_input(window, ctrl, value):

    if any([window is None, ctrl is None, value is None]):
        print(f"本次操作失败，请结合检测参数结果作出修改：\nwindow-{window}; ctrl-{ctrl}; value-{value}")
        return False
    pyperclip.copy(value)
    try:
        window.set_focus()
        window.maximize()
        sleep(random.uniform(0.1, 0.5))
    except Exception as e:  # noqa
        print(f"窗口聚焦警告，继续执行：{str(e)}")
    try:
        ctrl.click_input()
        sleep(random.uniform(0.1, 0.5))
    except Exception as e:  # noqa
        return False
    try:
        ctrl.type_keys("^a", with_spaces=True)
        sleep(random.uniform(0.1, 0.5))
        ctrl.type_keys("^v", with_spaces=True)
        sleep(random.uniform(0.1, 0.5))
        ctrl.type_keys("{ENTER}", with_spaces=True)
        sleep(random.uniform(0.1, 0.5))
    except Exception as e:
        return False
    return True


def get_data_cache_dir(marker=None):
    from pathlib import Path
    if marker is None:
        marker = [".git", "requirements.txt", "main.py"]
    p = Path(__file__).resolve()
    root_dir = None
    for parent in p.parents:
        if any((parent / m).exists() for m in marker):
            root_dir = parent
            break
    if root_dir is None:
        raise FileNotFoundError("找不到项目根目录标记文件")
    cache_folder = root_dir / "data" / "futures_data"
    cache_folder.mkdir(parents=True, exist_ok=True)
    return str(cache_folder)

# 统一弹窗的写法,目前暂未复用,如有必要请在main.py模块中参照修改
def get_direction(title="交易方向", msg=None) -> str | None:
    import tkinter as tk
    default_dir = direction
    if msg is None:
        msg = (f"金投网推荐[{ts_code}]: {'暂无推荐' if not direction else direction}"
               f"\n要变更交易方向，请手动选择！")
    options = ["Rise", "Fall", "Sideways", "Cautious", "Ease"]

    # 不新建Tk，创建弹窗依附主窗口
    root = tk.Toplevel()
    root.title(title)
    root.attributes('-topmost', True)
    root.lift()
    root.resizable(False, False)
    root.attributes('-toolwindow', True)
    # 其余逻辑不变...
    root.wait_window() # 替换mainloop，阻塞等待弹窗关闭

def clean_old_trade_db(db_folder_path: str = None, dry_run: bool = True):
    """
    21点以后清理历史交易日数据库文件
    :param db_folder_path: db文件夹完整路径
    :param dry_run: True=仅打印待删除，不真实删除；False=执行真实删除
    :return: (keep_list, delete_list)
    """
    now = datetime.now()
    current_hour = now.hour
    db_folder_path = Path(get_data_cache_dir()) / "db"
    print(db_folder_path)
    # 只有21点及以后执行清理
    if current_hour < 21:
        print_context(f"程序会在交易日的21:00:00后清除旧数据！ 当前时间： {now.strftime('%H:%M:%S')}")
        return [], []

    today_str = now.strftime("%Y%m%d")
    next_day_str = (now + timedelta(days=1)).strftime("%Y%m%d")

    # 需要保留的db文件名（不带路径）
    keep_db_names = {f"{today_str}.db", f"{next_day_str}.db"}
    # 连带保留wal/shm
    keep_aux = set()
    for name in keep_db_names:
        base = os.path.splitext(name)[0]
        keep_aux.add(f"{base}.db‑wal")
        keep_aux.add(f"{base}.db‑shm")

    keep_all = keep_db_names.union(keep_aux)

    if not os.path.isdir(db_folder_path):
        print_context(f"目录不存在:{db_folder_path}")
        return [], []

    keep_list = []
    delete_list = []

    for fname in os.listdir(db_folder_path):
        full_path = os.path.join(db_folder_path, fname)
        if not os.path.isfile(full_path):
            continue
        # 只处理db、db‑wal、db‑shm后缀
        ext = os.path.splitext(fname)[1]
        if not (fname.endswith(".db") or fname.endswith(".db‑wal") or fname.endswith(".db‑shm")):
            continue

        if fname in keep_all:
            keep_list.append(fname)
        else:
            delete_list.append(full_path)

    print_context(f"【db清理】保留文件:{keep_list},待删除数量:{len(delete_list)}")

    # 执行删除
    for file_path in delete_list:
        try:
            if dry_run:
                print_context(f"[模拟删除] {os.path.basename(file_path)}")
            else:
                os.remove(file_path)
                print_context(f"✅已删除 {os.path.basename(file_path)}")
        except PermissionError:
            print_context(f"❌删除失败，文件被占用（sqlite连接未关闭）:{file_path}")
        except Exception as e:
            print_context(f"❌删除异常 {file_path} err:{str(e)}")
    return None



if __name__ == "__main__":
    # print_context(f"今天是：{datetime.now().strftime('%Y/%m/%d %H:%M:%S')},期货交易：{is_trade_period}")
    # print(default_futures)
    # get_direction()
    clean_old_trade_db()