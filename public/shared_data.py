import threading
from time import sleep
import random
from collections import deque
from datetime import datetime, time
import pyperclip
from pywinauto import mouse
from chinese_calendar import is_holiday  # 纯本地节假日库，一次安装永久用
from public.print_context import print_context
import os
from pathlib import Path
from datetime import timedelta
import logging
import time
import psutil
from pywinauto import Application

# 创建类型重入锁
deque_lock = threading.Lock()
variables_rlock = threading.RLock()
ctrl_rlock = threading.RLock()
db_rlock = threading.RLock()
dict_rlock = threading.RLock()

user_type = 0  # 0-模拟用户  1-国泰君安期货用户
user_name = {0: "模拟交易-1811889418", 1: "国泰君安_CTP85415809"}  # 模拟交易-1811889418 国泰君安_CTP85415809
trade_window = None  # 同花顺交易平台桌面对象
# 打印限制设置（1次）
print_on_off = True
# 设置有效的交易时间间隔
valid_trade_interval = 5  # 默认5分钟后允许继续交易（单位：分）

start_time_of_session = None  #
valid_time = None  # 通过上面参数和具体交易时间决定下一次的交易时间,默认是成功启动并登录用户后的时刻

market_ctx_dict = {}  # cfg_pool.yaml文件读写上下文命名空间

# 期货品种即时行情价格缓冲区及相关安全配置
get_price_interval = 2  # 从同花顺窗口读取即时价格的时间间隔，默认为2秒
k_minutes = 3  # 设置指定时长的最后一根K线的时间
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

ui_busy: bool = False
# sideways_product_list = {"m", "c", "jd"}

# __________________________________________________
login_control = {}  # 登录期货通交易软件
ths_common_control = {}  # 交易平台常用控件字典,此处为多进程管理模式，以便进程数据共享
condition_control = {}  # 条件单窗口控件映射字典
logger: logging.Logger | None = None  # 根据用户选择的日志器
quote_list = {"m2701", "c2701"}  # 默认要从东方财富网获取开盘价等信息的期货品种
ts_code = "m2701"  # 期货商品代码（如au2601)通过人工手动选择后作为本次交易主体品种
default_tscode = "m2701"  # 当在无人进入期货交易时，自动选择该期货品种作为当日的交易品种
# search_future_list = []  # 待搜索的期货商品代码列表
open_price = {}  # 交易品种开盘价信息：trade.order()
pre_profit = 80  # 手动设置固定止盈值
pre_loss = 0  # 手动设置固定止损值
hold_value = 0  # 手动设置云保本值（取价差值）
target_days = 15  # 从tu_share获取ts_code历史行情数据（天数）
lot_size = 1  # 期货买卖手数，默认值1，不同商品规定必须最少多少手
tscode_lots_dict = {}  # 常用交易期货品种的手数设置
default_lots_dict = {"m": 1, "c": 1, "ma": 1, "jd": 1}  #
direction_dict = {}  # 期货品种大盘走势字典，品种来源于：quote_list = {"m2611", "c2611", "jd2611"}
direction = direction_dict.get(ts_code, "sideways")  # 如果有专业推荐，直接写买多-Rise、卖空-Fall，否则由历史数据与今日开盘价来确定多空方向

history_trade_df = None  # 期货品种历史交易原始数据，dataframe格式；
history_data_analysis = None  # 期货商品历史交易数据，来源于future_data模块
loss_profit_param = {"云止损单": 0, "云止盈单": 0, "云保本单": 0}  # 对应止损止盈设置
future_quote_dict = {}  # 期货行情 https://push2.eastmoney.com/api/qt/ulist.np/get
future_info_dict = {}  # 期货资讯行情
# "交易方向", "交易价", "止损价", "止盈价", "交易前总额", "交易后总额", "利润"
trade_menu_dict = {}  # 成交后的交易参数,在trade.py模块中产生
ts_code_attribute_dict = {}  # 交易品种的基本属性
BIN_NUM = 8  # 配置参数：箱体数量，日内短线推荐8个等宽箱体
# 项目线程列表
thread_list: list[threading.Thread] = []
total_balance = 0.0  # 账户总金额
available_balance = 0.0  # 账户可用资金
# 夜盘开盘价重取触发标记，key=ts_code，value=bool
night_trigger_done: dict[str, bool] = {}
# 全局停止标记，所有交易线程都监听这个
stop_flag: bool = False

