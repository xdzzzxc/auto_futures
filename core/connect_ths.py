from datetime import datetime
from pywinauto import Application, mouse, findwindows
from time import sleep
from public.close_ad_window import close_ad_windows
import time
import random
import os
from pywinauto.controls.uiawrapper import UIAWrapper
from pywinauto.findwindows import ElementNotFoundError
# from pywinauto.timings import TimeoutError, wait_until
import psutil
from public.print_context import print_context
from public import shared_data
from public.shared_data import simulate_input, trade_flag, is_trade_status, set_lots, click_position, condition_control
from pywinauto import mouse
from typing import cast
import threading
from tools.set_cloud_bills import set_cloud_bills
from tools.cancel_trade import cancel_trade
from tools.play_alert import *

_ths_watchdog_ui_lock = threading.Lock()

ths_path = r"C:\同花顺期货通\bin\hexinlauncher.exe"

login_ctrl = {'期货户': (1663, 1019, 1697, 1035), '选择用户': (862, 502, 1045, 522),
              '模拟用户': (847, 538, 1077, 555), '国泰君安_CTP': (847, 563, 1047, 580),
              '期货密码': (862, 582, 1046, 602), '登录': (840, 647, 1080, 681),
              }
user_name_dict = {0: "模拟用户", 1: "期货用户"}
subwindow = None

ths_common_ctrls_dict = {'用户名': (18, 721, 155, 738, "模拟交易国泰君安"), '权益': (165, 719, 256, 739, "权益"),
                         '可用资金': (271, 719, 390, 739, ""), '商品锁': (287, 797, 303, 813, ""),
                         '期货代码': (214, 796, 286, 813, ""), '即时价格': (245, 836, 281, 853, ""),
                         '平仓': (458, 863, 490, 884, ""), '盈亏': (213, 923, 454, 962, ""),
                         '保证金': (213, 945, 426, 962, ""), '条件单': (272, 988, 311, 1007, ""),
                         '买多': (243, 863, 275, 884, ""), '卖空': (350, 863, 382, 884, ""),
                         '手数': (321, 793, 92, 24, "")}

exchange_ctrl_dict = {"上期所": (), "大商所": (), "郑商所": (), "上能源": (), "广期所": ()}

# 新增工具函数
# def get_foreground_hwnd():
#     return user32.GetForegroundWindow()
#
# def ensure_window_focus(hwnd, retry=3, delay=0.3) -> bool:
#     """
#     确保目标窗口为前台焦点窗口
#     :param hwnd: 窗口句柄
#     :param retry: 重试次数
#     :param delay: 每次重试等待
#     :return: True成功获取焦点 / False失败
#     """
#     for _ in range(retry):
#         if get_foreground_hwnd() == hwnd:
#             return True
#         user32.SetForegroundWindow(hwnd)
#         time.sleep(delay)
#     return False
def kill_ths_background_processes():
    """杀死同花顺残留 happ.exe / HDP.exe"""
    kill_list = {"happ.exe", "hdp.exe"}
    for p in psutil.process_iter(["name"]):
        try:
            p_name = p.info["name"].lower()
            if p_name in kill_list:
                print_context(f"🔪 发现同花顺残留进程: {p.info['name']} PID={p.pid}，准备终止")
                p.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    # 等待片刻，让进程退出
    sleep(0.8)
    # 强制兜底kill，如果terminate没杀掉
    for p in psutil.process_iter(["name"]):
        try:
            p_name = p.info["name"].lower()
            if p_name in kill_list:
                print_context(f"💥 强制杀死残留进程 {p.info['name']} PID={p.pid}")
                p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

def is_ths_process_exist() -> bool:
    """只识别主行情happ.exe，过滤hexinlauncher残留启动器"""
    for proc in psutil.process_iter(attrs=["name"]):
        name = proc.info.get("name", "")
        if name and name.lower() == "happ.exe":
            return True
    return False


def get_happ_pid():
    for proc in psutil.process_iter(attrs=["name", "pid"]):
        name = proc.info.get("name", "")
        if name and name.lower() == "happ.exe":
            return proc.info["pid"]
    return None


