from datetime import datetime
from pywinauto import Application, mouse
from pywinauto.timings import wait_until_passes
from time import sleep
import random
import os
from public.print_context import print_context
import psutil
# from core.close_ad_window import close_ad_windows
from public.close_ad_window import close_ad_windows
from public import shared_data
ths_path = r"C:\同花顺期货通\bin\hexinlauncher.exe"
# RESTART_COUNT = 0
# MAX_RESTART_TIMES = 3  # 最多重启6次

login_ctrl = {'期货账户': (1663, 1019, 1697, 1035), '选择用户': (862, 502, 1045, 522),
              '模拟用户': (847, 538, 1077, 555), '国泰君安_CTP': (847, 563, 1047, 580),
              '期货密码': (862, 582, 1046, 602), '登录': (840, 647, 1080, 681),
              }
user_name_dict = {0: "模拟用户", 1: "期货用户"}
ctrl_mapping = {}
ths_common_ctrls_dict = {'用户名': (18, 721, 155, 738), '权益': (165, 719, 256, 739),
                         '可用资金': (271, 719, 390, 739), '商品锁': (287, 797, 303, 813),
                         '期货代码': (214, 796, 286, 813), '即时价格': (245, 836, 281, 853),
                         '平仓': (428, 829, 521, 889), '盈亏': (213, 923, 454, 962),
                         '保证金': (213, 945, 426, 962), '条件单': (272, 988, 311, 1007)}
# REQUIRE_CTRL_KEYS = list(ths_common_ctrls_dict.keys())


# def restart_ths():
#     global RESTART_COUNT
#     RESTART_COUNT += 1
#     print(f"\n===== 第 {RESTART_COUNT} 次重启同花顺 =====")
#
#     # 达到最大重试次数，直接退出
#     if RESTART_COUNT >= MAX_RESTART_TIMES:
#         print(f"[严重错误] 已达到最大重启次数 {MAX_RESTART_TIMES}，程序强制退出")
#         exit(1)
#
#     # 1. 强制结束所有同花顺相关进程
#     print("正在关闭旧同花顺进程...")
#     for proc in psutil.process_iter(['name', 'exe']):
#         try:
#             name = (proc.info.get('name') or "").lower()
#             exe = (proc.info.get('exe') or "").lower()
#             if "hexin" in name or "hexinlauncher" in name or "同花顺" in exe:
#                 proc.kill()
#                 print(f"已终止进程 PID: {proc.pid}")
#         except (psutil.NoSuchProcess, psutil.AccessDenied):
#             continue
#
#     # 2. 等待进程彻底退出、端口/句柄释放（延长时长，适配慢电脑）
#     sleep(5)
#     # 清空全局控件脏数据
#     shared_data.login_control.clear()
#     shared_data.ths_common_control.clear()
#     print("旧进程已关闭，准备重新启动软件...")
#
#     # 3. 捕获启动异常，避免单次失败直接炸栈
#     try:
#         start_ths()
#         # 等待主窗口、界面、控件渲染完成
#         sleep(4)
#         run_ths()
#     except Exception as e:
#         print(f"[重启异常] 启动/连接窗口失败: {str(e)}，继续重试")
#         sleep(2)
#         restart_ths()


# def check_ctrl_valid():
#     """校验所有关键控件，异常则重启"""
#     ctrl_map = shared_data.ths_common_control
#     for key in REQUIRE_CTRL_KEYS:
#         # 1. 键不存在 → 无效
#         if key not in ctrl_map:
#             print(f"[校验失败] 缺失控件键: {key}，即将重启")
#             sleep(2)  # 停顿2秒再重启
#             restart_ths()
#             return
#         # 2. 控件对象为 None → 无效
#         ctrl_item = ctrl_map[key]
#         if not ctrl_item or ctrl_item[0] is None:
#             print(f"[校验失败] 控件 {key} 为 None，即将重启")
#             sleep(2)
#             restart_ths()
#             return
#     # 全部通过
#     print(f"[校验通过] 所有控件加载正常 - {REQUIRE_CTRL_KEYS}")


def start_ths():
    Application(backend="uia").start(ths_path)
    print(f"程序正在连接同花顺主操作窗口对象 ------ [{datetime.now().strftime('%H:%M:%S')}]")
    while True:
        app = Application(backend="uia").connect(title_re=r".*同花顺期货通.*", timeout=30)
        ths_window = app.window(title_re=r".*同花顺期货通.*", control_type="Window")
        if ths_window is not None:
            shared_data.trade_window = ths_window
            # ths_window.print_control_identifiers()  # 这是一行测试窗口所有控件的代码
            break
    # print(f"程序已成功连接同花顺主操作窗口并创建了公共实例对象[ths_window] ------ [{datetime.now().strftime('%H:%M:%S')}]")
    print(f'>>>>>>同花顺期货通软件成功启动！')


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


