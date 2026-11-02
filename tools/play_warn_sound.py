import pythoncom
import win32com.client
import queue
import threading
import pyttsx3 as tts
import time

from public import print_context

text_type_dict = {0: "提示：", 1: "警告：", 2: "严重警告："}

def play_warn_sound(text: str = "运行警告：", text_type: int = 0):

    if not hasattr(play_warn_sound, "speak_queue"):
        q = queue.Queue(maxsize=5)

        def daemon_worker():
            try:
                # print("[speaker] worker 启动，CoInitialize")
                pythoncom.CoInitialize()
                spk = win32com.client.Dispatch("SAPI.SpVoice")
                # print("[speaker] SAPI 对象创建成功")
                while True:
                    msg = q.get()
                    # print(f"[speaker] 收到消息: {msg}")
                    if msg is None:
                        print("[speaker] 收到退出信号，退出循环")
                        break
                    spk.Speak(msg)
                    # print(f"[speaker] 播放完成: {msg}")
                    q.task_done()
            except Exception as e:
                print(f"[speaker] 播报线程异常：{repr(e)}")
            finally:
                pythoncom.CoUninitialize()
                print("[speaker] worker 结束，CoUninitialize")

        # ---------------- 关键区分：测试/生产 ----------------
        # 如果你是单独脚本测试：daemon=False；正式量化主程序改成 daemon=True
        t = threading.Thread(target=daemon_worker, daemon=False)
        t.start()
        play_warn_sound.speak_queue = q
        play_warn_sound.speak_thread = t

    try:
        play_warn_sound.speak_queue.put_nowait(text)
        print(f"{text_type_dict[text_type]}{repr(text)}")
        # print("[main] 消息入队成功")
    except queue.Full:
        print("[main] 队列已满，丢弃告警")


def play_warn_sound_win(text: str = "运行警告"):
    # 同步阻塞！业务主线程禁止调用这个
    pythoncom.CoInitialize()
    speaker = win32com.client.Dispatch("SAPI.SpVoice")
    speaker.Speak(text)
    pythoncom.CoUninitialize()


def play_warn_sound_tts(text: str = "运行警告"):
    if not hasattr(play_warn_sound_tts, "speak_queue"):
        q = queue.Queue(maxsize=5)
        def worker():
            try:
                engine = tts.init()
                while True:
                    msg = q.get()
                    if msg is None:
                        break
                    engine.say(msg)
                    engine.runAndWait()
                    q.task_done()
            except Exception as e:
                print(f"tts worker error: {e}")
        t = threading.Thread(target=worker, daemon=False)
        t.start()
        play_warn_sound_tts.speak_queue = q
        play_warn_sound_tts.speak_thread = t
    try:
        play_warn_sound_tts.speak_queue.put_nowait(text)
    except queue.Full:
        pass


if __name__ == '__main__':
    play_warn_sound("程序运行警告，测试播报")
    # 必须等待，给播放时间
    # time.sleep(4)
    # print("[main] 主线程准备退出")
    # play_warn_sound_tts()
