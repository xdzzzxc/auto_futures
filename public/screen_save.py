import ctypes

def press_esc():
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    # 按下 ESC
    user32.keybd_event(0x1B, 0, 0, 0)
    # 松开 ESC
    user32.keybd_event(0x1B, 0, 2, 0)

if __name__ == "__main__":
    press_esc()