from datetime import datetime
def show_date_time(code: int | None = None) -> str:
    """
    :param code: 0~6，不传/None 默认=5；非法code自动降级为5，仅打warning日志不抛异常
        0 → ymd              20261031
        1 → y-m-d            2026-10-31
        2 → h:m:s            09:10:21
        3 → ymd_w            20261031 星期六
        4 → y-m-d_w          2026-10-31 星期六
        5 → y-m-d h:m:s      2026-10-31 09:10:21
        6 → y-m-d h:m:s_w    2026-10-31 09:10:21 星期六
    """
    now = datetime.now()
    week_map = {
        0: "星期一",
        1: "星期二",
        2: "星期三",
        3: "星期四",
        4: "星期五",
        5: "星期六",
        6: "星期日",
    }
    week_str = week_map[now.weekday()]

    fmt_map = {
        0: ("%Y%m%d", False),
        1: ("%Y-%m-%d", False),
        2: ("%H:%M:%S", False),
        3: ("%Y%m%d", True),
        4: ("%Y-%m-%d", True),
        5: ("%Y-%m-%d %H:%M:%S", False),
        6: ("%Y-%m-%d %H:%M:%S", True),
    }

    # 优先处理默认值
    if code is None or code not in fmt_map:
        code = 5

    fmt, need_week = fmt_map[code]
    s = now.strftime(fmt)
    if need_week:
        s = f"{s} {week_str}"
    return s

if __name__ == '__main__':
    print(show_date_time())