set_lots_flag = True  # 切换合约时修改手数标记
trade_time_table = [(9, 0, 10, 15), (10, 30, 11, 30), (13, 30, 15, 0), (21, 0, 23, 0)]  # 交易时间表, 最后一个用测试。
start_trade_date = None  # 期货开始交易时间（下单日期）

# ===================== 核心函数 =====================
def get_direction():
    with variables_rlock:
        return direction_dict.get(ts_code, "sideways")

def print_thread_status():
    """
    线程看门狗巡检（放在shared_data.py内）
    全部线程存活：无任何输出
    检测到线程退出：打印名称+时间，并声音告警
    ⚠️ 无告警标记：每次巡检扫到死亡线程都会响警报
    """

    try:
        new_thread_list = thread_list
        has_dead = False

        for t in new_thread_list:
            if not isinstance(t, threading.Thread):
                has_dead = True
                print_context(f"⚠️ 无效对象，非线程实例：{t}")
                continue

            if not t.is_alive():
                has_dead = True
                tn = t.name
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # 仅触发告警那一刻才导入audio，规避循环导入
                from audio.play_alert import sound_warning_nonblock
                print_context(f"🚨 告警：线程【{tn}】已退出！检测时间：{now_str}")
                sound_warning_nonblock()

        if not has_dead:
            return

    except Exception as e:
        print_context(f"❌ print_thread_status 打印异常: {repr(e)}")

def is_cooling() -> bool:
    """返回 True = 处于冷却期，禁止开仓；False = 冷却结束，可以开仓"""
    with variables_rlock:
        cooling_time = valid_time
    if cooling_time is None:
        return False

    now = datetime.now()
    now_str = now.strftime("%H:%M:%S")
    cooling_str = cooling_time.strftime("%H:%M:%S")

    if now < cooling_time:
        print(f"\r[冷却] 当前:{now_str},冷却截止:{cooling_str},冷却中=True", flush=True, end="")
        return True
    else:
        print(f"\r[冷却] 当前:{now_str},冷却截止:{cooling_str},冷却结束=False ✅冷却放行", flush=True, end="")
        return False

