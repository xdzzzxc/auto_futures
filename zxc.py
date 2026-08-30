import ast
expr = "last_price > open_first_price"
tree = ast.parse(expr, mode="eval")
for node in ast.walk(tree):
    if isinstance(node, ast.Name):
        print(node.id) # last_price、open_first_price


def set_loss_profit(param: dict = None):
    """
    设置云止损止盈保本单，只打开一次弹窗，批量处理多个价位
    """
    if param is None:
        param = shared_data.loss_profit_param.copy()

    fut_code = shared_data.ts_code or "m2609"

    # 1. 先过滤出真正需要设置的项
    todo_list = []
    for drill_type, price in param.items():
        if price is not None and price > 0:
            todo_list.append((drill_type, price))
        else:
            print(f"跳过[{fut_code} {drill_type}] 设置！")

    if not todo_list:
        print(f"[{fut_code}] 没有需要设置的云止损/止盈参数，直接返回")
        return

    # -------- 只做一次连接窗口、右键、打开云止损弹窗 --------
    ths_window = None
    app = None
    if shared_data.trade_window is not None:
        ths_window = shared_data.trade_window
        app = ths_window.app
    else:
        ths_pid = get_happ_pid()
        app = Application(backend="uia").connect(process=ths_pid, timeout=10)
        ths_window = app.top_window()
        # 可选缓存窗口：shared_data.trade_window = ths_window

    ths_window.set_focus()

    # 点击【持仓】tab
    position_text_ctrl = ths_window.child_window(control_type="Text", title="持仓")
    position_text_ctrl.wait("visible", timeout=3)
    position_text_ctrl.click_input()

    # 定位合约条目
    fut_code_ctrl = None
    k = 0
    while fut_code_ctrl is None and k <= 10:
        k += 1
        try:
            tmp_ctrl = ths_window.child_window(control_type="Text", title=fut_code)
            tmp_ctrl.wait("visible", timeout=1)
            fut_code_ctrl = tmp_ctrl
        except Exception:
            fut_code_ctrl = None
        if fut_code_ctrl is None:
            sleep(1)

    if fut_code_ctrl is None:
        print_context(f"[{fut_code}] 找不到持仓合约控件，终止设置")
        return

    fut_code_ctrl = cast(UIAWrapper, fut_code_ctrl)
    fut_code_ctrl.right_click_input()
    sleep(1)

    context_menu = app.top_window()
    context_menu.wait("visible", timeout=3)
    stop_loss_profit_item = context_menu.child_window(
        control_type="MenuItem",
        title="止损止盈"
    )
    stop_loss_profit_item.click_input()

    rect = stop_loss_profit_item.rectangle()
    # 模拟鼠标点击菜单位置（原有逻辑保留）
    from pywinauto import mouse
    mouse.click(button="left", coords=(rect.right + 50, rect.top + 20))

    close_ad_windows()
    # 唤起云止损单弹窗，只打开一次
    create_win = ths_window.child_window(control_type="Window", title="云止损单")
    create_win.wait("visible", timeout=3)

    # -------- 在同一个弹窗内循环处理每一个待设置项 --------
    for drill_type, price in todo_list:
        try:
            cloud_ctrl = ths_window.child_window(control_type="Text", title=drill_type)
            cloud_ctrl.wait("visible", timeout=3)
            cloud_ctrl.click_input()

            edit_ctrl = create_win.descendants(control_type="Edit")[0]
            sleep(0.5)
            edit_ctrl.set_text(str(price))

            create_text = ths_window.child_window(control_type="Text", title="创建")
            create_text.wait("visible", timeout=3)
            create_text.click_input()
            sleep(0.6)

            print(f"[{fut_code} {drill_type}] 设置完毕！")
        except Exception as e:
            print(f"[{fut_code} {drill_type}] 设置失败，异常：{str(e)}")
            # 单项失败，继续下一项，不整体崩溃
            continue

    # 可选：弹窗残留处理，如果弹窗还在，按ESC关闭；防止弹窗残留遮挡后续操作
    try:
        if create_win.exists():
            create_win.type_keys("{ESC}")
    except Exception:
        pass