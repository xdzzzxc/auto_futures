from pywinauto import Application, mouse
from time import sleep
import random
import os
import re
import psutil
import ctypes
import sys
import pywinauto.remote_memory_block
from public import shared_data

# ===================== 修补pywinauto底层，解决内存访问报错 =====================
original_init = pywinauto.remote_memory_block.RemoteMemoryBlock.__init__


def patched_init(self, element_info, size=4096):
    original_init(self, element_info, size)
    if self.mem_address is None:
        self.mem_address = 0


original_check_guard = pywinauto.remote_memory_block.RemoteMemoryBlock.CheckGuardSignature


def patched_check_guard(self):
    if self.mem_address is None:
        return
    original_check_guard(self)


pywinauto.remote_memory_block.RemoteMemoryBlock.__init__ = patched_init
pywinauto.remote_memory_block.RemoteMemoryBlock.CheckGuardSignature = patched_check_guard

# ===================== 导入逻辑 =====================

try:
    from .close_ad_window import close_ad_windows
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from close_ad_window import close_ad_windows

# ===================== 全局变量 =====================
ths_path = r"C:\同花顺期货通\bin\hexinlauncher.exe"
ctrl_rectangle_dict = {'品种': (214, 796, 286, 813), '手数一': (321, 793, 413, 817),
                       '即时价位': (242, 836, 277, 853), '条件单': (272, 988, 311, 1007),
                       '合约信息': (213, 945, 445, 962), '用户名': (18, 721, 168, 738),
                       '买入': (731, 441, 759, 461), '卖出': (803, 441, 831, 461),
                       '止损价': (954, 503, 1054, 527), '止盈价': (1156, 503, 1256, 527),
                       '确定开仓': (1147, 667, 1173, 686), '手数二': (1015, 439, 1115, 463),
                       '期货户': (1663, 1019, 1697, 1035), '用户类型': (862, 502, 1045, 522),
                       '模拟交易': (847, 538, 1077, 555), '期货用户': (847, 563, 1047, 580),
                       '期货密码': (862, 582, 1046, 602), '登录': (840, 647, 1080, 681),
                       '平仓': (458, 863, 490, 884), '条件单品种': (669, 341, 779, 360),
                       '条件单限价': (812, 412, 902, 436)}

user_name_dict = {0: "模拟交易-1811889418", 1: "期货用户-国泰君安_CTP-85415809"}
ctrl_mapping = {}


# ===================== 管理员权限检查 =====================
def check_admin():
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    except:
        is_admin = False
    if not is_admin:
        print("⚠️ 正在提权为管理员权限...")
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, __file__, None, 1)
        sys.exit(0)


# ===================== 核心：纯pywinauto窗口定位（无任何额外依赖） =====================
def get_ths_window_simple():
    """纯pywinauto定位，绕开所有系统API依赖"""
    # 步骤1：找同花顺进程PID
    ths_pids = []
    for proc in psutil.process_iter(['name', 'pid']):
        try:
            name = proc.info.get('name', '').lower()
            if 'happ' in name or 'hexinlauncher' in name:
                ths_pids.append(proc.info['pid'])
        except:
            continue

    # 步骤2：逐个PID尝试连接
    for pid in ths_pids:
        try:
            app = Application(backend="win32").connect(process=pid, timeout=8)
            # 遍历该进程下所有窗口，不判断visible，直接取第一个标题含同花顺的
            for win in app.windows():
                win_text = win.window_text().lower()
                if "同花顺" in win_text and "期货通" in win_text:
                    # 强制激活窗口（不检测状态）
                    win.set_focus()
                    win.maximize()
                    return win
        except:
            continue

    # 步骤3：终极兜底-直接启动并连接
    print("⚠️ 未找到现有窗口，尝试重新启动同花顺...")
    if os.path.exists(ths_path):
        app = Application(backend="win32").start(ths_path)
        sleep(20)
        # 启动后再次尝试连接
        for win in app.windows():
            win_text = win.window_text().lower()
            if "同花顺" in win_text and "期货通" in win_text:
                win.set_focus()
                win.maximize()
                return win

    return None


# ===================== 原有函数修复 =====================
def start_ths():
    print("📌 正在启动同花顺期货通...")
    if os.path.exists(ths_path):
        Application(backend="win32").start(ths_path)
        sleep(random.uniform(15, 20))
    else:
        print(f"❌ 同花顺路径不存在：{ths_path}")
        sys.exit(1)


