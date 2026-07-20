from datetime import datetime
from pywinauto import Application, mouse
from time import sleep
from public.anti_screensaver import kill_unprotected_process
import random
import os
from pywinauto.controls.uiawrapper import UIAWrapper
from pywinauto.findwindows import ElementNotFoundError
from pywinauto.timings import TimeoutError, wait_until
import psutil
from pywinauto import ElementAmbiguousError
from public.print_context import print_context
from public.close_ad_window import close_ad_windows
from public import shared_data
from public.shared_data import simulate_input
from pywinauto import Desktop, mouse

ths_path = r"C:\同花顺期货通\bin\hexinlauncher.exe"

login_ctrl = {'期货户': (1663, 1019, 1697, 1035), '选择用户': (862, 502, 1045, 522),
              '模拟用户': (847, 538, 1077, 555), '国泰君安_CTP': (847, 563, 1047, 580),
              '期货密码': (862, 582, 1046, 602), '登录': (840, 647, 1080, 681),
              }
user_name_dict = {0: "模拟用户", 1: "期货用户"}
subwindow = None

ths_common_ctrls_dict = {'用户名': (18, 721, 155, 738), '权益': (165, 719, 256, 739),
                         '可用资金': (271, 719, 390, 739), '商品锁': (287, 797, 303, 813),
                         '期货代码': (214, 796, 286, 813), '即时价格': (245, 836, 281, 853),
                         '平仓': (458, 863, 490, 884), '盈亏': (213, 923, 454, 962),
                         '保证金': (213, 945, 426, 962), '条件单': (272, 988, 311, 1007),
                         '买多': (243, 863, 275, 884), '卖空': (350, 863, 382, 884)}

# 新增工具函数
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
        return win.exists(timeout=0.3)
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

    close_ad_windows()
    # 唤起登录弹窗
    shared_data.login_control['期货户'][0].click_input()
    sleep(2)

    # 等待登录弹窗出现
    exist_flag = False
    max_wait = 15
    wait_cnt = 0
    desktop = Desktop(backend="uia")
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
    print("正在准备重启同花顺期货通应用程序 ······")
    # 新增冷却，释放10612残留端口，解决ConnectRefused
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


def click_position(rect_tuple):
    x = rect_tuple[0] + (rect_tuple[2] - rect_tuple[0])//2
    y = rect_tuple[1] + (rect_tuple[3] - rect_tuple[1])//2
    return mouse.click(button='left', coords=(x, y))

def local_control():
    missing_ctrls = 0  # 用来在定位完控件后统计检测未定位到的控件数量
    try_max = 5
    try_count = 0
    local_control_count = len(ths_common_ctrls_dict)
    ths_window = None
    none_count = 0
    ctrl_mapping = {}
    for key in ths_common_ctrls_dict.keys():
        ctrl_mapping[key] = None

    if not shared_data.trade_window or not is_win_valid(shared_data.trade_window):
        app = Application(backend="uia").connect(title_re=r".*同花顺期货通.*", timeout=3)
        ths_window = app.window(title_re=r".*同花顺期货通.*")
        ths_window.wait('visible', timeout=2)
        shared_data.trade_window = ths_window
        ths_window.set_focus()
        ths_window.maximize()
    else:
        ths_window = shared_data.trade_window

    while try_count < try_max:
        all_ctrls = ths_window.descendants()
        for num, ctrl in enumerate(all_ctrls):
            try:
                rect = ctrl.rectangle()
                win_txt = ctrl.window_text()
                l, t, r, b = rect.left, rect.top, rect.right, rect.bottom
                rect_tuple = (l, t, r, b)
                if is_around(ths_common_ctrls_dict["条件单"][0], l) and is_around(ths_common_ctrls_dict["条件单"][1], t):
                    if ctrl_mapping['条件单'] is None:
                        ctrl_mapping['条件单'] = [ctrl, rect_tuple, win_txt]
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
            print(f"\r >>>>>>>>>>>> 已准确定位到全部所需控件[{local_control_count}] <<<<<<<<<<<<")
            # 需求3：打印全部控件key列表
            ctrl_key_list = list(ctrl_mapping.keys())
            print(f"全部控件名称列表：{ctrl_key_list}")
            break
        else:
            print(f"\r正在定位应用所需的控件：{local_control_count - none_count} - {[k for k, v in ctrl_mapping.items() if v is not None]}", flush=True, end="")
        try_count += 1
        sleep(0.1)
    missing_ctrls = [k for k, v in ctrl_mapping.items() if v is None]
    none_count = len(missing_ctrls)
    if none_count > 0:
        print(f"未定位到所需全部控件，程序不能继续运行即将自动退出：\n>>> 缺失控件列表[共缺失{none_count}个]:{missing_ctrls}")
        exit(0)
    shared_data.ths_common_control = ctrl_mapping
    # 在期货代码框输入交易品种代码并锁定
    code_ctrl = shared_data.ths_common_control['期货代码'][0]
    lock_ctrl = shared_data.ths_common_control["商品锁"][0]
    window = UIAWrapper(shared_data.trade_window.element_info)
    ts_code = shared_data.ts_code or "m2609"
    if code_ctrl.window_text() != ts_code:
        if code_ctrl.is_enabled():
            simulate_input(ctrl=code_ctrl, window=window, value=ts_code)
            lock_ctrl.click_input()
        else:
            lock_ctrl.click_input()
            simulate_input(ctrl=code_ctrl, window=window, value=ts_code)
            lock_ctrl.click_input()
        if code_ctrl.is_enabled():
            lock_ctrl.click_input()


