from datetime import datetime
import threading
from time import sleep
from public import shared_data
from public.jiaoyisuo import futures_info
import re
from public.print_context import print_context
from core.connect_ths import run_ths
from core.trade import order
from log.trade_log import setup_trade_loggers
from data.collect_current_price import get_current_price
from data.future_trend import query_future_info
import tkinter as tk
from tkinter import ttk
from data.excel import monitor_trade
from data.data_from_sina import fetch_future_data
from public.sync_time import sync_time
from core.trade import monitor_profit_loss
from data.get_quote import get_open_price
from public.anti_screensaver import anti_screensaver_thread


def get_direction(title="交易方向", msg=None) -> str | None:
    default_dir = shared_data.direction
    if msg is None:
        msg = (f"金投网推荐[{shared_data.ts_code}]: {'暂无推荐' if not shared_data.direction else shared_data.direction}"
               f"\n要变更交易方向，请手动选择！")
    OPTIONS = ["Rise", "Fall", "Sideways", "Cautious", "Ease"]

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

    def ok():
        nonlocal result
        result = selected_dir.get().strip()
        shared_data.direction = result
        root.destroy()

    def cancel():
        nonlocal result
        result = None
        root.destroy()

    root.bind("<Return>", lambda e: ok())
    root.bind("<Escape>", lambda e: cancel())

    btn_frame = ttk.Frame(frame)
    btn_frame.pack(anchor="e", pady=4)
    ttk.Button(btn_frame, text="确定", command=ok, width=6).pack(side=tk.LEFT, padx=5)
    ttk.Button(btn_frame, text="取消", command=cancel, width=6).pack(side=tk.LEFT)

    root.mainloop()
    # print_context(f"今天期货交易参数列表：\n期货品种：{shared_data.ts_code}, \n交易方向：{shared_data.direction}\n"
    #               f"今日开盘：{shared_data.open_price}\n等待程序启动同花顺期货通 ······")
    return result


def show_custom_choicebox(choices, title="选择品种", msg="请选择期货品种") -> str | None:
    selected = None

    def on_ok():
        nonlocal selected
        if listbox.curselection():
            selected = listbox.get(listbox.curselection())
        win.destroy()

    def on_cancel():
        nonlocal selected
        selected = None
        win.destroy()

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
    listbox.pack(padx=18, pady=6, fill=tk.BOTH, expand=True)

    if choices:
        listbox.selection_set(0)

    listbox.bind("<Double-1>", lambda event: on_ok())

    btn_frame = ttk.Frame(win)
    btn_frame.pack(pady=12)

    ok_btn = ttk.Button(btn_frame, text="OK", command=on_ok, width=10)
    ok_btn.pack(side=tk.LEFT, padx=14)

    cancel_btn = ttk.Button(btn_frame, text="Cancel", command=on_cancel, width=10)
    cancel_btn.pack(side=tk.LEFT, padx=14)

    win.mainloop()
    return selected

def select_future():
    futures_info_dict = query_future_info()
    choices = []
    code_map = {}

    # 1. 先加载资讯里的品种
    for code, (trend, info) in futures_info_dict.items():
        display_text = f"{code}-{trend}-{info}"
        choices.append(display_text)
        code_map[display_text] = (code, trend)

    # ====================== 【核心：强制加入你的必备品种】 ======================
    # 不管资讯有没有，这几个必须出现在选择框里
    from public import shared_data
    required_contracts = shared_data.quote_list  # ["m2609", "c2609", "jd2609"]

    # 默认趋势（如果资讯里没有，就给一个默认值）
    default_trend = "Sideways"

    for code in required_contracts:
        # 构造显示文本
        display_text = f"{code}-{default_trend}-必备品种"

        # 如果已经存在，就不重复添加
        if display_text not in choices:
            choices.append(display_text)
            code_map[display_text] = (code, default_trend)
    # ==========================================================================

    def show_scroll_choicebox(title, msg, choices) -> str | None:
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

        selected_val = None

        def confirm_choose():
            nonlocal selected_val
            sel_idx = list_box.curselection()
            if sel_idx:
                selected_val = list_box.get(sel_idx[0])
            root.destroy()

        def cancel_choose():
            nonlocal selected_val
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
        parts = selected_text.split("-")
        code = parts[0]
        trend = parts[1]
        shared_data.ts_code = code
        shared_data.direction = trend
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

def _init_shared_data(user_type, target_days, lot_size):
    print_context("程序正在校验日期、时间 ······")
    sync_time()
    shared_data.user_type = user_type
    shared_data.logger = setup_trade_loggers()
    select_future()
    ts_code = shared_data.ts_code
    # print_context(f"您已选择的期货品种： {ts_code}")
    shared_data.target_days = target_days
    shared_data.lot_size = lot_size
    prefix = re.match(r'[a-zA-Z]+', ts_code).group()
    shared_data.min_price_change = futures_info[prefix]['min_price_change']
    get_open_price()
    # 加入新浪历史交易数据
    analysis_data, fut_data = fetch_future_data(ts_code=shared_data.ts_code)
    shared_data.history_data_analysis = analysis_data
    # print_context(f'新浪网历史数据 - 期货交易品种 >>> {shared_data.ts_code}\n{shared_data.history_data_analysis}')
    # exit()
    run_ths()


if __name__ == "__main__":
    _init_shared_data(
        user_type=0,
        target_days=5,
        lot_size=1
    )

    # ========== 启动核心线程（daemon=True 安全退出）==========
    price_thread = threading.Thread(target=get_current_price, name="PriceThread", daemon=True)
    order_thread = threading.Thread(target=order, name="OrderThread", daemon=True)
    monitor_thread = threading.Thread(target=monitor_profit_loss, name="MonitorThread", daemon=True)

    price_thread.start()
    order_thread.start()
    sleep(5)
    monitor_thread.start()

    print_context("✅ 所有交易线程启动成功，程序运行中...")
    anti_screensaver_thread()
    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        print_context("\n🛑 程序已手动停止")