def is_win_valid(win) -> bool:
    """校验窗口有效性，失效清空全局缓存"""
    try:
        return win.exists(timeout=2)
    except Exception:
        shared_data.trade_window = None
        if hasattr(shared_data, "ths_common_control"):
            shared_data.ths_common_control = {}
        return False


def is_around(checked_value, target_value, error_range=4):
    return (target_value - error_range) <= checked_value <= (target_value + error_range)


def start_ths():
    """启动同花顺并自动完成全套登录，全程自动化无需人工操作"""
    try_counts = 0
    max_try_counts = 3
    Application(backend="uia").start(ths_path)
    print(f"已启动同花顺期货通，等待窗口加载 ------ [{datetime.now().strftime('%H:%M:%S')}]")
    sleep(5)
    while True:
        try_counts += 1
        print(f"\r第{try_counts}/{max_try_counts}次尝试连接窗口", flush=True, end="")
        if try_counts > max_try_counts:
            raise RuntimeError(f"连接同花顺窗口超时，已重试{max_try_counts}次，请检查程序是否正常启动")
        try:
            app = Application(backend="uia").connect(title_re=r".*同花顺期货通.*", timeout=10)
            ths_window = app.window(title_re=r".*同花顺期货通.*", control_type="Window")
            if ths_window.exists(timeout=10):
                shared_data.trade_window = ths_window
                ths_window.maximize()
                ths_window.set_focus()
                print(
                    f"\r第{try_counts}/{max_try_counts}次尝试连接窗口 - 连接成功 [{datetime.now().strftime('%H:%M:%S')}]\n")
                break
        except Exception as e:
            print(f"窗口未就绪，等待重试，异常信息：{str(e)}")
        sleep(1)
    return ths_window


def auto_login(ths_window):
    """
    纯登录逻辑，接收已连接好的主窗口
    无内嵌login函数，所有登录操作平铺写在本函数内
    软件已启动时，直接调用此函数即可，无需重复启动exe
    """
    # global subwindow

    # 定位期货户按钮
    user_type_btn = ths_window.child_window(control_type='Button', title_re='期货户|期货用户')
    shared_data.login_control.clear()
    shared_data.login_control['期货户'] = [
        user_type_btn, user_type_btn.rectangle()]

    if not user_type_btn.is_enabled():
        restart_ths()
        ths_window = shared_data.trade_window
        ths_window.set_focus()
        ths_window.maximize()
        user_type_btn = ths_window.child_window(control_type='Button', title='期货户')
        shared_data.login_control.clear()
        shared_data.login_control['期货户'] = [user_type_btn, user_type_btn.rectangle()]

    # close_ad_windows()
    close_ad_windows()  # 功能更强大，替换close_ad_windows()
    # 唤起登录弹窗
    shared_data.login_control['期货户'][0].click_input()
    sleep(2)

    # 等待登录弹窗出现
    exist_flag = False
    max_wait = 15
    wait_cnt = 0
    # desktop = Desktop(backend="uia")
    subwindow = None
    while not exist_flag and wait_cnt < max_wait:
        close_ad_windows()  # 每次循环都要清理一下广告弹窗
        try:
            subwindow = ths_window.child_window(title="同花顺期货通交易", control_type="Window")
            # subwindow = desktop.window(title_re=r".*同花顺期货通交易.*", control_type="Window", timeout=1)
            if subwindow.exists(timeout=0):
                exist_flag = True
                break
        except Exception:
            pass
        wait_cnt += 1
        sleep(1)
    if not exist_flag:
        raise RuntimeError("等待【同花顺期货通交易】登录窗口超时，未检测到弹窗")
    shared_data.login_control['登录窗口'] = [subwindow, subwindow.rectangle()]

    # 获取输入框
    edit_ctrls = ths_window.descendants(control_type='Edit')
    shared_data.login_control['选择用户'] = [edit_ctrls[0], edit_ctrls[0].rectangle()]
    shared_data.login_control['期货密码'] = [edit_ctrls[2], edit_ctrls[2].rectangle()]

    # 展开账号下拉列表
    shared_data.login_control['选择用户'][0].click_input()
    sleep(random.uniform(0.5, 1))

    # 账号文本控件
    user_type = subwindow.descendants(control_type='Text')
    shared_data.login_control['模拟交易'] = [user_type[0], user_type[0].rectangle()]
    shared_data.login_control['国泰君安'] = [user_type[1], user_type[1].rectangle()]
    login_btn = subwindow.child_window(title='登录')
    shared_data.login_control['登录'] = [login_btn, login_btn.rectangle()]

    # 平铺登录操作，不再嵌套内部login函数
    subwindow.set_focus()
    if shared_data.user_type == 0:
        # 模拟账户
        sleep(random.uniform(0.2, 0.5))
        shared_data.login_control['模拟交易'][0].click_input()
        sleep(random.uniform(0.2, 0.5))
    else:
        # 实盘国泰君安
        sleep(random.uniform(0.2, 0.5))
        shared_data.login_control['国泰君安'][0].click_input()
        sleep(random.uniform(0.2, 0.5))
        shared_data.login_control['期货密码'][0].set_text(os.environ.get("trade_password"))
    # 点击登录
    shared_data.login_control['登录'][0].click_input()


