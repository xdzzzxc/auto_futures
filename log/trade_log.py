import logging
import os
from logging.handlers import RotatingFileHandler
from public import shared_data


def setup_trade_loggers(level=logging.INFO):
    """
    配置并返回两个交易相关的日志器（模拟用户、期货用户）
    :param level: 日志级别，默认INFO
    :return: simulation_logger, futures_logger 两个日志器对象
    """
    # 创建log文件夹（如果不存在）
    user_type = shared_data.user_type
    log_dir = "log"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)  # 加exist_ok=True防止多线程创建报错

    # 定义通用日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    def _setup_single_logger(logger_name, log_file):
        """内部辅助函数：配置单个日志器"""
        # 创建日志器
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        logger.propagate = False  # 防止日志重复输出

        # 避免重复添加处理器
        if logger.handlers:
            return logger

        # 创建文件处理器（设置日志文件大小限制和备份数量）
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=20,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)

        # 配置控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level)

        # 添加处理器到日志器
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        return logger

    # ========== 核心修正：路径拼接去掉多余的'log' ==========
    if user_type == 0:
        simulation_logger = _setup_single_logger(
            'simulation_user',
            os.path.join(log_dir, 'simulation_user_trade.log')  # 正确路径：log/simulation_user_trade.log
        )
        return simulation_logger
    else:
        futures_logger = _setup_single_logger(
            'futures_user',
            os.path.join(log_dir, 'futures_user_trade.log')     # 正确路径：log/futures_user_trade.log
        )
        return futures_logger
    # 返回两个日志器
    # return simulation_logger, futures_logger


# 调用示例
if __name__ == "__main__":
    # 获取日志器
    log = setup_trade_loggers(user_type=0)  # user_type=1表示期货用户
    # 测试输出
    log.info("用户日志测试 - 路径已修正")
    log.error("用户错误日志测试")
