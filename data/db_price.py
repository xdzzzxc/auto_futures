import os
from public import shared_data
import sqlite3
import pandas as pd
import time
from functools import wraps
from public import print_context
from public.jiaoyisuo import get_future_info
from datetime import datetime, timedelta
from public.shared_data import get_data_cache_dir
import threading

TABLE_MAX_ROWS = 100000
# 全局数据库锁
_db_lock = threading.Lock()

# 锁冲突重试装饰器
def _retry_on_lock(max_retries=5, delay=0.3):
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

# 目录初始化
BASE_DIR = get_data_cache_dir()
# print(f"BASE_DIR: {BASE_DIR}")
db_folder = os.path.join(BASE_DIR, "db")
os.makedirs(db_folder, exist_ok=True)

def get_short_code(full_ts_code: str) -> str:
    return full_ts_code[:-4]

def get_write_db_paths() -> list[str]:
    """
    判断当前时间，返回需要写入的数据库路径列表
    <21点：仅今日库；≥21点：今日库、次日库两个路径
    """
    now = datetime.now()
    current_hour = now.hour
    today_str = now.strftime("%Y%m%d")
    next_day_str = (now + timedelta(days=1)).strftime("%Y%m%d")

    paths = [os.path.join(db_folder, f"{today_str}.db")]

    # 无论几点，始终包含今日库
    # 21点后追加次日库，实现双库保存
    if current_hour >= 21:
        paths.append(os.path.join(db_folder, f"{next_day_str}.db"))
    return paths

# 按当日日期生成统一数据库文件 YYYYMMDD.db
def get_db_path(full_ts_code: str) -> str:
    now = datetime.now()
    current_hour = now.hour
    if current_hour >= 21:
        # 21点后写入次日日期db
        target_str = (now + timedelta(days=1)).strftime("%Y%m%d")
    else:
        # 21点前写入当日db
        target_str = now.strftime("%Y%m%d")
    return os.path.join(db_folder, f"{target_str}.db")

# 联合主键表结构
def init_table(db_path: str):
    create_sql = """
    CREATE TABLE IF NOT EXISTS price_data (
        record_time TEXT NOT NULL,
        price REAL NOT NULL,
        ts_code TEXT NOT NULL,
        PRIMARY KEY(record_time, ts_code)
    )
    """
    with sqlite3.connect(db_path, timeout=10) as conn:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA cache_size = -2000;")
        conn.execute(create_sql)

def trim_old_data(db_path: str):
    with _db_lock:
        with sqlite3.connect(db_path, timeout=10) as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM price_data")
            total = cur.fetchone()[0]
            if total > TABLE_MAX_ROWS + 5000:
                del_num = total - TABLE_MAX_ROWS
                del_sql = """
                DELETE FROM price_data
                WHERE record_time IN (
                    SELECT record_time FROM price_data ORDER BY record_time ASC LIMIT ?
                )
                """
                cur.execute(del_sql, (del_num,))
                conn.commit()

# def write_price(price_list):
#     if len(price_list) != 3:
#         print_context.print_context("参数长度错误")
#         return
#
#     record_time, price, ts_code = price_list
#     record_time = str(record_time).strip()
#     ts_code = str(ts_code).strip()
#
#     if not record_time or not ts_code:
#         print_context.print_context("时间/合约码为空，跳过入库")
#         return
#
#     try:
#         price = float(str(price).strip())
#     except (ValueError, TypeError):
#         print_context.print_context("价格格式错误，跳过入库")
#         return
#
#     db_path = get_db_path(ts_code)
#     try:
#         init_table(db_path)
#         insert_sql = "INSERT OR IGNORE INTO price_data (record_time, price, ts_code) VALUES (?, ?, ?)"
#         with _db_lock:
#             with sqlite3.connect(db_path, timeout=10) as conn:
#                 conn.execute(insert_sql, (record_time, price, ts_code))
#         trim_old_data(db_path)
#     except sqlite3.IntegrityError:
#         print_context.print_context(f"主键 {record_time} {ts_code} 已存在，本次保存数据失败！")
#     except Exception as e:
#         print_context.print_context(f"入库异常：{e}")

