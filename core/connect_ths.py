from datetime import datetime
from pywinauto import Application, mouse
from time import sleep
import random
import os
from public.print_context import print_context
import psutil
# from core.close_ad_window import close_ad_windows
from public.close_ad_window import close_ad_windows
from public import shared_data
from public.shared_data import simulate_input

ths_path = r"C:\同花顺期货通\bin\hexinlauncher.exe"
# RESTART_COUNT = 0
# MAX_RESTART_TIMES = 3  # 最多重启6次

login_ctrl = {'期货户': (1663, 1019, 1697, 1035), '选择用户': (862, 502, 1045, 522),
              '模拟用户': (847, 538, 1077, 555), '国泰君安_CTP': (847, 563, 1047, 580),
              '期货密码': (862, 582, 1046, 602), '登录': (840, 647, 1080, 681),
              }
user_name_dict = {0: "模拟用户", 1: "期货用户"}
subwindow = None  # 定义登录子窗口变量

ths_common_ctrls_dict = {'用户名': (18, 721, 155, 738), '权益': (165, 719, 256, 739),
                         '可用资金': (271, 719, 390, 739), '商品锁': (287, 797, 303, 813),
                         '期货代码': (214, 796, 286, 813), '即时价格': (245, 836, 281, 853),
                         '平仓': (458, 863, 490, 884), '盈亏': (213, 923, 454, 962),
                         '保证金': (213, 945, 426, 962), '条件单': (272, 988, 311, 1007),
                         '买多': (243, 863, 275, 884), '卖空': (350, 863, 382, 884)}


def start_ths():
    """
    启动同花顺并登录期货交易平台
    """
    global subwindow
    try_counts = 0
    max_try_counts = 6
    # 1. 先启动同花顺客户端
    Application(backend="uia").start(ths_path)
    print(f"已启动同花顺期货通，等待窗口加载 ------ [{datetime.now().strftime('%H:%M:%S')}]")

    while True:
        try_counts += 1
        print(f"\r第{try_counts}/{max_try_counts}次尝试连接窗口", flush=True, end="")

        # 超过最大重试次数，抛出异常终止
        if try_counts > max_try_counts:
            raise RuntimeError(f"连接同花顺窗口超时，已重试{max_try_counts}次，请检查程序是否正常启动")

        try:
            # 连接主程序，短超时快速判断
            app = Application(backend="uia").connect(title_re=r".*同花顺期货通.*", timeout=10)
            ths_window = app.window(title_re=r".*同花顺期货通.*", control_type="Window")

            # 判断窗口真实存在
            if ths_window.exists(timeout=10):
                shared_data.trade_window = ths_window
                ths_window.set_focus()
                ths_window.maximize()
                print(f"\r第{try_counts}/{max_try_counts}次尝试连接窗口 - 连接成功 [{datetime.now().strftime('%H:%M:%S')}]")
                print()
                # ths_window.print_control_identifiers()
                break
        except Exception as e:
            # 捕获连接超时、找不到进程等所有异常，继续重试
            print(f"窗口未就绪，等待重试，异常信息：{str(e)}")

        # 每次轮询间隔1秒，降低CPU占用
        sleep(1)
    user_type_btn = ths_window.child_window(control_type='Button', title_re='期货户|期货用户')
    # print("用正则表达式成功获取控件定位！")
    shared_data.login_control.clear()
    shared_data.login_control['期货户'] = [user_type_btn,
                                           (user_type_btn.rectangle().left, user_type_btn.rectangle().top,
                                            user_type_btn.rectangle().right, user_type_btn.rectangle().bottom)]
    if not user_type_btn.is_enabled():
        # print(f'用户已登录，如有冲突请退出同花顺程序重新登录！')
        restart_ths()
        ths_window = shared_data.trade_window
        ths_window.set_focus()
        ths_window.maximize()
        user_type_btn = ths_window.child_window(control_type='Button', title='期货户')
        shared_data.login_control.clear()
        shared_data.login_control['期货户'] = [user_type_btn, user_type_btn.rectangle()]

    close_ad_windows()
    shared_data.login_control['期货户'][0].click_input()
    sleep(2)
    exist_flag = False
    max_wait = 15  # 最多等待15秒
    wait_cnt = 0

    while not exist_flag and wait_cnt < max_wait:
        try:
            subwindow = ths_window.child_window(title="同花顺期货通交易", control_type="Window")
            # timeout=0 立刻判断，不阻塞
            if subwindow.exists(timeout=0):
                exist_flag = True
                break
        except Exception:  # noqa
            # 查找中途控件未渲染，直接跳过本轮
            pass
        wait_cnt += 1
        sleep(1)

    if not exist_flag:
        raise RuntimeError("等待【同花顺期货通交易】登录窗口超时，未检测到弹窗")
    shared_data.login_control['登录窗口'] = [subwindow, subwindow.rectangle()]
    # 定位登录控件
    edit_ctrls = ths_window.descendants(control_type='Edit')
    shared_data.login_control['选择用户'] = [edit_ctrls[0], edit_ctrls[0].rectangle()]
    shared_data.login_control['期货密码'] = [edit_ctrls[2], edit_ctrls[2].rectangle()]
    shared_data.login_control['选择用户'][0].click_input()
    sleep(random.uniform(0.5, 1))
    user_type = subwindow.descendants(control_type='Text')
    shared_data.login_control['模拟交易'] = [user_type[0], user_type[0].rectangle()]
    shared_data.login_control['国泰君安'] = [user_type[1], user_type[1].rectangle()]
    login_btn = subwindow.child_window(title='登录')
    # print(f'login_btn:{login_btn.window_text()} - {login_btn.rectangle()}')
    shared_data.login_control['登录'] = [login_btn, login_btn.rectangle()]

    def login():
        # close_ad_windows()  # 关闭广告窗口
        subwindow.set_focus()
        if not shared_data.login_control["登录窗口"][0].is_visible():
            shared_data.login_control['期货户'][0].click_input()
        if shared_data.user_type == 0:
            shared_data.login_control['选择用户'][0].click_input()
            sleep(random.uniform(0.2, 0.5))
            shared_data.login_control['模拟交易'][0].click_input()
            sleep(random.uniform(0.2, 0.5))
        else:
            shared_data.login_control['选择用户'][0].click_input()
            sleep(random.uniform(0.2, 0.5))
            shared_data.login_control['国泰君安'][0].click_input()
            sleep(random.uniform(0.2, 0.5))
            shared_data.login_control['期货密码'][0].set_text(os.environ.get("trade_password"))
        shared_data.login_control['登录'][0].click_input()
    # 登录期货交易界面
    login()


