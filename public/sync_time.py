import ntplib
import subprocess
from datetime import datetime


def sync_time():
    try:
        # 获取网络时间
        ntp = ntplib.NTPClient()
        res = ntp.request('ntp.aliyun.com', timeout=3)

        # 转成标准时间格式
        dt = datetime.fromtimestamp(res.tx_time)
        date_str = dt.strftime("%Y-%m-%d")
        time_str = dt.strftime("%H:%M:%S")

        print("同步成功！网络时间：", dt.strftime("%Y-%m-%d %H:%M:%S"))

        # Windows 正确设置时间命令（无乱码、无报错）
        subprocess.run(f'date {date_str}', shell=True, capture_output=True, text=True, encoding='gbk')
        subprocess.run(f'time {time_str}', shell=True, capture_output=True, text=True, encoding='gbk')

        print("✅ 系统时间已同步！")

    except Exception as e:
        print("❌ 同步失败，请用【管理员身份运行】Python")
        print("错误信息：", e)


if __name__ == "__main__":
    sync_time()