def run_ths(user_type=shared_data.user_type):
    shared_data.user_name = user_name_dict[user_type]
    flag = check_ths_status()
    if not flag:
        start_ths()
    app = Application(backend="uia").connect(title_re=r".*同花顺期货通.*", timeout=20)
    ths_window = app.window(title_re=r".*同花顺期货通.*")
    ths_window.wait('visible', timeout=20)
    shared_data.trade_window = ths_window
    # print(f'ths_window:{ths_window}\nshared_data.trade_window_id:{shared_data.trade_window}')
    ths_window.set_focus()
    ths_window.maximize()
    user_type_btn = ths_window.child_window(control_type='Button', title='期货账户')
    
    shared_data.login_control.clear()
    shared_data.login_control['期货账户'] = [user_type_btn, (user_type_btn.rectangle().left, user_type_btn.rectangle().top, user_type_btn.rectangle().right, user_type_btn.rectangle().bottom)]
    if not user_type_btn.is_enabled():
        # print(f'用户已登录，如有冲突请退出同花顺程序重新登录！')
        restart_ths()
        ths_window = shared_data.trade_window
        ths_window.set_focus()
        ths_window.maximize()
        user_type_btn = ths_window.child_window(control_type='Button', title='期货账户')
        shared_data.login_control.clear()
        shared_data.login_control['期货账户'] = [user_type_btn, user_type_btn.rectangle()]

    close_ad_windows()
    shared_data.login_control['期货账户'][0].click_input()
    sleep(2)
    subwindow = ths_window.child_window(title="同花顺期货通交易", control_type="Window")
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
            shared_data.login_control['期货账户'][0].click_input()
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
    login()
    # 开始定位通用控件：ths_common_control = {} 交易平台常用控件字典
    shared_data.ths_common_control.clear()
    all_ctrls_count = 0
    # print(f"等待同花顺程序加载底层控件......[{datetime.now().strftime('%H:%M:%S')}]\n如果等待时间太长，可以选择手动先重启软件。")
    while True:
        all_ctrls = ths_window.descendants()  # control_type='Text'
        if len(all_ctrls) == all_ctrls_count:
            print(f'\r成功加载底层控件： {len(all_ctrls)}  [{datetime.now().strftime("%H:%M:%S")}]', end='', flush=True)
            break
        else:
            print(f'\r[{datetime.now().strftime("%H:%M:%S")}]程序正在加载所有控件，现已加载控件数： {len(all_ctrls)}', end='', flush=True)
        all_ctrls_count = len(all_ctrls)
        sleep(4)  # 每次循环停留4秒的时间
    print("\n")  # 恢复正常打印
    for num, ctrl in enumerate(all_ctrls):
        if ctrl.rectangle().left > 200 and ctrl.rectangle().top > 800 and ctrl.window_text() == "条件单":
            shared_data.ths_common_control['条件单'] = [ctrl, (ctrl.rectangle().left, ctrl.rectangle().top, ctrl.rectangle().right, ctrl.rectangle().bottom), ctrl.window_text()]
        if all(key in ctrl.window_text() for key in ["保证金", "所"]):
            shared_data.ths_common_control['保证金'] = [ctrl, (ctrl.rectangle().left, ctrl.rectangle().top, ctrl.rectangle().right, ctrl.rectangle().bottom), ctrl.window_text()]
        if any(key in ctrl.window_text() for key in ["GeometryGroup.TradeUnLock", "GeometryGroup.TradeLock"]):
            shared_data.ths_common_control["商品锁"] = [ctrl, (ctrl.rectangle().left, ctrl.rectangle().top, ctrl.rectangle().right, ctrl.rectangle().bottom), ctrl.window_text()]
        if ctrl.element_info.control_type == "Text" and any(key in ctrl.window_text() for key in ["平仓", "平多", "平空", "先开先平", "平多仓", "平空仓"]):
            shared_data.ths_common_control['平仓'] = [ctrl, (ctrl.rectangle().left, ctrl.rectangle().top, ctrl.rectangle().right, ctrl.rectangle().bottom), ctrl.window_text()]
        if any(key in ctrl.window_text() for key in ["模拟交易-1811889418", "国泰君安_CTP-85415809"]):
            shared_data.ths_common_control['用户名'] = [ctrl, ctrl.rectangle(), ctrl.window_text()]
        if "权益" in ctrl.window_text():
            shared_data.ths_common_control['权益'] = [ctrl, ctrl.rectangle(), ctrl.window_text()]
        if "可用资金" in ctrl.window_text():
            shared_data.ths_common_control['可用资金'] = [ctrl, ctrl.rectangle(), ctrl.window_text()]
        if any(key in ctrl.window_text() for key in ["买多", "加多", "锁仓"]):
            shared_data.ths_common_control['买多'] = [ctrl, (ctrl.rectangle().left, ctrl.rectangle().top, ctrl.rectangle().right, ctrl.rectangle().bottom), ctrl.window_text()]
        if any(key in ctrl.window_text() for key in ["卖空", "加空", "锁仓"]):
            shared_data.ths_common_control['卖空'] = [ctrl, (ctrl.rectangle().left, ctrl.rectangle().top, ctrl.rectangle().right, ctrl.rectangle().bottom), ctrl.window_text()]

    for num, ctrl in enumerate(all_ctrls):
        top = shared_data.ths_common_control['保证金'][0].rectangle().top
        left = shared_data.ths_common_control['保证金'][0].rectangle().left
        if ctrl.rectangle().left in range(left-2, left+3) and ctrl.rectangle().top in range(top - 24, top - 20) and \
                ctrl.element_info.control_type == 'Text':
            shared_data.ths_common_control['盈亏'] = [ctrl, ctrl.rectangle(), ctrl.window_text()]
        left = shared_data.ths_common_control['商品锁'][0].rectangle().left
        top = shared_data.ths_common_control['商品锁'][0].rectangle().top
        if ctrl.rectangle().left in range(left-75, left - 70) and ctrl.rectangle().top in range(top-2, top+3):
            shared_data.ths_common_control['期货代码'] = [ctrl, (ctrl.rectangle().left, ctrl.rectangle().top, ctrl.rectangle().right, ctrl.rectangle().bottom), ctrl.window_text()]
        if ctrl.rectangle().left in range(230, 250) and ctrl.rectangle().top in range(830, 842):
            shared_data.ths_common_control['即时价格'] = [ctrl, ctrl.rectangle(), ctrl.window_text()]

    # check_ctrl_valid()  # 检查所在控件是否是已成功加载


if __name__ == '__main__':
    # start_ths()
    run_ths()

