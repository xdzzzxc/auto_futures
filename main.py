from time import sleep
from core.monitor import monitor_profit_loss
from public import shared_data
from log.trade_log import setup_trade_loggers, stop_queue_listener
from public.print_context import print_context
from core.connect_ths import check_ths_status, ths_watchdog
from core.trade import order
from data.collect_current_price import get_current_price
from data.future_trend import merge_two_info_dict
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from data.data_from_sina import fetch_future_data
from public.sync_time import sync_time
from data.get_quote import get_open_price
from data.db_price import flush_remain_buffer
from data.reget_open_price import reget_open_price
from public.anti_screensaver import main_daemon
from public.shared_data import clean_old_trade_db, default_lots_dict
from audio.play_alert import *

TIMEOUT_SEC = 10

def global_exception_handler(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    _logger = shared_data.logger
    if _logger is None:
        sound_warning()
        print_context("【全局未捕获异常】程序崩溃，日志器尚未初始化完成！", exc_info=(exc_type, exc_value, exc_traceback))
        return
    _logger.critical("【全局未捕获异常】程序崩溃", exc_info=(exc_type, exc_value, exc_traceback))

def get_direction(title="交易方向", msg=None) -> str | None:
    default_dir = shared_data.direction
    if msg is None:
        msg = (f"金投网推荐[{shared_data.ts_code}]: {'暂无推荐' if not shared_data.direction else shared_data.direction}"
               f"\n要变更交易方向，请手动选择！")
    OPTIONS = ["rise", "fall", "sideways", "cautious", "ease"]

    root = tk.Tk()
    root.title(title)
    root.attributes('-topmost', True)
    root.lift()
    root.resizable(False, False)
    root.attributes('-toolwindow', True)

    win_width = 380
    win_height = 150
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    root.geometry(f"{win_width}x{win_height}+{(screen_width - win_width) // 2}+{(screen_height - win_height) // 2}")

    frame = ttk.Frame(root, padding=10)
    frame.pack(fill=tk.BOTH, expand=True)

    ttk.Label(frame, text=msg, font=("微软雅黑", 10)).pack(anchor="w")

    selected_dir = tk.StringVar(value=default_dir)
    combo = ttk.Combobox(
        frame,
        textvariable=selected_dir,
        values=OPTIONS,
        font=("微软雅黑", 10),
        state="readonly"
    )
    combo.pack(fill=tk.X, pady=6)

    result = None
    timer_id = None
    is_auto = False

    def auto_timeout():
        nonlocal is_auto
        is_auto = True
        if root.winfo_exists():
            ok()

    timer_id = root.after(TIMEOUT_SEC * 1000, auto_timeout)

    def ok():
        nonlocal result, timer_id
        if timer_id is not None:
            root.after_cancel(timer_id)
            timer_id = None
        result = selected_dir.get().strip()
        shared_data.direction = result
        if is_auto:
            print_context(f"程序自动输入交易方向的默认值：{result}")
        else:
            print_context(f"人工手动输入交易方向值：{result}")
        root.destroy()

    def cancel():
        nonlocal result, timer_id
        if timer_id is not None:
            root.after_cancel(timer_id)
            timer_id = None
        result = None
        root.destroy()

    root.bind("<Return>", lambda e: ok())
    root.bind("<Escape>", lambda e: cancel())

    btn_frame = ttk.Frame(frame)
    btn_frame.pack(anchor="e", pady=4)
    ttk.Button(btn_frame, text="确定", command=ok, width=6).pack(side=tk.LEFT, padx=5)
    ttk.Button(btn_frame, text="取消", command=cancel, width=6).pack(side=tk.LEFT)

    root.mainloop()
    return result

def show_custom_choicebox(choices, title="选择品种", msg="请选择期货品种") -> str | None:
    selected = None
    timer_id = None

    win = tk.Tk()
    win.title(title)
    win.geometry("600x420")
    win.resizable(False, False)
    win.configure(bg="#f0f0f0")

    label = ttk.Label(win, text=msg, font=("Microsoft YaHei", 11))
    label.pack(pady=8)

    listbox = tk.Listbox(
        win,
        font=("Microsoft YaHei", 10),
        height=14,
        width=50,
        bg="white",
        relief="groove",
        bd=1,
        selectbackground="#0078D7",
        selectforeground="yellow",
        fg='blue',
        highlightthickness=0,
        selectborderwidth=0,
        activestyle="none"
    )
    for item in choices:
        listbox.insert(tk.END, item)

    default_code = shared_data.default_tscode
    target_idx = None
    for idx, text in enumerate(choices):
        if text.startswith(f"{default_code}-"):
            target_idx = idx
            break
    if target_idx is not None:
        listbox.selection_set(target_idx)
    elif choices:
        listbox.selection_set(0)

    listbox.pack(padx=18, pady=6, fill=tk.BOTH, expand=True)
    listbox.bind("<Double-1>", lambda event: on_ok())

    is_auto = False
    def auto_timeout():
        nonlocal is_auto
        is_auto = True
        if win.winfo_exists():
            target_code = shared_data.default_tscode
            idx = None
            for i, text in enumerate(choices):
                if text.startswith(f"{target_code}-"):
                    idx = i
                    break
            if idx is not None:
                listbox.selection_clear(0, tk.END)
                listbox.selection_set(idx)
            on_ok()

    timer_id = win.after(TIMEOUT_SEC * 1000, auto_timeout)

    def on_ok():
        nonlocal selected, timer_id, is_auto
        if timer_id is not None:
            win.after_cancel(timer_id)
            timer_id = None
        sel_idx = listbox.curselection()
        if sel_idx:
            selected = listbox.get(sel_idx[0])
            if is_auto:
                print_context(f"程序自动输入选择品种的默认值：{selected}")
            else:
                print_context(f"人工手动输入选择品种值：{selected}")
        win.destroy()

    def on_cancel():
        nonlocal selected, timer_id
        if timer_id is not None:
            win.after_cancel(timer_id)
            timer_id = None
        selected = None
        win.destroy()

    btn_frame = ttk.Frame(win)
    btn_frame.pack(pady=12)
    ok_btn = ttk.Button(btn_frame, text="OK", command=on_ok, width=10)
    ok_btn.pack(side=tk.LEFT, padx=14)
    cancel_btn = ttk.Button(btn_frame, text="Cancel", command=on_cancel, width=10)
    cancel_btn.pack(side=tk.LEFT, padx=14)

    win.mainloop()
    return selected

def select_future():
    futures_info_dict = merge_two_info_dict()
    choices = []
    code_map = {}

    for code, (trend, info) in futures_info_dict.items():
        display_text = f"{code}-{trend}-{info}"
        choices.append(display_text)
        code_map[display_text] = (code, trend)

    from public import shared_data
    required_contracts = shared_data.quote_list
    default_trend = "sideways"
    for code in required_contracts:
        display_text = f"{code}-{default_trend}-必备品种"
        if display_text not in choices:
            choices.append(display_text)
            code_map[display_text] = (code, default_trend)

    def show_scroll_choicebox(title, msg, choices) -> str | None:
        selected_val = None
        timer_id = None
        is_auto = False

        root = tk.Tk()
        root.title(title)
        root.geometry("600x400")
        root.minsize(700, 450)
        main_frame = tk.Frame(root, padx=25, pady=25)
        main_frame.pack(fill=tk.BOTH, expand=True)
        tip_label = tk.Label(main_frame, text=msg, font=("blue", 14))
        tip_label.pack(anchor="w", pady=(0, 18))
        list_panel = tk.Frame(main_frame, relief=tk.RIDGE, bd=3)
        list_panel.pack(fill=tk.BOTH, expand=True, pady=0)
        v_scroll = tk.Scrollbar(list_panel, orient=tk.VERTICAL)
        h_scroll = tk.Scrollbar(list_panel, orient=tk.HORIZONTAL)
        list_box = tk.Listbox(
            list_panel,
            yscrollcommand=v_scroll.set,
            xscrollcommand=h_scroll.set,
            font=("微软雅黑", 11),
            bd=8,
            relief=tk.FLAT,
            highlightthickness=0,
            activestyle="dotbox",
            fg="blue",
        )
        list_box.bind('<Double-Button-1>', lambda e: confirm_choose())
        v_scroll.config(command=list_box.yview)
        h_scroll.config(command=list_box.xview)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        list_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        for item in choices:
            list_box.insert(tk.END, item)

        def auto_timeout():
            nonlocal is_auto
            is_auto = True
            if root.winfo_exists():
                target_code = shared_data.default_tscode
                target_idx = None
                for i, text in enumerate(choices):
                    if text.startswith(f"{target_code}-"):
                        target_idx = i
                        break
                if target_idx is not None:
                    list_box.selection_clear(0, tk.END)
                    list_box.selection_set(target_idx)
                confirm_choose()

        timer_id = root.after(TIMEOUT_SEC * 1000, auto_timeout)

        def confirm_choose():
            nonlocal selected_val, timer_id, is_auto
            if timer_id is not None:
                root.after_cancel(timer_id)
                timer_id = None
            sel_idx = list_box.curselection()
            if sel_idx:
                selected_val = list_box.get(sel_idx[0])
                if is_auto:
                    print_context(f"程序自动输入选择品种的默认值：{selected_val}")
                else:
                    print_context(f"人工手动输入选择品种值：{selected_val}")
            root.destroy()

        def cancel_choose():
            nonlocal selected_val, timer_id
            if timer_id is not None:
                root.after_cancel(timer_id)
                timer_id = None
            selected_val = None
            root.destroy()

        btn_frame = tk.Frame(main_frame)
        btn_frame.pack(pady=(20, 0))
        tk.Button(btn_frame, text="确定", width=14, command=confirm_choose).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="取消", width=14, command=cancel_choose).pack(side=tk.LEFT, padx=10)

        root.mainloop()
        return selected_val

    selected_text = show_scroll_choicebox(
        title="选择品种",
        msg="请选择您要交易的期货商品品种！",
        choices=choices
    )
    if selected_text:
        parts = selected_text.split("-", maxsplit=2)
        code = parts[0].lower()
        trend = parts[1].lower()
        shared_data.ts_code = code
        shared_data.direction = trend
        with shared_data.variables_rlock:
            if code not in shared_data.quote_list:
                shared_data.quote_list.insert(0, code)
    else:
        print_context("没有选择合适的期货商品，程序已退出！")
        exit()

    try_nums = 0
    while True:
        input_value = get_direction()
        try_nums += 1
        if try_nums >= 3:
            print_context("交易方向不能为空，您已超过试错次，程序将自动退出！")
            exit()
        if not input_value:
            print_context(f"您没有确定交易方向，还有 {3-try_nums} 次选择机会！")
        else:
            shared_data.direction = input_value
            break