def set_loss_profit(param: dict=None):
    """
    设置云止损止盈保本单
    """
    if param is None:
        param = shared_data.order_param_dict.copy()  # 即时行情价分析结果
    app = None
    # ths_window = None
    fut_code = shared_data.ts_code or "m2609"

    def set_price(drill_type: str, price):
        if shared_data.trade_window is not None:
            ths_window = shared_data.trade_window
        else:
            ths_pid = get_happ_pid()
            app = Application(backend="uia").connect(process=ths_pid, timeout=10)
            ths_window = app.top_window()
        ths_window.set_focus()
        # 定位”持仓"控件，设置前点击它确保显示期货代码控件可点
        position_text_ctrl = ths_window.child_window(control_type="Text", title="持仓")
        position_text_ctrl.wait("visible", timeout=3)
        position_text_ctrl.click_input()
        # print(f'同花顺窗口的标题：{ths_window.window_text()}')
        fut_code_ctrl = ths_window.child_window(control_type="Text", title=fut_code)
        fut_code_ctrl.wait("visible", timeout=3)
        # print(f"fut_code_ctrl：{fut_code_ctrl.window_text()}")
        fut_code_ctrl.right_click_input()

        context_menu = app.top_window()
        context_menu.wait("visible", timeout=3)
        stop_loss_profit_item = context_menu.child_window(
            control_type="MenuItem",
            title="止损止盈"
        )
        # print(f"stop_loss_item: {stop_loss_profit_item.window_text()}")
        stop_loss_profit_item.click_input()
        rect = stop_loss_profit_item.rectangle()
        # print(f"cx: {rect.left}, cy: {rect.top}")
        mouse.click(button="left", coords=(rect.right + 50, rect.top + 20))
        # 杀屏保程序，以防在启动止损止盈设置时出现遮挡
        kill_unprotected_process()
        print("已完成屏保、壁纸等遮挡处理！")
        create_win = ths_window.child_window(control_type="Window", title="云止损单")
        create_win.wait("visible", timeout=3)

        cloud_ctrl = ths_window.child_window(control_type="Text", title=drill_type)
        cloud_ctrl.wait("visible", timeout=3)
        cloud_ctrl.click_input()
        edit_ctrl = create_win.descendants(control_type="Edit")[0]
        sleep(0.5)
        edit_ctrl.set_text(price)
        create_text = ths_window.child_window(control_type="Text", title="创建")
        create_text.wait("visible", timeout=3)
        create_text.click_input()

    for drill_type, price in param.items():
        if price is not None:
            print(f"[{fut_code} {drill_type}] 设置完毕！")
            set_price(drill_type, price)
        else:
            print(f"跳过[{fut_code} {drill_type}] 设置！")
            continue




if __name__ == '__main__':
    # check_ths_status()
    # local_control()
    set_loss_profit()