def restart_ths():
    try:
        app = Application(backend="uia").connect(title_re=r".*同花顺期货通.*")
        app.kill()
    except Exception:
        pass
    # 新增：清理hexinlauncher残留进程
    for proc in psutil.process_iter(attrs=["name"]):
        name = proc.info.get("name", "")
        if name and name.lower() == "hexinlauncher.exe":
            try:
                proc.kill()
            except:
                pass
    print("正在准备重启同花顺期货通应用程序 ······")
    # 冷却，释放端口，解决ConnectRefused
    sleep(1)
    # 清空全局缓存
    shared_data.trade_window = None
    if hasattr(shared_data, "ths_common_control"):
        shared_data.ths_common_control = {}
    window = start_ths()
    auto_login(ths_window=window)
    local_control()


# 主入口 check_ths_status 修复逻辑+补充打印启动状态、登录用户名
def check_ths_status():
    status_type = {0: "未启动同花顺软件", 1: "未登录期货用户", 2: "模拟用户", 3: "期货用户（国泰君安）"}
    # proc_running = is_ths_process_exist()
    happ_pid = get_happ_pid()
    # 先打印基础状态，登录账户后置获取，避免临时窗口识别失败
    print_context(f"正在检查[同花顺期货通]运行状态：{status_type}")
    print_context(f"软件进程启动状态：{'已启动' if happ_pid else '未启动'}")

    # 分支1：无同花顺进程，自动启动+自动登录
    if not happ_pid:
        print_context("检测：无同花顺进程，自动启动并完成登录流程")
        window = start_ths()
        auto_login(ths_window=window)
        local_control()
        return 0
    # 当判断同花顺软件已启动后的操作：只启动软件未登录用户；启动软件登录了用户。
    if happ_pid:
        # app = Application(backend="uia").connect(title_re=r".*同花顺期货通.*", timeout=10)
        app = Application(backend="uia").connect(process=happ_pid, timeout=5)
        # ths_window = app.window(title_re=r".*同花顺期货通.*", control_type="Window")
        ths_window = app.window(control_type="Window", visible_only=False)
        close_ad_windows()  # 关闭弹窗确保启动顺利进行
        #  这里是防止系统残留同花顺期货通后台程序干扰而设置的启动逻辑
        try:
            ths_window.set_focus()
            ths_window.maximize()
        except Exception:
            print("程序检测到系统后台还残留了同花顺期货通后台进程，正在将其销毁再重新启动同花顺期货通应用程序！")
            kill_ths_background_processes()
            start_ths()
            sleep(4)
            ths_window = app.window(control_type="Window")
            ths_window.wait("visible", timeout=5)
            shared_data.trade_window = ths_window
            ths_window.set_focus()
            ths_window.maximize()
        qhh_btn = ths_window.child_window(control_type='Button', title_re='期货户|期货用户')
        qhh_btn_enabled = qhh_btn.is_enabled()
        if qhh_btn_enabled:
            print(f"同花顺期货交易软件已正常启动，等待用户登录 ........ \n")
            auto_login(ths_window=ths_window)
            local_control()
            return 1
        if not qhh_btn_enabled:
            user_type = 0
            user_ctrl = ths_window.child_window(control_type="Button", title_re=r"模拟交易.*|国泰君安.*")
            user_ctrl_text = user_ctrl.window_text()
            if user_ctrl_text.startswith("国泰"):
                user_type = 1
            if user_type == shared_data.user_type:
                print_context(f"connect_ths.check_ths_status:已登录用户：{'模拟用户' if user_type==0 else '期货用户'}\n")
                local_control()
                return f"指定用户已登录：{'模拟用户' if user_type==0 else '期货用户'}！"
            else:
                print_context(f"正在重启同花顺期货通交易软件并切换用户：{'模拟用户' if user_type==0 else '期货用户'}\n")
                restart_ths()
                return f"正在重启并切换用户：{'模拟用户' if user_type==0 else '期货用户'}"


