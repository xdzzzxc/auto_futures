import logging
import os
from logging.handlers import RotatingFileHandler
from public import shared_data

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
log_dir = os.path.join(BASE_DIR, "log")

# 全局缓存logger，避免重复初始化
_logger_cache = {}

def setup_trade_loggers(level=logging.INFO):
    """
    配置交易日志器，根据用户类型返回对应单例日志对象
    :param level: 日志级别
    :return: 日志器实例
    """
    os.makedirs(log_dir, exist_ok=True)
    user_type = shared_data.user_type

    def _setup_single_logger(logger_name, log_file):
        # 优先读缓存，彻底避免重复添加handler
        if logger_name in _logger_cache:
            return _logger_cache[logger_name]

        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        logger.propagate = False
        # 清空已有handler（兜底）
        logger.handlers.clear()

        # 文件日志格式
        file_fmt = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(filename)s[%(lineno)d] %(funcName)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=20,
            encoding='utf-8'
        )
        file_handler.setFormatter(file_fmt)

        # 控制台格式 + 颜色（级别区分色，消息绿色）
        console_fmt = logging.Formatter(
            '\033[33m%(asctime)s\033[0m \033[31m%(levelname)s\033[0m %(filename)s:%(lineno)d \n>>> \033[32m%(message)s\033[0m',
            datefmt='%H:%M:%S'
        )
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(console_fmt)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        _logger_cache[logger_name] = logger
        return logger

    if user_type == 0:
        return _setup_single_logger('simulation_user', os.path.join(log_dir, 'simulation_user_trade.log'))
    else:
        return _setup_single_logger('futures_user', os.path.join(log_dir, 'futures_user_trade.log'))


def read_log(user_type=0, last_lines: int = 0) -> None:
    log_file_map = {0: "simulation_user_trade.log", 1: "futures_user_trade.log"}
    log_name = log_file_map.get(user_type, "simulation_user_trade.log")
    log_path = os.path.join("log", log_name)
    if not os.path.exists(log_path):
        print(f"日志文件不存在：{log_path}")
        return

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if last_lines > 0:
            show_data = lines[-last_lines:] if len(lines) >= last_lines else lines
        else:
            show_data = lines

        print("========== 日志内容 ==========")
        print("".join(show_data))
    except Exception as e:
        print(f"读取日志失败：{e}")


# 调用示例
if __name__ == "__main__":
    # 获取日志器
    log = setup_trade_loggers()  # user_type=1表示期货用户
    # 测试输出
    log.info("用户日志测试 - 路径已修正")
    log.error("用户错误日志测试")
    read_log()