def set_stop_loss():
    win = tk.Tk()
    win.title("设置止盈止损")
    win.geometry("260x130")
    win.resizable(False, False)
    timer_id = None
    is_auto = False

    tk.Label(win, text="止盈值：").place(x=30, y=20)
    e1 = tk.Entry(win, width=15)
    e1.insert(0, "200")
    e1.place(x=90, y=20)
    tk.Label(win, text="止损值：").place(x=30, y=50)
    e2 = tk.Entry(win, width=15)
    e2.insert(0, "500")
    e2.place(x=90, y=50)

    def auto_timeout():
        nonlocal is_auto
        is_auto = True
        if win.winfo_exists():
            confirm()

    timer_id = win.after(TIMEOUT_SEC * 1000, auto_timeout)

    def confirm():
        nonlocal timer_id, is_auto
        if timer_id is not None:
            win.after_cancel(timer_id)
            timer_id = None
        try:
            lots = shared_data.tscode_lots_dict.get(shared_data.ts_code, 1)
            pre_profit = float(e1.get()) * lots
            pre_loss = -abs(float(e2.get())) * lots
            shared_data.pre_profit = pre_profit
            shared_data.pre_loss = pre_loss
            if is_auto:
                print_context(f"程序自动输入止盈止损的默认值：止盈{pre_profit}元，止损{pre_loss}元")
            else:
                print_context(f"人工手动输入止盈止损值：止盈{pre_profit}元，止损{pre_loss}元")
            win.destroy()
        except Exception:
            messagebox.showerror("错误", "请输入有效数字")

    def cancel():
        nonlocal timer_id
        if timer_id is not None:
            win.after_cancel(timer_id)
            timer_id = None
        win.destroy()
        print("请勿按取消按钮，否则程序将关闭应用等待重启！")

    def enter_submit(event):
        confirm()

    def e1_switch_e2(event):
        e2.focus_set()
        e2.select_range(0, tk.END)

    e1.bind("<Return>", e1_switch_e2)
    e2.bind("<Return>", enter_submit)
    win.bind("<Return>", enter_submit)

    btn_ok = tk.Button(win, text="确定", width=7, command=confirm)
    btn_ok.place(x=50, y=85)
    tk.Button(win, text="取消", width=7, command=cancel).place(x=130, y=85)

    win.focus_force()
    e1.focus_set()
    e1.select_range(0, tk.END)
    win.mainloop()