def local_control():
    missing_ctrls = 0  # 用来在定位完控件后统计检测未定位到的控件数量
    try_max = 10
    try_count = 0
    local_control_count = len(ths_common_ctrls_dict)
    ths_window = None
    none_count = 0
    ctrl_mapping = {}
    for key in ths_common_ctrls_dict.keys():
        ctrl_mapping[key] = None

    if not shared_data.trade_window or not is_win_valid(shared_data.trade_window):
        from pywinauto import Application, findwindows
        # 枚举所有匹配标题的UIA顶层元素
        elem_list = findwindows.find_elements(title_re=r".*同花顺期货通.*", backend="uia")
        # 过滤Chromium附属渲染窗口Chrome_WidgetWin_1
        real_elems = [e for e in elem_list if e.class_name != "Chrome_WidgetWin_1"]
        if len(real_elems) == 0:
            raise RuntimeError("找不到同花顺主窗口，请确认软件已打开")
        if len(real_elems) > 1:
            raise RuntimeError("仍然存在多个主窗口，无法选择")
        # 使用窗口句柄连接，不再使用title_re，消除二义性
        main_handle = real_elems[0].handle
        app = Application(backend="uia").connect(handle=main_handle, timeout=3)
        ths_window = app.window(handle=main_handle)
        ths_window.wait('visible', timeout=2)
        shared_data.trade_window = ths_window
        ths_window.set_focus()
        ths_window.maximize()
        print_context(">>> 主窗口句柄连接成功，预留2s等待Chromium UIA树稳定")
        time.sleep(2.0)
    else:
        ths_window = shared_data.trade_window

    while try_count < try_max:
        # ========== 嵌入耗时统计 ==========
        scan_start = time.perf_counter()
        all_ctrls = ths_window.descendants()
        # 手动过滤可见控件（替代不存在的visible_only参数）
        all_ctrls = [c for c in all_ctrls if c.is_visible]
        scan_end = time.perf_counter()
        scan_cost = scan_end - scan_start
        print_context(f"> [扫描轮次{try_count+1}] descendants遍历耗时:{scan_cost:.3f}s, 读取控件总数:{len(all_ctrls)}")
        # ==================================

        for num, ctrl in enumerate(all_ctrls):
            try:
                rect = ctrl.rectangle()
                win_txt = ctrl.window_text()
                l, t, r, b = rect.left, rect.top, rect.right, rect.bottom
                rect_tuple = (l, t, r, b)
                if is_around(ths_common_ctrls_dict["条件单"][0], l) and is_around(ths_common_ctrls_dict["条件单"][1], t):
                    if ctrl_mapping['条件单'] is None:
                        ctrl_mapping['条件单'] = [ctrl, rect_tuple, win_txt]
                if is_around(ths_common_ctrls_dict["手数"][0], l) and is_around(ths_common_ctrls_dict["手数"][1], t):
                    if ctrl_mapping['手数'] is None:
                        ctrl_mapping['手数'] = [ctrl, rect_tuple, win_txt]
                if all(key in win_txt for key in ["保证金", "每手"]):
                    if ctrl_mapping['保证金'] is None:
                        ctrl_mapping['保证金'] = [ctrl, rect_tuple, win_txt]
                if is_around(ths_common_ctrls_dict["平仓"][0], l) and is_around(ths_common_ctrls_dict["平仓"][1], t):
                    if ctrl_mapping['平仓'] is None:
                        ctrl_mapping['平仓'] = [ctrl, rect_tuple, win_txt]
                if any(key in win_txt for key in ["模拟交易", "国泰君安"]):
                    if ctrl_mapping['用户名'] is None:
                        ctrl_mapping['用户名'] = [ctrl, rect_tuple, win_txt]
                if "权益" in win_txt:
                    if ctrl_mapping['权益'] is None:
                        ctrl_mapping['权益'] = [ctrl, rect_tuple, win_txt]
                if "可用资金" in win_txt:
                    if ctrl_mapping['可用资金'] is None:
                        ctrl_mapping['可用资金'] = [ctrl, rect_tuple, win_txt]
                if is_around(ths_common_ctrls_dict["买多"][0], l) and is_around(ths_common_ctrls_dict["买多"][1], t):
                    if ctrl_mapping['买多'] is None:
                        ctrl_mapping['买多'] = [ctrl, rect_tuple, win_txt]
                if is_around(ths_common_ctrls_dict["卖空"][0], l) and is_around(ths_common_ctrls_dict["卖空"][1], t):
                    if ctrl_mapping['卖空'] is None:
                        ctrl_mapping['卖空'] = [ctrl, rect_tuple, win_txt]
                if is_around(ths_common_ctrls_dict["商品锁"][0], l) and is_around(ths_common_ctrls_dict["商品锁"][1], t):
                    if ctrl_mapping['商品锁'] is None:
                        ctrl_mapping['商品锁'] = [ctrl, rect_tuple, win_txt]
                if is_around(ths_common_ctrls_dict["盈亏"][0], l) and is_around(ths_common_ctrls_dict["盈亏"][1], t):
                    if ctrl_mapping['盈亏'] is None:
                        ctrl_mapping['盈亏'] = [ctrl, rect_tuple, win_txt]
                if is_around(ths_common_ctrls_dict["期货代码"][0], l) and is_around(ths_common_ctrls_dict["期货代码"][1], t):
                    if ctrl_mapping['期货代码'] is None:
                        child_edits = ctrl.children(control_type="Edit")
                        if len(child_edits) > 0:
                            real_edit = child_edits[0]
                            ctrl_mapping['期货代码'] = [real_edit, rect_tuple, real_edit.window_text()]
                if is_around(ths_common_ctrls_dict["即时价格"][0], l, error_range=15) and is_around(ths_common_ctrls_dict["即时价格"][1], t):
                    if ctrl_mapping['即时价格'] is None:
                        ctrl_mapping['即时价格'] = [ctrl, rect_tuple, win_txt]
            except Exception:
                continue

        none_count = sum(1 for v in ctrl_mapping.values() if v is None)
        if none_count == 0:
            print_context(f"\r >>>>>>>>>>>> 已准确定位到全部所需控件[{local_control_count}] <<<<<<<<<<<<")
            # 需求3：打印全部控件key列表
            ctrl_key_list = list(ctrl_mapping.keys())
            # print(f"全部控件名称列表：{ctrl_key_list}")
            break
        else:
            pass
        print_context(f"\r正在定位应用所需的控件：{local_control_count - none_count} - {[k for k, v in ctrl_mapping.items() if v is not None]}")
        try_count += 1
        sleep(0.3)
    # ============新增：单独定位【持仓】tab控件，不依赖坐标============
    ctrl_mapping['持仓'] = None
    ctrl_mapping['撤单'] = None
    try:
        # 移除固定control_type="Text"，兼容Button/Text两种类型
        pos_ctrl = ths_window.child_window(title="持仓")
        if pos_ctrl.exists(timeout=1):
            # pos_ctrl.click_input()
            rect_tuple = (pos_ctrl.rectangle().left, pos_ctrl.rectangle().top,
                          pos_ctrl.rectangle().right,
                          pos_ctrl.rectangle().bottom)
            win_txt = pos_ctrl.window_text()
            # 和其他控件格式对齐：[ctrl对象,坐标元组,文本]
            ctrl_mapping["持仓"] = [pos_ctrl, rect_tuple, win_txt]
    except Exception:
        print_context(f"本次启动同花顺交易软件时尚未定位到[持仓]控件！")
    missing_ctrls = [k for k, v in ctrl_mapping.items() if v is None]
    none_count = len(missing_ctrls)
    if none_count > 0:
        print_context(f"未定位到[撤单]控件，后续程序需要时会补定位！ 缺失控件列表[共缺失{none_count}个]:{missing_ctrls}")
        # exit(0)
    shared_data.ths_common_control = ctrl_mapping

    # 在期货代码框输入交易品种代码并锁定
    code_ctrl = shared_data.ths_common_control['期货代码'][0]
    lock_ctrl = shared_data.ths_common_control["商品锁"][0]
    window = UIAWrapper(shared_data.trade_window.element_info)
    ts_code = shared_data.ts_code or "m2609"

    # 将拟交易的期货品种代码输入到期货代码控件内，同时运用锁控件锁定该期货代码控件以防误操作导致读取的即时价格错乱。
    UI_CLICK_DELAY = 0.3  # 设定UI操作的时间间隔
    current_code = code_ctrl.window_text().strip()

    if current_code == ts_code:
        # 代码一致，检查是否锁定
        if code_ctrl.is_enabled():
            # 可编辑=未锁定，点击锁定
            lock_ctrl.click_input()
            sleep(UI_CLICK_DELAY)
            print_context(f"品种代码已是{ts_code}，已执行锁定操作")
        # else:
        #     print_context(f"品种代码已是{ts_code}，已锁定，无需操作")
    else:
        # 代码不一致，需要修改代码
        if not code_ctrl.is_enabled():
            # 当前锁定，先解锁
            lock_ctrl.click_input()
            sleep(UI_CLICK_DELAY)
        # 此时已经解锁可编辑，输入代码
        simulate_input(ctrl=code_ctrl, window=window, value=ts_code)
        sleep(UI_CLICK_DELAY)
        # 输入完成，锁定
        lock_ctrl.click_input()
        sleep(UI_CLICK_DELAY)
        # 校验输入结果，防止输入失败
        after_code = code_ctrl.window_text().strip()
        if after_code != ts_code:
            raise Exception(f"品种代码输入校验失败，预期:{ts_code},实际:{after_code}")
        print_context(f"您拟将交易的期货品种代码是：{ts_code}，程序已将其锁定，请在开盘或开市后再次确认！")
    # 设置期货品种的交易手数
    set_lots()