def restart_ths():
    app = Application(backend="uia").connect(title_re=r".*同花顺期货通.*")
    app.kill()  # 直接关闭程序
    print("正在准备重启同花顺期货通应用程序 ······")
    start_ths()

def check_ths_status(keyword='happ'):  # noqa
    flag = False
    # 遍历所有进程，指定需要的字段
    for proc in psutil.process_iter(['name', 'pid', 'exe']):
        try:
            process_info = proc.info
            # 提取字段，并为None值设置默认空字符串
            name = process_info.get('name', '')  # 避免name为None
            pid = process_info.get('pid', 0)
            exe = process_info.get('exe', '')  # 避免exe为None

            # 打印进程信息（仅非空时，避免打印None）
            # print(f'进程名：{name}, 进程ID：{pid}, 进程路径：{exe if exe else "无"}')

            # 仅当name或exe非空时，才进行关键字匹配
            if (name and keyword in name) or (exe and keyword in exe):
                # print(f'【匹配到】进程名：{name}, 进程ID：{pid}, 进程路径：{exe}')
                flag = True  # 标记找到匹配进程
        except psutil.NoSuchProcess:
            # 进程已结束，跳过
            continue
        except psutil.AccessDenied:
            # 权限不足，无法获取进程信息，跳过
            print(f'进程ID：{proc.pid} 无访问权限，跳过')
            continue
    return flag  # 返回是否找到匹配进程

def click_position(rect_tuple):
    x = rect_tuple[0] + (rect_tuple[2] - rect_tuple[0])//2
    y = rect_tuple[1] + (rect_tuple[3] - rect_tuple[1])//2
    return mouse.click(button='left', coords=(x, y))

