import inspect
import os
import sys
from typing import Optional


# Windows开启ANSI VT100颜色支持
def _init_ansi_color():
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        std_handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint()
        kernel32.GetConsoleMode(std_handle, ctypes.byref(mode))
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        if not (mode.value & ENABLE_VIRTUAL_TERMINAL_PROCESSING):
            kernel32.SetConsoleMode(std_handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)


# 程序启动执行一次颜色初始化
_init_ansi_color()


class Color:
    # 文字颜色 ANSI 转义码
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    PURPLE = '\033[35m'
    CYAN = '\033[36m'
    RESET = '\033[0m'


def print_context(content: Optional[str] = "") -> None:
    """
    带代码上下文、彩色的增强打印函数
    :param content: 打印内容，默认为空字符串
    """
    frame = None
    try:
        # 获取上层调用栈帧
        frame = inspect.currentframe().f_back
        if not frame:
            print(f"{Color.RED}无法获取调用上下文{Color.RESET}", flush=True)
            return

        # 标准跨平台获取纯文件名（替代手动分割路径）
        file_name = os.path.basename(frame.f_code.co_filename)

        # 函数名处理
        func_name = frame.f_code.co_name
        if func_name == "<module>":
            func_name = "主程序"

        # 调用行号
        line_num = frame.f_lineno

        # 紧凑格式输出（不再多余换行）
        prefix = (
            f"{Color.GREEN}{file_name} "
            f"{Color.YELLOW}[{func_name}] "
            f"{Color.RED}行:{line_num}{Color.RESET}"
        )
        msg = f"{prefix} \n>>> {Color.BLUE}{content}{Color.RESET}"
        # 关键：flush=True，子线程强制刷新输出缓冲区
        print(msg, flush=True)

    except Exception as e:
        print(f"打印上下文异常: {e}", flush=True)
    finally:
        # 关键：手动释放栈帧，避免内存累积
        if frame:
            del frame


# 测试
if __name__ == "__main__":
    print_context("测试普通内容")
    print_context()  # 空内容测试

    # 模拟子线程测试
    import threading
    def thread_test():
        print_context("【子线程测试】如果能看到这条，修复成功")
    t = threading.Thread(target=thread_test)
    t.start()
    t.join()