def set_loss_profit(param: dict = None):
    """
    设置云止损止盈保本单；内部函数封装单条设置逻辑，每条完整重新打开弹窗
    """
    set_mapping = {"云止损单": 0, "云止盈单": 1, "云保本单": 2}
    if param is None:
        param = shared_data.loss_profit_param.copy()

    fut_code = shared_data.ts_code or "m2701"

    # 1. 先过滤出真正需要设置的项
    todo_list = []
    for drill_type, price in param.items():
        if price > 0:
            todo_list.append((drill_type, price))
        else:
            print(f"跳过[{fut_code} {drill_type}] 设置！")
    if not todo_list:
        print(f"[{fut_code}] 没有需要设置的云止损/止盈参数，直接返回")
        return

    # -------- 连接窗口 --------
    ths_window = None
    app = None
    if shared_data.trade_window is not None:
        ths_window = shared_data.trade_window
        app = ths_window.app
    else:
        ths_pid = get_happ_pid()
        app = Application(backend="uia").connect(process=ths_pid, timeout=10)
        ths_window = app.top_window()
    ths_window.set_focus()
    ths_window.maximize()
    area_left, area_top, area_w, area_h = 680, 794, 48, 17
    area_right = area_left + area_w
    area_bottom = area_top + area_h
    # 开始设置云止损止盈保本单
    wait_total_sec = 60
    start_time = time.time()
    target_ctrl = None
    found = False
    # 这里必须先点击"持仓"控件，确保进入持仓面版才可以定位含有期货品种代码的控件
    click_position(rect_tuple=(534, 747, 574, 766))
    print_context(f"[{fut_code}] 开始等待成交确认控件，区域({area_left},{area_top})，最长等待{wait_total_sec}s...")
    while time.time() - start_time < wait_total_sec:
        try:
            # 获取窗口所有后代控件
            all_ctrls = ths_window.descendants()
            for ctrl in all_ctrls:
                try:
                    rect = ctrl.rectangle()
                    # 判断控件是否落在目标矩形框内
                    ctrl_in_area = (
                            area_left <= rect.left <= area_right
                            and area_top <= rect.top <= area_bottom
                    )
                    if not ctrl_in_area:
                        continue
                    # 获取控件文本，转小写匹配合约
                    ctrl_text = ctrl.window_text().strip().lower()
                    if fut_code.lower() in ctrl_text:
                        target_ctrl = ctrl
                        found = True
                        break
                except Exception:
                    # 部分控件无法读取rect/window_text，直接跳过
                    continue
            if found:
                break
        except Exception as e:
            print_context(f"检索控件异常: {str(e)}")

        # 轮询间隔，不要爆循环，0.8s一次足够，降低CPU
        time.sleep(0.8)

    if not found or target_ctrl is None:
        sound_warn()  # 警告音
        cancel_trade()  # 撤单：在60秒延时未达成交易则程序自动撤单
        print_context(f"[{fut_code}] 等待成交确认控件超时{wait_total_sec}s，未找到合约控件，放弃本次云止损止盈设置！")
        # 在try--except中进行撤单操作
        return
    print_context(f"[{fut_code}] ✅ 成功定位成交确认控件，文本：{target_ctrl.window_text()}，继续设置云止损止盈")
    # 云设置
    print(todo_list)
    for item in todo_list:
        set_cloud_bills(cloud_type=set_mapping[item[0]], set_value=item[1])
        print_context(f"成功设置[{shared_data.ts_code}] {item[0]}: {item[1]}")
    

