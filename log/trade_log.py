import logging
import os
import sys
from logging.handlers import RotatingFileHandler, QueueHandler, QueueListener
import queue
import threading
from typing import Optional

from public import shared_data

# ====================== 常量配置区，后续可迁移到YAML ======================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "log")
MAX_LOG_SIZE = 5 * 1024 * 1024  # 单个日志文件最大 5MB
BACKUP_COUNT = 20  # 保留归档日志数量
CONSOLE_COLOR_ENABLE: bool = sys.platform != "win32"  # Windows默认关闭彩色，避免乱码
# ========================================================================

# 全局缓存 + 线程锁，防止多线程并发初始化logger
_logger_cache: dict[str, logging.Logger] = {}
_cache_lock = threading.Lock()

# 全局异步日志队列与监听器（单例，所有logger共用）
_log_queue = queue.Queue(-1)
_queue_listener: Optional[QueueListener] = None


class TraceIdFilter(logging.Filter):
    """
    日志Filter：如果record没有trace_id，自动填充 "-"
    挂载到handler，保证格式化时一定是字符串，不会是None
    """
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "trace_id") or record.trace_id is None:
            record.trace_id = "-"
        return True


def _start_queue_listener():
    """启动全局异步日志队列监听器，进程内只启动一次"""
    global _queue_listener
    if _queue_listener is None:
        _queue_listener = QueueListener(_log_queue)
        _queue_listener.start()


def _stop_queue_listener():
    global _queue_listener
    if _queue_listener is not None and _queue_listener._thread is not None:
        _queue_listener.stop()


def setup_trade_loggers(level: int = logging.INFO) -> logging.Logger:
    """
    配置交易日志器，区分模拟盘/实盘，返回单例日志对象，使用异步队列写文件不阻塞主线程

    :param level: 日志级别 logging.DEBUG / INFO / WARNING / ERROR
    :return: 日志器实例
    """
    os.makedirs(LOG_DIR, exist_ok=True)
    user_type = shared_data.user_type

    def _setup_single_logger(logger_name: str, log_file: str):
        # 加锁，防止多线程并发创建同一个logger
        with _cache_lock:
            if logger_name in _logger_cache:
                return _logger_cache[logger_name]

            logger = logging.getLogger(logger_name)
            logger.setLevel(level)
            logger.propagate = False
            logger.handlers.clear()  # 兜底清理旧handler

            # 启动异步日志队列
            _start_queue_listener()
            trace_filter = TraceIdFilter()

            # ---------------------- 文件日志格式 ----------------------
            file_fmt = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(filename)s[%(lineno)d] %(funcName)s - trace_id=%(trace_id)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )

            # 真实文件handler，交给异步队列消费
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=MAX_LOG_SIZE,
                backupCount=BACKUP_COUNT,
                encoding='utf-8'
            )
            file_handler.setFormatter(file_fmt)
            file_handler.addFilter(trace_filter)  # 挂载到文件handler

            # QueueListener 监听的handlers列表
            # QueueListener会在后台线程，使用这些handlers输出日志
            _queue_listener.handlers = [file_handler]

            # QueueHandler：日志先丢进队列，主线程不阻塞IO
            queue_handler = QueueHandler(_log_queue)
            logger.addHandler(queue_handler)

            # ---------------------- 控制台Handler ----------------------
            if CONSOLE_COLOR_ENABLE:
                console_fmt = logging.Formatter(
                    '\033[33m%(asctime)s\033[0m \033[31m%(levelname)s\033[0m %(filename)s:%(lineno)d \n>>> \033[32m%(message)s\033[0m',
                    datefmt='%H:%M:%S'
                )
            else:
                # Windows无颜色版本
                console_fmt = logging.Formatter(
                    '%(asctime)s %(levelname)s %(filename)s:%(lineno)d >>> %(message)s',
                    datefmt='%H:%M:%S'
                )
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(console_fmt)
            console_handler.addFilter(trace_filter) # 控制台也挂载filter
            logger.addHandler(console_handler)

            _logger_cache[logger_name] = logger
            return logger

    if user_type == 0:
        return _setup_single_logger('simulation_user', os.path.join(LOG_DIR, 'simulation_user_trade.log'))
    else:
        return _setup_single_logger('futures_user', os.path.join(LOG_DIR, 'futures_user_trade.log'))


def read_log(user_type: int = 0, last_lines: int = 0) -> None:
    """
    读取日志文件，优化大文件读取，last_lines>0时只读取尾部N行，不加载整个文件到内存

    :param user_type: 0模拟盘，1实盘
    :param last_lines: 需要读取末尾行数，0=读取全部
    """
    log_file_map = {0: "simulation_user_trade.log", 1: "futures_user_trade.log"}
    log_name = log_file_map.get(user_type, "simulation_user_trade.log")
    log_path = os.path.join(LOG_DIR, log_name)

    if not os.path.exists(log_path):
        print(f"日志文件不存在：{log_path}")
        return

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            if last_lines <= 0:
                content = f.read()
            else:
                # 大文件尾部读取，避免一次性加载全部日志
                buffer: list[str] = []
                for line in f:
                    buffer.append(line)
                    if len(buffer) > last_lines:
                        buffer.pop(0)
                content = "".join(buffer)

        print("========== 日志内容 ==========")
        print(content)
    except Exception as e:
        print(f"读取日志失败：{e}")




# def global_exception_handler(exc_type, exc_value, exc_traceback):
#     """全局未捕获异常钩子，将崩溃异常写入日志"""
#     if issubclass(exc_type, KeyboardInterrupt):
#         sys.__excepthook__(exc_type, exc_value, exc_traceback)
#         return
#     logger = setup_trade_loggers(logging.ERROR)
#     logger.critical("未捕获全局异常", exc_info=(exc_type, exc_value, exc_traceback))


# 注册全局异常捕获
# sys.excepthook = global_exception_handler
# 上面注册全局异常捕获放在main.py模块然后再以公共变量方式放在shared_data中
# 对外公共接口，给main调用，规避私有函数导入警告
def stop_queue_listener():
    _stop_queue_listener()

# ---------------------- 使用示例 ----------------------
if __name__ == "__main__":
    # 获取日志器，原有调用方式完全不变
    log = setup_trade_loggers(logging.INFO)

    # ✅ 正常使用，extra 传入 trace_id
    extra = {"trace_id": "T20260916001"}
    log.info("策略信号触发，contract=m2611 volume=1", extra=extra)
    try:
        1 / 0
    except Exception:
        log.exception("执行发生异常", extra=extra)

    # 不传extra，自动填充 trace_id="-"
    log.info("普通日志，不带trace_id")

    # 读取最后10行日志
    read_log(user_type=0, last_lines=10)

    # 程序退出前调用，刷完异步队列剩余日志
    import atexit
    atexit.register(_stop_queue_listener)
