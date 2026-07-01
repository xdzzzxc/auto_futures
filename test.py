from datetime import datetime
from pywinauto import Application, mouse
from time import sleep
from pywinauto.controls.uiawrapper import UIAWrapper
from public.print_context import print_context
from public.close_ad_window import close_ad_windows
from public import shared_data
from public.shared_data import simulate_input
import ctypes

def get_inspect_is_enabled(ctrl):
    """读取和Inspect一致的IsEnabled原生状态，替代不准的ctrl.is_enabled()"""
    try:
        # pywinauto内置封装，直接读取UIA原生IsEnabled属性
        return ctrl.element_info.get_property_value("IsEnabled")
    except Exception:
        return None


ths_common_ctrls_dict = {'用户名': (18, 721, 155, 738), '权益': (165, 719, 256, 739),
                         '可用资金': (271, 719, 390, 739), '商品锁': (287, 797, 303, 813),
                         '期货代码': (214, 796, 286, 813), '即时价格': (245, 836, 281, 853),
                         '平仓': (458, 863, 490, 884), '盈亏': (213, 923, 454, 962),
                         '保证金': (213, 945, 426, 962), '条件单': (272, 988, 311, 1007),
                         '买多': (243, 863, 275, 884), '卖空': (350, 863, 382, 884)}

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
            print(f"\r >>>>>>>>>>>> 已准确定位到全部所需控件 <<<<<<<<<<<<")
            break
        else:
            print(f"\r正在定位应用所需的控件：{local_control_count - none_count} - {[k for k, v in ctrl_mapping.items() if v is not None]}", flush=True, end="")
        try_count += 1
        sleep(2)
    if none_count > 0:
        print(f"未定位到所需控件：{none_count}, 程序不能继续运行！")
        exit(0)
    shared_data.ths_common_control = ctrl_mapping

    code_ctrl = shared_data.ths_common_control['期货代码'][0]
    lock_ctrl = shared_data.ths_common_control["商品锁"][0]
    print(f"code_ctrl:{get_inspect_is_enabled(code_ctrl)}, lock_ctrl:{get_inspect_is_enabled(lock_ctrl)}")
    window = UIAWrapper(shared_data.trade_window.element_info)
    ts_code = shared_data.ts_code or "jd2609"
    print(f"期货代码控件的可用属性：{code_ctrl.is_enabled()} - {code_ctrl.window_text()}")

    if code_ctrl.is_enabled():
        print(f"期货代码控件的可用属性：{code_ctrl.is_enabled()}")
        simulate_input(ctrl=code_ctrl, window=window, value=ts_code)
        lock_ctrl.click_input()
    else:
        print(f"期货代码控件的可用属性：{code_ctrl.is_enabled()}")
        lock_ctrl.click_input()
        simulate_input(ctrl=code_ctrl, window=window, value=ts_code)
        lock_ctrl.click_input()
    for n,(k, v) in enumerate(ctrl_mapping.items()):
        print(f"{n+1}.{k}: {v}")

if __name__ == '__main__':
    local_control()