# 检查同花顺应用程序是否会在休市时段断线退出用户登录
def ths_watchdog():
    """看门狗线程任务：无限循环轮询检测掉线，掉线自动重连（和项目锁范式对齐 with ctrl_rlock）"""
    lose_count = 0
    lose_threshold = 3   # 连续3轮判定掉线才触发重连防抖
    interval = 3.0
    while True:
        try:
            happ_pid = get_happ_pid()
            if not happ_pid:
                lose_count += 1
                print_context(f"[ths_watchdog] 未检测happ进程，计数 {lose_count}/{lose_threshold}")
                if lose_count >= lose_threshold:
                    print_context("[ths_watchdog] 持续丢失happ进程，执行重启同花顺")
                    with shared_data.ctrl_rlock:
                        restart_ths()
                        lose_count = 0
                time.sleep(interval)
                continue

            login_ok = False
            # ========== 状态检测本身也是UIA操作，必须上锁 ==========
            with shared_data.ctrl_rlock:
                app = Application(backend="uia").connect(process=happ_pid, timeout=5)
                ths_window = app.window(control_type="Window", visible_only=False, found_index=0)
                close_ad_windows()
                qhh_btn = ths_window.child_window(control_type="Button", title_re="期货户")
                login_ok = not qhh_btn.is_enabled()

            if not login_ok:
                lose_count += 1
                print_context(f"[ths_watchdog] 检测到登录掉线，计数 {lose_count}/{lose_threshold}")
                if lose_count >= lose_threshold:
                    print_context("[ths_watchdog] 持续掉线，执行自动重连")
                    with shared_data.ctrl_rlock:
                        ths_window.set_focus()
                        ths_window.maximize()
                        auto_login(ths_window=ths_window)
                        local_control()
                        lose_count = 0
                        print_context("✅重连成功，控件表已刷新")
            else:
                lose_count = 0

            time.sleep(interval)
        except Exception as e:
            print_context(f"[ths_watchdog] 全局捕获异常: {repr(e)}")
            time.sleep(interval)


if __name__ == '__main__':
    # check_ths_status()
    # local_control()
    set_loss_profit()
    # ths_watchdog()
    pass
