import os
import sqlite3
import pandas as pd
import time  # ← 新增：重试延时用
from functools import wraps  # ← 新增：装饰器用
from public import print_context
from public.jiaoyisuo import get_future_info
from datetime import datetime, timedelta
import threading  # ← 新增：全局锁用

TABLE_MAX_ROWS = 100000

# 1. 全局数据库锁（最稳妥的串行化保障）
_db_lock = threading.Lock()

# 2. 锁冲突重试装饰器
def _retry_on_lock(max_retries=5, delay=0.3):
    """数据库锁自动重试"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for i in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e):
                        time.sleep(delay * (i + 1))
                        continue
                    raise
            print_context.print_context(f"重试{max_retries}次仍被锁定，放弃")
            return None
        return wrapper
    return decorator
# ====================== 新增结束 ======================

# 目录初始化
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db_folder = os.path.join(BASE_DIR, r"futures_data\db")
os.makedirs(db_folder, exist_ok=True)

def get_short_code(full_ts_code: str) -> str:
    return full_ts_code[:-4]

def get_db_path(full_ts_code: str) -> str:
    short_code = get_short_code(full_ts_code)
    return os.path.join(db_folder, f"{short_code}.db")

def init_table(db_path: str):
    # 严格非空约束，从表结构层面禁止空值
    create_sql = """
    CREATE TABLE IF NOT EXISTS price_data (
        record_time TEXT PRIMARY KEY NOT NULL,
        price REAL NOT NULL,
        ts_code TEXT NOT NULL
    )
    """
    with sqlite3.connect(db_path, timeout=10) as conn:  # ← 修改：加超时10秒
        # ====================== 新增开始：开启WAL模式 ======================
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA cache_size = -2000;")
        # ====================== 新增结束 ======================
        conn.execute(create_sql)

def trim_old_data(db_path: str):
    with _db_lock:  # ← 新增：加锁
        with sqlite3.connect(db_path, timeout=10) as conn:  # ← 修改：加超时
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM price_data")
            total = cur.fetchone()[0]
            if total > TABLE_MAX_ROWS:
                del_num = total - TABLE_MAX_ROWS
                del_sql = """
                DELETE FROM price_data
                WHERE record_time IN (
                    SELECT record_time FROM price_data ORDER BY record_time ASC LIMIT ?
                )
                """
                cur.execute(del_sql, (del_num,))

def write_price(price_list):
    # 1. 基础长度校验
    if len(price_list) != 3:
        print_context.print_context("参数长度错误")
        return

    record_time, price, ts_code = price_list
    # 2. 去除首尾空白 + 非空校验
    record_time = str(record_time).strip()
    ts_code = str(ts_code).strip()

    if not record_time or not ts_code:
        print_context.print_context("时间/合约码为空，跳过入库")
        return

    # 3. 价格类型校验
    try:
        price = float(str(price).strip())
    except (ValueError, TypeError):
        print_context.print_context("价格格式错误，跳过入库")
        return

    db_path = get_db_path(ts_code)
    try:
        init_table(db_path)
        insert_sql = "INSERT INTO price_data (record_time, price, ts_code) VALUES (?, ?, ?)"
        with _db_lock:  # ← 新增：加锁
            with sqlite3.connect(db_path, timeout=10) as conn:  # ← 修改：加超时
                conn.execute(insert_sql, (record_time, price, ts_code))
        trim_old_data(db_path)
    except sqlite3.IntegrityError:
        print_context.print_context(f"主键 {record_time} 已存在，本次保存数据失败！")
    except Exception as e:
        print_context.print_context(f"入库异常：{e}")


@_retry_on_lock()  # ← 新增：重试装饰器
def read_db(full_ts_code, start_time=None, end_time=None, counts=None, ascending=False):
    """
    读取合约数据并转为DataFrame
    :param full_ts_code: 完整合约代码，如 m2609
    :param start_time: 起始时间(字符串，格式: YYYYMMDDHHMMSS)，不传则不限制
    :param end_time: 结束时间(字符串，格式: YYYYMMDDHHMMSS)，不传则不限制
    :param ascending: 排序，True=时间正序，False=时间倒序
    :counts: 记录数
    :return: DataFrame / None
    """
    # 拼接库路径
    short_code = full_ts_code[:-4]
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), r"futures_data\db", f"{short_code}.db")

    if not os.path.exists(db_path):
        print_context.print_context(f"No filepath:{db_path}")
        return None
    current_hour = datetime.now().hour
    is_night = get_future_info(short_code).get('night_trading', False)

    if start_time is None:
        if is_night:
            if current_hour < 21:
                # 21点前：从昨日21点开始
                start_dt = datetime.today() - timedelta(days=1)
            else:
                # 21点及之后：从今日21点开始
                start_dt = datetime.today()
            start_time = start_dt.strftime("%Y%m%d") + "210000"
        else:
            # 无夜盘，默认今日09点
            start_time = datetime.today().strftime("%Y%m%d") + "090000"
    # 拼接SQL + 时间筛选条件
    base_sql = "SELECT * FROM price_data"
    conds = []
    params = []
    conds.append("ts_code = ?")
    params.append(full_ts_code)
    if start_time:
        conds.append("record_time >= ?")
        params.append(start_time)
    if end_time:
        conds.append("record_time <= ?")
        params.append(end_time)
    if conds:
        base_sql += " WHERE " + " AND ".join(conds)

    # 排序
    order = "ORDER BY record_time ASC" if ascending else "ORDER BY record_time DESC"
    sql = f"{base_sql} {order}"

    try:
        with _db_lock:  # ← 新增：加锁
            with sqlite3.connect(db_path, timeout=10) as conn:  # ← 修改：加超时
                df = pd.read_sql(sql, conn, params=params)

        # 字符串时间转为标准时间格式，新增一列便于分析
        df["dt"] = pd.to_datetime(df["record_time"], format="%Y%m%d%H%M%S")
        if counts and isinstance(counts, int) and counts > 0:
            df = df.head(counts)
        return df
    except Exception:
        return None


def manual_start_wal(db_folder_path:str = db_folder):
    """
    给所有已存在的数据库手动开启 WAL
    """
    for filename in os.listdir(db_folder_path):
        if filename.endswith(".db"):
            db_path = os.path.join(db_folder_path, filename)
            conn = sqlite3.connect(db_path)

            # 开启 WAL
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")

            # 验证是否开启成功
            result = conn.execute("PRAGMA journal_mode;").fetchone()
            print(f"{filename}: {result[0]}")  # 应该输出 wal

            conn.commit()
            conn.close()

    print("全部处理完成！")

if __name__ == '__main__':
    # 测试用例，正常插入
    price_list = ["20260613000237", 4525, "m2607"]
    write_price(price_list)
    df1 = read_db(full_ts_code="m2607", start_time="20260613000200", end_time=None, counts=2, ascending=False)
    print(df1)
