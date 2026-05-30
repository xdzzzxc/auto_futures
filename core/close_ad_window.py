import win32gui
import win32con
import win32api
from pywinauto import Desktop
from time import sleep
window_dict = {0: ["同花顺期货能"], 1: ["同花顺期货能", ".py", "豆包"]}


def close_ad_windows():  # 删除电脑右下角广告弹窗等窗口以免遮挡导致自动化失败
    """获取所有可见窗口的信息，包括句柄、坐标和宽高"""
    ad_windows = []
    special_window = ['pcm_h5_msg', '广告', '系统提示', '推荐', '升级']  # 某些特殊窗口的删除方法

    def callback(hwnd, extra):
        """窗口枚举回调函数"""
        # 检查窗口是否可见
        if win32gui.IsWindowVisible(hwnd):
            # 过滤掉最小化窗口
            if win32gui.GetWindowPlacement(hwnd)[1] != win32con.SW_SHOWMINIMIZED:
                # 获取窗口矩形坐标
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                # 计算宽度和高度
                width = right - left
                height = bottom - top
                # 获取窗口标题
                title = win32gui.GetWindowText(hwnd)
                rule_left = win32api.GetSystemMetrics(win32con.SM_CXSCREEN) * 0.6
                # print(f'rule_left:{rule_left}')
                rule_bottom = win32api.GetSystemMetrics(win32con.SM_CYSCREEN) * 0.9
                # print(f'rule_top:{rule_bottom}, {win32api.GetSystemMetrics(win32con.SM_CYSCREEN)}')
                # 收集窗口信息
                if (left > rule_left and bottom > rule_bottom and width > 100 and
                        height > 50 or (width <= 500 and height <= 400) or
                        title in special_window):
                    window_info = {
                        "hwnd": hwnd,
                        "title": title,
                        "X1": left,
                        "Y1": top,
                        "X2": right,
                        "Y2": bottom,
                        "width": width,
                        "height": height
                    }
                    ad_windows.append(window_info)

    # 枚举所有顶层窗口
    # print("程序正在删除广告窗口······")
    win32gui.EnumWindows(callback, None)
    for n, w in enumerate(ad_windows):
        # print(f"\n正在删除第{n + 1}个广告弹窗 ······")
        hwnd = w['hwnd']
        win32gui.SendMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        # print(f"已将句柄为{hwnd}的[{w['title'] if w['title'] else '无标题'}]窗口移除！")


# 需保留的窗口关键词列表（标题包含任意一个则不关闭）
window_list = ["同花顺期货能", ".py", "豆包"]


def close_all_windows():  # 删除电脑右下角广告弹窗等窗口以免遮挡导致自动化失败
    """
    获取所有可见窗口的信息，筛选符合广告特征的窗口并关闭
    但保留标题包含window_list中任意关键词的窗口
    """
    ad_windows = []
    special_window = ['pcm_h5_msg', '广告', '系统提示', '推荐', '升级']  # 某些特殊窗口的删除方法

    def callback(hwnd, extra):
        """窗口枚举回调函数"""
        # 检查窗口是否可见
        if win32gui.IsWindowVisible(hwnd):
            # 过滤掉最小化窗口
            if win32gui.GetWindowPlacement(hwnd)[1] != win32con.SW_SHOWMINIMIZED:
                # 获取窗口矩形坐标
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                # 计算宽度和高度
                width = right - left
                height = bottom - top
                # 获取窗口标题
                title = win32gui.GetWindowText(hwnd)

                # ========== 新增核心过滤逻辑 ==========
                # 检查标题是否包含需保留的关键词，包含则直接跳过（不加入广告列表）
                need_preserve = False
                for keyword in window_list:
                    if keyword in title:
                        need_preserve = True
                        break
                if need_preserve:
                    return  # 跳过该窗口，不加入广告列表
                # =====================================

                rule_left = win32api.GetSystemMetrics(win32con.SM_CXSCREEN) * 0.6
                rule_bottom = win32api.GetSystemMetrics(win32con.SM_CYSCREEN) * 0.9
                # 收集符合广告特征的窗口信息
                if (left > rule_left and bottom > rule_bottom and width > 100 and
                        height > 50 or (width <= 500 and height <= 400) or
                        title in special_window):
                    window_info = {
                        "hwnd": hwnd,
                        "title": title,
                        "X1": left,
                        "Y1": top,
                        "X2": right,
                        "Y2": bottom,
                        "width": width,
                        "height": height
                    }
                    ad_windows.append(window_info)

    # 枚举所有顶层窗口
    # print("程序正在扫描并删除广告窗口······")
    win32gui.EnumWindows(callback, None)

    # 统计变量
    closed_count = 0
    preserved_by_rule = 0  # 因包含保留关键词被跳过的窗口数（仅用于日志，实际在callback中已跳过）

    for n, w in enumerate(ad_windows):
        try:
            hwnd = w['hwnd']
            # 发送关闭消息
            win32gui.SendMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            closed_count += 1
            # print(f"已关闭第{n + 1}个广告窗口：[{w['title'] if w['title'] else '无标题'}] (句柄：{hwnd})")
            sleep(0.1)  # 短暂延迟，避免操作过快
        except Exception as e:
            print(f"关闭窗口失败：[{w['title'] if w['title'] else '无标题'}]，错误：{str(e)}")

    print(f"\n广告窗口清理完成！共关闭 {closed_count} 个广告窗口，保留了包含指定关键词的窗口")


# 调用示例
if __name__ == "__main__":
    close_ad_windows()