def set_lot_size():
    win = tk.Tk()
    win.title("设置交易手数")
    win.geometry("240x110")
    win.resizable(False, False)
    timer_id = None
    is_auto = False

    tk.Label(win, text="交易手数(1~10)：").place(x=22, y=22)
    entry = tk.Entry(win, width=12)
    entry.insert(0, "1")
    entry.place(x=110, y=22)

    lot_result = None

    def auto_timeout():
        nonlocal is_auto
        is_auto = True
        if win.winfo_exists():
            confirm()

    timer_id = win.after(TIMEOUT_SEC * 1000, auto_timeout)

    def confirm():
        nonlocal lot_result, timer_id, is_auto
        if timer_id is not None:
            win.after_cancel(timer_id)
            timer_id = None
        try:
            val = int(entry.get().strip())
            if 1 <= val <= 10:
                lot_result = val
                if is_auto:
                    print_context(f"程序自动输入交易手数的默认值：{lot_result}手")
                else:
                    print_context(f"人工手动输入交易手数值：{lot_result}手")
                win.destroy()
            else:
                messagebox.showerror("输入错误", "手数必须是1~10之间整数！")
        except ValueError:
            messagebox.showerror("输入错误", "请输入整数！")

    def cancel():
        nonlocal lot_result, timer_id
        if timer_id is not None:
            win.after_cancel(timer_id)
            timer_id = None
        lot_result = None
        win.destroy()

    def enter_submit(event):
        confirm()

    entry.bind("<Return>", enter_submit)
    win.bind("<Return>", enter_submit)

    tk.Button(win, text="确定", width=7, command=confirm).place(x=40, y=70)
    tk.Button(win, text="取消", width=7, command=cancel).place(x=120, y=70)

    win.focus_force()
    entry.focus_set()
    entry.select_range(0, tk.END)

    win.mainloop()

    if lot_result == 1 or lot_result is None:
        lot_result = shared_data.default_lots_dict.get(shared_data.ts_code[:-4], 1)
        shared_data.tscode_lots_dict.update({shared_data.ts_code: lot_result})
        print_context(f"✅ 程序已使用期货券商的默认交易手数：{lot_result}手")
        return lot_result
    else:
        shared_data.tscode_lots_dict.update({shared_data.ts_code: lot_result})
        print_context(f"✅ 已设置交易手数：{lot_result}手")
        return lot_result




