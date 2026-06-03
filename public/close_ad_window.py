import win32gui
import win32con
import win32api
from time import sleep

# 白名单窗口（标题包含这些 → 不关闭）
PRESERVE_WORDS = ["同花顺期货", ".py", "豆包"]

def close_ad_windows():
    ad_windows = []

    def callback(hwnd, extra):
        # 只处理可见窗口
        if not win32gui.IsWindowVisible(hwnd):
            return

        # 跳过最小化
        if win32gui.GetWindowPlacement(hwnd)[1] == win32con.SW_SHOWMINIMIZED:
            return

        # 获取窗口信息
        title = win32gui.GetWindowText(hwnd).strip()
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width = right - left
        height = bottom - top

        # ============== 你的白名单逻辑（完全保留） ==============
        for kw in PRESERVE_WORDS:
            if kw in title:
                return

        # ============== 你的原始判断规则（100% 保留不动） ==============
        screen_w = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
        screen_h = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
        rule_left = screen_w * 0.6
        rule_bottom = screen_h * 0.9

        condition1 = (left > rule_left) and (bottom > rule_bottom) and (width > 100) and (height > 50)
        condition2 = (width <= 500) and (height <= 400)
        condition3 = title in ['pcm_h5_msg', '广告', '系统提示', '推荐', '升级']

        # 你的原始逻辑：满足任意一个就判定为广告 → 关闭
        if condition1 or condition2 or condition3:
            ad_windows.append({
                "hwnd": hwnd,
                "title": title
            })

    # 枚举所有窗口
    win32gui.EnumWindows(callback, None)

    # 关闭广告
    count = 0
    for wnd in ad_windows:
        try:
            win32gui.PostMessage(wnd["hwnd"], win32con.WM_CLOSE, 0, 0)
            count += 1
            sleep(0.1)
        except:
            continue

    print(f"已关闭广告弹窗：{count} 个")

if __name__ == "__main__":
    close_ad_windows()