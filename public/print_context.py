import inspect


class Color:
    # 文字颜色
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    PURPLE = '\033[35m'
    CYAN = '\033[36m'
    # 重置颜色（必须加，否则后续输出都会带颜色）
    RESET = '\033[0m'


def print_context(content=None):
    """
    带上下文信息的打印函数（新增行号输出）
    :param content: 要打印的核心内容
    """
    # 获取调用该函数的上一级栈帧
    frame = inspect.currentframe().f_back

    # 获取模块文件名（兼容Windows/Linux路径）
    file_path = frame.f_code.co_filename
    file_name = file_path.split("\\")[-1] if "\\" in file_path else file_path.split("/")[-1]

    # 获取函数名（主程序显示<主程序>）
    func_name = frame.f_code.co_name if frame.f_code.co_name != "<module>" else " 主程序"

    # 新增：获取调用print_context()语句所在的行号
    line_num = frame.f_lineno

    # 格式化打印（新增行号 {line_num}）
    print(f"{Color.GREEN}{file_name} (module) {Color.YELLOW}{func_name} (function) {Color.RED}(line) {line_num}\n{Color.BLUE}>>> {content}{Color.RESET}")


if __name__ == "__main__":
    print_context()
