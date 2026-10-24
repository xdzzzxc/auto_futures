from pywinauto import mouse, keyboard
from time import sleep
from typing import Union
import pyperclip

rect_dict = {
    "position": (534, 747, 40, 19),
    "ts_code": (680, 794, 48, 17),
    "loss_profit": (706, 932, 218, 34),
    "set_loss_profit": (957, 938, 70, 20),
    "cloud_loss": (845, 330, 52, 19),
    "cloud_profit": (934, 330, 52, 19),
    "cloud_hold": (1023, 330, 52, 19),
    "edit": (765, 508, 80, 24),
    "create": (1085, 720, 26, 19)
}


def move_click(ctrl_name: str, click_type=0):
    """
    click_type: 0仅移动悬浮;1左键;2右键
    """
    x, y, w, h = rect_dict[ctrl_name]
    # print(f"【{ctrl_name}】rect: {x, y, w, h} | center: {x + w // 2, y + h // 2}")
    center_x = x + w // 2
    center_y = y + h // 2
    mouse.move((center_x, center_y))
    sleep(0.5)
    if click_type == 1:
        mouse.click(button="left", coords=(center_x, center_y))
    elif click_type == 2:
        mouse.click(button="right", coords=(center_x, center_y))
    sleep(0.5)


def edit_input(ctrl_name: str, value: Union[str, int, float]):
    """
    点击编辑框、全选、剪贴板粘贴输入，规避send_keys小数点特殊符号BUG
    支持整数、小数，兼容黄金au、原油sc等带小数合约
    """
    move_click(ctrl_name, click_type=1)
    sleep(0.5)
    # 全选原有内容
    keyboard.send_keys("^a")
    sleep(0.2)

    # 转为原始字符串，保留小数，不做任何转义
    raw_text = str(value)
    # 写入剪贴板
    pyperclip.copy(raw_text)
    sleep(0.1)
    # Ctrl+V粘贴
    keyboard.send_keys("^v")
    sleep(0.3)



def set_cloud_bills(cloud_type: int, set_value: Union[str, int, float]):
    """
    cloud_type: 0 云止损；1 云止盈；2 云保本
    """
    if cloud_type not in (0, 1, 2):
        raise ValueError("cloud_type 只能是 0(止损)/1(止盈)/2(保本)")

    print(f"\r===== 开始设置云单 =====", flush=True, end="")
    # 选中持仓行（增加左键点击，原代码只悬浮！）
    move_click("position", click_type=1)
    # 右键合约代码，弹出菜单
    move_click("ts_code", click_type=2)
    sleep(1.0)  # 右键菜单额外等待，同花顺弹窗渲染慢，重点优化
    move_click("loss_profit", click_type=1)
    move_click("set_loss_profit", click_type=1)
    sleep(0.8)  # 云止盈止损弹窗弹出等待

    if cloud_type == 0:
        # print(" >> 选择【云止损】")
        move_click("cloud_loss", click_type=1)
        edit_input(ctrl_name="edit", value=set_value)
        move_click("create", click_type=1)
        print("\r===== 云止损单设置执行完成 =====", flush=True, end="")
    elif cloud_type == 1:
        # print(" >> 选择【云止盈】")
        move_click("cloud_profit", click_type=1)
        edit_input(ctrl_name="edit", value=set_value)
        move_click("create", click_type=1)
        print("\r===== 云止盈单设置执行完成 =====", flush=True, end="")
    elif cloud_type == 2:
        # print(" >> 选择【云保本】")
        move_click("cloud_hold", click_type=1)
        edit_input(ctrl_name="edit", value=set_value)
        move_click("create", click_type=1)
        print("\r===== 云保本单设置执行完成 =====", flush=True, end="")


if __name__ == '__main__':
    # 使用示例：0止损，设置1200
    # set_cloud_bills(cloud_type=0, set_value=1200)
    # set_cloud_bills(cloud_type=1, set_value=3260)
    set_cloud_bills(cloud_type=0, set_value=3238)