def batch_write_price(batch_list):
    # 先全局校验所有数据，过滤无效行
    valid_all = []
    for price_list in batch_list:
        if len(price_list) != 3:
            print_context.print_context("参数长度错误")
            continue

        record_time, price, ts_code = price_list
        record_time = str(record_time).strip()
        ts_code = str(ts_code).strip()

        if not record_time or not ts_code:
            print_context.print_context("时间/合约码为空，跳过入库")
            continue

        try:
            price_float = float(str(price).strip())
        except (ValueError, TypeError):
            print_context.print_context("价格格式错误，跳过入库")
            continue
        valid_all.append((record_time, price_float, ts_code))

    if not valid_all:
        return

    # 获取本次需要写入的所有库路径（21点=双库，其余单库）
    target_db_paths = get_write_db_paths()

    # 循环每个数据库，完整写入全部行情
    for db_path in target_db_paths:
        try:
            init_table(db_path)
            insert_sql = "INSERT OR IGNORE INTO price_data (record_time, price, ts_code) VALUES (?, ?, ?)"
            with _db_lock:
                with sqlite3.connect(db_path, timeout=10) as conn:
                    conn.executemany(insert_sql, valid_all)
            trim_old_data(db_path)
            print_context.print_context(f"✅ 批量写入完成：{db_path} 共{len(valid_all)}条")
        except Exception as e:
            print_context.print_context(f"批量入库异常 db:{db_path} err:{e}")

def flush_remain_buffer():
    """程序关闭/读库前刷新缓冲区"""
    with shared_data.buffer_lock:
        remain = shared_data.price_buffer.copy()
        shared_data.price_buffer.clear()
    if remain:
        batch_write_price(remain)

@_retry_on_lock()
def read_db(full_ts_code, start_time=None, end_time=None, counts=None, ascending=False):
    # 读取数据库前强制把内存缓存全部写入磁盘，保证数据完整
    flush_remain_buffer()

    base_db_folder = os.path.join(get_data_cache_dir(), "db")
    os.makedirs(base_db_folder, exist_ok=True)

    # 根据当前小时选择数据库文件
    now = datetime.now()
    current_hour = now.hour
    if current_hour >= 21:
        # 21点及以后，使用次日日期数据库
        target_db_date = (now + timedelta(days=1)).strftime("%Y%m%d")
    else:
        # 0~20点59分，使用今日数据库
        target_db_date = now.strftime("%Y%m%d")

    # 拼接数据库路径 YYYYMMDD.db
    db_path = os.path.join(base_db_folder, f"{target_db_date}.db")
    print_context.print_context(f"现在是夜场交易时段：{now.strftime('%Y%m%d %H:%M:%S')}，使用数据库文件：{db_path}")

    if not os.path.exists(db_path):
        print_context.print_context(f"No filepath:{db_path} (对应日期库不存在，无行情数据)")
        return None

    # 拼接查询语句
    base_sql = "SELECT * FROM price_data"
    conds = []
    params = []
    # 固定筛选品种
    conds.append("ts_code = ?")
    params.append(full_ts_code)

    # 有start_time才追加大于等于条件
    if start_time is not None:
        conds.append("record_time >= ?")
        params.append(start_time)
    # 有end_time才追加小于等于条件
    if end_time is not None:
        conds.append("record_time <= ?")
        params.append(end_time)

    if conds:
        base_sql += " WHERE " + " AND ".join(conds)

    # 排序
    order = "ORDER BY record_time ASC" if ascending else "ORDER BY record_time DESC"
    sql = f"{base_sql} {order}"
    # print_context.print_context(f"【调试】执行SQL：{sql} 参数:{params}")

    try:
        with sqlite3.connect(db_path, timeout=10) as conn:
            df = pd.read_sql(sql, conn, params=params)
        # print_context.print_context(f"【调试】查询返回原始行数：{len(df)}")
        df["dt"] = pd.to_datetime(df["record_time"], format="%Y%m%d%H%M%S")
        if counts and isinstance(counts, int) and counts > 0:
            df = df.head(counts)
        return df
    except Exception as e:
        print_context.print_context(f"读取数据库异常: {str(e)}")
        return None


def manual_start_wal(db_folder_path:str = db_folder):
    for filename in os.listdir(db_folder_path):
        if filename.endswith(".db"):
            db_path = os.path.join(db_folder_path, filename)
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            result = conn.execute("PRAGMA journal_mode;").fetchone()
            print(f"{filename}: {result[0]}")
            conn.commit()
            conn.close()
    print("全部处理完成！")

if __name__ == '__main__':
    df1 = read_db(full_ts_code="fu2609", start_time="20260727224600", end_time=None, counts=None, ascending=False)
    print(df1)
    get_write_db_paths()