def check_ths_status(keyword='happ'):
    flag = False
    print(f'程序正在检查[{keyword}]进程的运行新动态······')

    # 遍历进程
    for proc in psutil.process_iter(['name', 'pid', 'exe']):
        try:
            process_info = proc.info
            name = process_info.get('name', '')
            exe = process_info.get('exe', '')

            if (name and keyword in name) or (exe and keyword in exe):
                flag = True
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    print(f'进程[{keyword}]的检查结果：{"正在运行！" if flag else "未发现该进程！"}')
    return flag


def click_position(rect_tuple):
    """稳定的坐标点击（增加随机延迟，提高兼容性）"""
    x = rect_tuple[0] + (rect_tuple[2] - rect_tuple[0]) // 2
    y = rect_tuple[1] + (rect_tuple[3] - rect_tuple[1]) // 2
    # 移动鼠标到目标位置（增加随机延迟）
    mouse.move(coords=(x, y))
    sleep(random.uniform(0.3, 0.7))
    # 执行点击（双击兜底，防止单次点击无效）
    mouse.click(button='left', coords=(x, y))
    sleep(random.uniform(0.5, 1.0))


def run_ths():
    # 1. 检查管理员权限
    check_admin()

    # 2. 获取用户信息
    user_type = shared_data.user_type
    user_name = user_name_dict[user_type]

    # 3. 检查进程状态（仅日志，不影响后续操作）
    check_ths_status()

    # 4. 纯pywinauto获取窗口（核心修复：无任何系统API依赖）
    print("🔍 正在定位同花顺期货通窗口...")
    ths_window = get_ths_window_simple()
    if not ths_window:
        print("❌ 无法获取同花顺期货通窗口，请手动确认软件已启动！")
        sys.exit(1)
    print("✅ 窗口定位成功！")

    # 5. 强制窗口操作（不检测任何状态）
    try:
        ths_window.set_focus()
    except:
        print("⚠️ 窗口聚焦失败，继续执行后续操作...")
    try:
        ths_window.maximize()
    except:
        print("⚠️ 窗口最大化失败，继续执行后续操作...")
    sleep(3)  # 给窗口足够的响应时间

    # 6. 跳过控件检测，直接执行登录流程（全程坐标操作）
    print("🔑 执行登录流程（全程坐标操作）...")
    close_ad_windows()
    sleep(random.uniform(1.0, 2.0))

    # 步骤1：点击期货账户按钮
    click_position(ctrl_rectangle_dict['期货户'])
    sleep(random.uniform(1.5, 3.0))

    # 步骤2：选择用户类型
    click_position(ctrl_rectangle_dict['用户类型'])
    sleep(random.uniform(1.0, 2.0))
    click_position(ctrl_rectangle_dict[user_name[:4]])
    sleep(random.uniform(1.0, 2.0))

    # 步骤3：输入密码并登录
    if user_type == 1:
        # 期货用户：输入密码
        click_position(ctrl_rectangle_dict['期货密码'])
        sleep(random.uniform(2.0, 4.0))
        from pywinauto.keyboard import send_keys
        # 读取密码（优先环境变量，无则提示）
        trade_pwd = os.environ.get('trade_password')
        if not trade_pwd:
            print("⚠️ 未设置trade_password环境变量，请手动输入密码！")
            sleep(5)
        else:
            send_keys(trade_pwd)
            sleep(random.uniform(1.0, 2.0))
            send_keys('{ENTER}')
    else:
        # 模拟交易：直接点击登录
        click_position(ctrl_rectangle_dict['登录'])
        sleep(random.uniform(1.0, 2.0))

    # 7. 完成操作，保存窗口
    shared_data.trade_window = ths_window
    close_ad_windows()
    print(f'✅ [{user_name_dict[user_type]}] 登录流程执行完成！')


def local_ths_common_control():
    flag = check_ths_status()
    if not flag:
        print(f"程序没有加载同花顺期货软件，交易窗口未成功启动！\n窗口信息：{shared_data.trade_window}")
        sys.exit()

    text_controls = []
    try:
        trade_window = shared_data.trade_window
        # 仅遍历可见控件，跳过异常
        for ctrl in trade_window.children():
            try:
                if not ctrl.is_visible() or not ctrl.window_text():
                    continue
                if "权益" in ctrl.window_text():
                    text_controls.append(ctrl)
            except:
                continue
    except:
        pass

    sleep(2)
    for k, ctrl in enumerate(text_controls):
        print(f"{k}.{ctrl.window_text()}   {ctrl.rectangle()}")


# ===================== 主程序 =====================
if __name__ == '__main__':
    # 禁用pywinauto的所有日志（减少干扰）
    import logging
    logging.getLogger('pywinauto').setLevel(logging.ERROR)
    run_ths()
    local_ths_common_control()
