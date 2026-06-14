import inspect
import os
from typing import Optional


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
            print(f"{Color.RED}无法获取调用上下文{Color.RESET}")
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
        print(msg)

    except Exception as e:
        print(f"打印上下文异常: {e}")
    finally:
        # 关键：手动释放栈帧，避免内存累积
        if frame:
            del frame



# 测试
if __name__ == "__main__":
    print_context("测试普通内容")
    print_context()  # 空内容测试
