from pynput import mouse
import sys

def on_mouse_move(x, y):
    # \r 回到行首，覆盖原有内容，end="" 不自动换行
    sys.stdout.write(f"\r当前鼠标坐标 X: {x}, Y: {y}")
    sys.stdout.flush()

def track_mouse():
    listener = mouse.Listener(on_move=on_mouse_move)
    print("鼠标坐标监听已启动，移动鼠标查看坐标，按 Ctrl+C 退出\n")
    listener.start()
    try:
        while True:
            input()
    except KeyboardInterrupt:
        listener.stop()
        print("\n\n监听已关闭")

if __name__ == "__main__":
    track_mouse()