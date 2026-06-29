import tkinter as tk
from tkinter import messagebox
from public import shared_data

def set_stop_loss():
    win = tk.Tk()
    win.title("设置止盈止损")
    win.geometry("260x130")
    win.resizable(False, False)

    # 默认值0
    tk.Label(win, text="止盈值：").place(x=30, y=20)
    e1 = tk.Entry(win, width=15)
    e1.insert(0, "0")
    e1.place(x=90, y=20)

    tk.Label(win, text="止损值：").place(x=30, y=50)
    e2 = tk.Entry(win, width=15)
    e2.insert(0, "0")
    e2.place(x=90, y=50)

    def confirm():
        try:
            shared_data.pre_profit = float(e1.get())
            shared_data.pre_loss = float(e2.get())
            win.destroy()
        except Exception as e:  # noqa
            messagebox.showerror("错误", "请输入有效数字")

    def cancel():
        win.destroy()

    tk.Button(win, text="确定", width=7, command=confirm).place(x=50, y=85)
    tk.Button(win, text="取消", width=7, command=cancel).place(x=130, y=85)

    win.mainloop()

if __name__ == '__main__':
    set_stop_loss()