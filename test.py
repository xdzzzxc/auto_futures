def select_future():
    futures_info_dict = query_future_info()
    choices = []
    code_map = {}

    for code, (trend, info) in futures_info_dict.items():
        display_text = f"{code}-{trend}-{info}"
        choices.append(display_text)
        code_map[display_text] = (code, trend)

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