def is_trade_status() -> bool:
    """判断是否持仓或是否在交易状态中：权益!= 可用资金 → 有持仓、交易中、返回 True
    返回：True = 有持仓 / False = 无持仓
    """
    global print_on_off, pre_profit, pre_loss, trade_menu_dict, ts_code, direction
    valid_chars = {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", ".", "-"}
    has_pos = False
    try:
        with ctrl_rlock:
            equity_ctrl = ths_common_control["权益"][0]
            available_ctrl = ths_common_control["可用资金"][0]
            equity_text = equity_ctrl.window_text().strip()
            available_text = available_ctrl.window_text().strip()

        # 提取数字
        def get_num(text):
            s = "".join(c for c in text if c in valid_chars)
            return float(s) if s else 0.0

        equity = get_num(equity_text)
        available = get_num(available_text)
        if print_on_off:
            print_context(f" 权益：{equity} 可用资金：{available} 固定止盈值：{pre_profit} 元 固定止损值：{pre_loss} 元 ")
            print_on_off = False
        # 差异 > 1 元判定为有持仓
        has_pos = abs(equity - available) > 1.0

        # ============如果有持仓，止损止盈值均为0且trade_menu_dict={}============
        if has_pos and not trade_menu_dict:
            try:
                # 读取UI控件，ths_lock保护
                with ctrl_rlock:
                    profit_loss_ctrl = ths_common_control["盈亏"][0]
                    ts_code_text = ths_common_control["期货代码"][0].window_text().strip()
                    profit_text = profit_loss_ctrl.window_text().strip()

                # 判断多空，赋值给全局direction
                if "手多仓" in profit_text:
                    direction = "rise"
                else:
                    direction = "fall"
                # 更新全局ts_code
                ts_code = ts_code_text

                # 局部参数
                loc_pre_profit = 200
                loc_pre_loss = 0

                # 进入dict_rlock，更新全局共享字典
                with dict_rlock:
                    if pre_profit == 0 and pre_loss == 0:
                        pre_profit = loc_pre_profit
                        pre_loss = loc_pre_loss
                    # 重建trade_menu_dict
                    trade_menu_dict = {
                        "ts_code": ts_code,
                        "pre_profit": pre_profit,
                        "pre_loss": pre_loss,
                        "trade_direction": direction,
                        "rule_id": "unknow",
                        "trade_time": "老仓",
                        "trade_period": "unknow"
                    }
                print_context(f"[老仓自动重建trade_menu_dict成功] direction={direction}, ts_code={ts_code}")

            except Exception as e:
                # UI读取失败兜底
                with dict_rlock:
                    trade_menu_dict = {
                        "ts_code": "",
                        "pre_profit": 200,
                        "pre_loss": 0,
                        "trade_direction": "",
                        "rule_id": "unknow",
                        "trade_time": "老仓(读取UI失败)",
                        "trade_period": "unknow"
                    }
    except Exception as e:
        print_context(f"is_trade_status读取UI异常，判定无持仓：{str(e)}")
        has_pos = False
    # 【关键修复】无论走哪个分支，统一返回has_pos
    return has_pos

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

def click_position(rect_tuple, settle_wait: float = 0.2, post_click_wait: float = 0.15, stable_threshold: int = 2, max_wait_timeout: float = 3.0):
    """
    点击矩形控件中心，内置：等待鼠标稳定 + 移动 + 分段按下抬起 + 超时保护
    :param rect_tuple: (left, top, right, bottom)
    :param settle_wait: 需要持续稳定的时长，人鼠标静止这么久才执行点击
    :param post_click_wait: 点击完成后等待UI响应时间
    :param stable_threshold: 像素阈值，鼠标移动超过该像素视为在操作
    :param max_wait_timeout: 最长等待超时，超过则抛TimeoutError，防止永久卡死
    """
    import time
    def get_cursor_pos():
        return mouse.win32api.GetCursorPos()

    l, t, r, b = rect_tuple
    # 校验：right必须大于left，bottom大于top，捕获非法矩形
    if not (r > l and b > t):
        raise ValueError(f"非法矩形 {rect_tuple}，left/top/right/bottom 必须满足 right>left、bottom>top")

    target_x = l + (r - l) // 2
    target_y = t + (b - t) // 2

    # 等待鼠标稳定，带总超时
    total_start = time.time()
    stable_start = time.time()
    last_x, last_y = get_cursor_pos()

    while True:
        if time.time() - total_start > max_wait_timeout:
            raise TimeoutError(
                f"click_position:等待鼠标稳定超时{max_wait_timeout}s，检测到人为持续操作鼠标，放弃点击。目标坐标({target_x},{target_y})"
            )

        curr_x, curr_y = get_cursor_pos()
        if abs(curr_x - last_x) > stable_threshold or abs(curr_y - last_y) > stable_threshold:
            stable_start = time.time()
            last_x, last_y = curr_x, curr_y

        if time.time() - stable_start >= settle_wait:
            break
        time.sleep(0.02)

    # pywinauto移动鼠标到目标位置
    mouse.move(coords=(target_x, target_y))
    time.sleep(0.05)

    # 再次确认鼠标到达目标并稳定一小段
    stable_start = time.time()
    last_x, last_y = get_cursor_pos()
    while time.time() - stable_start < 0.1:
        cx, cy = get_cursor_pos()
        if abs(cx - last_x) > stable_threshold or abs(cy - last_y) > stable_threshold:
            stable_start = time.time()
            last_x, last_y = cx, cy
        time.sleep(0.02)

    # 如果多线程会并发调用鼠标操作，仅在这里包裹 ctrl_lock，只保护点击动作
    # with ctrl_lock:
    mouse.press(button="left", coords=(target_x, target_y))
    time.sleep(0.04)
    mouse.release(button="left", coords=(target_x, target_y))

    # 等待UI消化点击事件
    time.sleep(post_click_wait)
    return True

def click_control(text, click_btn=None, control_type="Text",
                  top_min=700, top_max=950, left_min=200, left_max=700):
    """
    通用控件查找并点击函数：主要专用于撤单操作和云设置条件单的操作
    :param text: 控件可见文本（window_text 精确匹配）
    :param click_btn: 鼠标按键：0=左键，2=右键
    :param control_type: 控件类型，默认 "Text"，可选 "Button" / "MenuItem"/"Static"
    :param top_min/top_max: 控件 top 坐标范围过滤
    :param left_min/left_max: 控件 left 坐标范围过滤
    :return: 成功返回 (ctrl, rect)；失败返回 (None, None)
    """
    from time import sleep
    # ========== 内部局部函数1：查找进程pid ==========
    def get_ths_pid():
        for proc in psutil.process_iter(attrs=["name", "pid"]):
            name = proc.info.get("name", "")
            if name and name.lower() == "happ.exe":
                return proc.info["pid"]
        return None

    # ========== 内部局部函数2：连接窗口 ==========
    def connect_ths_window(retry=3, interval=0.5):
        pid = get_ths_pid()
        if pid is None:
            print_context("❌未找到 happ.exe 进程")
            return None
        for attempt in range(retry):
            try:
                app = Application(backend="uia").connect(process=pid, timeout=5)
                all_tops = app.windows()
                if not all_tops:
                    time.sleep(interval)
                    continue
                win = all_tops[0]
                if win.is_visible():
                    return win
            except Exception as e:
                print_context(f"第{attempt+1}次连接异常: {repr(e)}")
            time.sleep(interval)
        print_context("❌连接同花顺窗口失败")
        return None

    # ========== 内部局部函数3：查找控件 ==========
    def find_ctrl(ths_win, ctype, txt, t_min, t_max, l_min, l_max):
        try:
            all_ctrls = ths_win.descendants(control_type=ctype)
        except Exception as e:
            print_context(f"descendants获取控件失败: {e}")
            return None, None

        for ctrl in all_ctrls:
            try:
                rect = ctrl.rectangle()
                win_txt = ctrl.window_text().strip()
                if win_txt != txt.strip():
                    continue
                if not (t_min <= rect.top <= t_max):
                    continue
                if not (l_min <= rect.left <= l_max):
                    continue
                return ctrl, rect
            except Exception:
                continue
        return None, None

    # ========== click_control 主逻辑 ==========
    ths_window = connect_ths_window()
    if ths_window is None:
        print_context("❌获取同花顺窗口失败")
        return None, None

    # 先最大化窗口 + 设置焦点
    ths_window.maximize()
    ths_window.set_focus()
    sleep(0.6)

    ctrl, rect = find_ctrl(ths_window, control_type, text,
                           top_min, top_max, left_min, left_max)
    if ctrl is None:
        print_context(f"❌未找到 [{control_type}] 文本为[{text}] 的控件")
        return None, None

    print_context(f"✅找到控件 [{control_type}] '{text}' rect={rect}")

    if click_btn == 0:
        ctrl.click_input()
        print_context(f"🖱️左键点击 [{text}] 完成")
    elif click_btn == 2:
        ctrl.click_input(button='right')
        print_context(f"🖱️右键点击 [{text}] 完成")
    else:
        print_context(f"⚠️click_btn={click_btn} 不支持，仅支持0=左键/2=右键")
    sleep(0.5)
    return ctrl, rect


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

def set_lots(window=None, fut_ctrl=None, fut_lots=1):
    # print_context(f"[调试1] set_lots被调用！当前品种ts_code={ts_code}")
    # print_context(f"[调试2] 手数字典当前全部内容={tscode_lots_dict}")

    window = trade_window
    fut_ctrl = ths_common_control["手数"][0]
    with dict_rlock:
        fut_lots = tscode_lots_dict.get(ts_code, default_lots_dict.get(ts_code[:-4], 1))
    print_context(f"set_lots被调用！当前品种ts_code:{ts_code} 本次计算出的目标手数={tscode_lots_dict}")
    if any([window is None, fut_ctrl is None]):
        fut_lots = 1
        print_context("设置交易手数不成功，使用默认值：1")
        return

    if 10 >= fut_lots > 1:
        simulate_input(ctrl=fut_ctrl, window=window, value=fut_lots)  # 模拟输入
        fut_ctrl.type_keys("{ENTER}")
        sleep(0.2)
        with dict_rlock:
            tscode_lots_dict.update({ts_code: fut_lots})


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
# def get_direction(title="交易方向", msg=None) -> str | None:
#     import tkinter as tk
#     default_dir = direction
#     if msg is None:
#         msg = (f"金投网推荐[{ts_code}]: {'暂无推荐' if not direction else direction}"
#                f"\n要变更交易方向，请手动选择！")
#     options = ["Rise", "Fall", "Sideways", "Cautious", "Ease"]
#
#     # 不新建Tk，创建弹窗依附主窗口
#     root = tk.Toplevel()
#     root.title(title)
#     root.attributes('-topmost', True)
#     root.lift()
#     root.resizable(False, False)
#     root.attributes('-toolwindow', True)
#     # 其余逻辑不变...
#     root.wait_window() # 替换mainloop，阻塞等待弹窗关闭

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
    # click_position(rect_tuple=(100,100,200,200))
    # print(is_trade_status())
    # click_control(text="锁仓", control_type="Text", click_btn=0)
    pass