def init_shared_data(user_type, ts_code, target_days, trade_futures_list, get_price_interval=5):
    # sound_order()
    print_context("程序正在校验日期、时间 ······")
    sync_time()
    shared_data.user_type = user_type
    shared_data.logger = setup_trade_loggers()
    log = shared_data.logger
    log.info("开始初始化交易程序", extra={"trace_id": "INT"})

    shared_data.open_price = None  # 初始化开盘价容器

    merge_two_info_dict()
    select_future()  # 选择交易的期货品种
    set_lot_size()   # 【新增】弹出手数输入框
    set_stop_loss()  # 设置期货品种的固定止损止盈值
    shared_data.target_days = target_days
    shared_data.quote_list = trade_futures_list
    # if ts_code in trade_futures_list:
    #     shared_data.ts_code = ts_code
    # else:
    #     shared_data.ts_code = trade_futures_list[0]  # 默认第一个为交易品种，如有改变再在交易窗口中切换
    shared_data.get_price_interval = get_price_interval  # 获取即时行情价格的时间间隔
    clean_old_trade_db(dry_run=False)
    fetch_future_data()
    check_ths_status()  # 检查同花顺期货通启动状态


def main():
    # 【关键：开启全局异常捕获】
    sys.excepthook = global_exception_handler
    import atexit
    import signal

    def exit_clean():
        print("\n🛑 程序触发退出，正在落地行情缓存...")
        try:
            flush_remain_buffer()
            print("✅ 缓存全部写入数据库完成")
        except Exception as e:
            print(f"❌ 缓存落库异常: {e}")

    atexit.register(exit_clean)
    # 注册日志队列关闭，刷盘
    atexit.register(stop_queue_listener)

    def signal_handler(signum, frame):
        print(f"\n⚠️ 收到系统信号 {signum}，执行缓存落库")
        exit_clean()
        stop_queue_listener()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, signal_handler)

    # ========== 初始化，挂载logger到shared_data ==========
    init_shared_data(user_type=0,
                     target_days=15,
                     ts_code="",
                     get_price_interval=5,
                     trade_futures_list=["m2701", "c2701"])

    # 定义所有线程
    price_thread = threading.Thread(target=get_current_price, name="PriceThread", daemon=True)
    order_thread = threading.Thread(target=order, name="OrderThread", daemon=True)
    monitor_thread = threading.Thread(target=monitor_profit_loss, name="MonitorThread", daemon=True)
    reget_open_price_thread = threading.Thread(target=reget_open_price, name="ReGetOpenPriceThread", daemon=True)
    anti_thread = threading.Thread(target=main_daemon, name="AntiThread", daemon=True)
    watchdog = threading.Thread(target=ths_watchdog, name="WatchdogThread", daemon=True)
    # 统一全部start，消除时序分散问题
    price_thread.start()
    order_thread.start()
    monitor_thread.start()
    reget_open_price_thread.start()
    anti_thread.start()
    # watchdog.start()
    print_context(f"✅ 所有量化交易线程启动成功 >>>\n"
                  f"获取期货品种即时行情线程-collect_current_price(PriceThread)\n"
                  f"订单线程-trade.order(OrderThread)\n"
                  f"自动交易监控线程-monitor.monitor(MonitorThread)\n"
                  f"开仓价重取线程-ReGetOpenPriceThread\n"
                  f"守护任务线程-AntiThread")

    # ===== 新增：开盘价获取放到独立子线程，休市等待不再阻塞主线程 =====
    open_price_thread = threading.Thread(target=get_open_price, name="OpenPriceThread", daemon=True)
    open_price_thread.start()
    print_context("✅ 开盘价获取线程 OpenPriceThread 已启动（休市等待在子线程执行，不阻塞主线程）")

    # 把线程放到列表里方便后续模块调用查看线程的存活状态
    shared_data.thread_list = []
    shared_data.thread_list.extend([
        price_thread,
        order_thread,
        monitor_thread,
        reget_open_price_thread,
        anti_thread,
        open_price_thread
    ])

    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        flush_remain_buffer()
        print_context("\n🛑 程序已手动停止")


if __name__ == "__main__":
    main()
    # select_future()