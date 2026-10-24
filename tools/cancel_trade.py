from pywinauto import mouse


def cancel_trade(rect = (539, 948, 20, 18)):
    x, y, w, h = rect
    center_x = x + w // 2
    center_y = y + h // 2
    mouse.click(button="left", coords=(center_x, center_y))

if __name__ == '__main__':
    cancel_trade()