def is_around(checked_value, target_value, error_range=4):  # 检测坐标位置函数,定位窗口控件时需用
    return (target_value - error_range) <= checked_value <= (target_value + error_range)

def local_control():
    try_max = 5
    try_count = 0
    local_control_count = len(ths_common_ctrls_dict)  # 需定位的控件数
    ths_window = None  # 定义同花顺交易窗口对象
    none_count = 0
    ctrl_mapping = {}
    for key in ths_common_ctrls_dict.keys():
        ctrl_mapping[key] = None
    # print(f"{ctrl_mapping}\n{ctrl_mapping.values()}")
    if not shared_data.trade_window:
        # print("shared_data.ths_common_control为空，等待连接同花顺")
        app = Application(backend="uia").connect(title_re=r".*同花顺期货通.*", timeout=20)
        ths_window = app.window(title_re=r".*同花顺期货通.*")
        ths_window.wait('visible', timeout=20)
        shared_data.trade_window = ths_window
        ths_window.set_focus()
        ths_window.maximize()
        # print(f"窗口对象：{ths_window}\n窗口大小：{ths_window.rectangle()}")
    else:
        ths_window = shared_data.trade_window

    # 通过循环完成对所需控件的定位操作
    while try_count < try_max:
        all_ctrls = ths_window.descendants()
        for num, ctrl in enumerate(all_ctrls):  # 开始定位控件
            try:
                rect = ctrl.rectangle()
                win_txt = ctrl.window_text()
                l, t, r, b = rect.left, rect.top, rect.right, rect.bottom
                rect_tuple = (l, t, r, b)
                if is_around(ths_common_ctrls_dict["条件单"][0], l) and is_around(ths_common_ctrls_dict["条件单"][1], t):
                    if ctrl_mapping['条件单'] is None:
                        ctrl_mapping['条件单'] = [ctrl, rect_tuple, win_txt]
                if all(key in win_txt for key in ["保证金", "所"]):
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
                        print(ctrl.help_text())
                if is_around(ths_common_ctrls_dict["盈亏"][0], l) and is_around(ths_common_ctrls_dict["盈亏"][1], t):
                    if ctrl_mapping['盈亏'] is None:
                        ctrl_mapping['盈亏'] = [ctrl, rect_tuple, win_txt]
                if is_around(ths_common_ctrls_dict["期货代码"][0], l) and is_around(ths_common_ctrls_dict["期货代码"][1], t):
                    if ctrl_mapping['期货代码'] is None:
                        ctrl_mapping['期货代码'] = [ctrl, rect_tuple, win_txt]

                if is_around(ths_common_ctrls_dict["即时价格"][0], l, error_range=15) and is_around(ths_common_ctrls_dict["即时价格"][1], t):
                    if ctrl_mapping['即时价格'] is None:
                        ctrl_mapping['即时价格'] = [ctrl, rect_tuple, win_txt]
            except Exception:  # noqa
                continue

        none_count = sum(1 for v in ctrl_mapping.values() if v is None)
        if none_count == 0:
            print(f" >>> 已准确定位到全部所需控件！")
            break
        else:
            print(f"\r正在定位应用所需的控件：{local_control_count - none_count} - {[k for k, v in ctrl_mapping.items() if v is not None]}", flush=True, end="")
        try_count += 1
        sleep(2)
    if none_count > 0:
        print(f"未定位到所需控件：{none_count}, 程序不能继续运行！")
        exit(0)
    shared_data.ths_common_control = ctrl_mapping
    # for n,(k, v) in enumerate(ctrl_mapping.items()):
    #     print(f"{n+1}.{k}: {v}")

def connect_ths():
    flag = check_ths_status()
    if not flag:
        print("正在启动同花顺软件并登录用户")
        start_ths()  # 正常启动同花顺并完成用户登录
        local_control()  # 定位交易窗口所需控件
    else:
        print("程序检测到同花顺在运行中，为防止登录用户冲突，正在校验用户身份的合法性······")
        restart_ths()
        local_control()


if __name__ == '__main__':
    # start_ths()
    # connect_ths()
    local_control()
