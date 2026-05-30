'''
本模块实现快速连接同花顺操作主窗口，主要用于对子程序的调试
同花顺交易软件须是已登录期货用户！！！！！！！
'''
from functools import lru_cache
from pywinauto import Application
from core import close_ad_window
from core.connect_ths import run_ths


@lru_cache(maxsize=None)
def quick_conn(user_type=0):
    ths_window = None
    try:
        app = Application(backend="uia").connect(title_re=r".*同花顺期货通.*", control_type="Window")
        ths_window = app.window(title_re=r".*同花顺期货通.*", control_type="Window")
        ths_window.wait('visible', timeout=10)
        ths_window.set_focus()
        ths_window.maximize()
        close_ad_window.close_ad_windows()
        return ths_window
    except ValueError:
        print("您没有打开的同花顺应用程序，请等待程序重新启动 ······")
        run_ths()


if __name__ == "__main__":
    quick_conn()
