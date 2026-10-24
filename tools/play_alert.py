import os
import threading
from public.print_context import print_context
from public.shared_data import get_data_cache_dir
from pathlib import Path


audio_cache_dir = Path(get_data_cache_dir()).parent.parent / "audio" / "audios"
audio_cache_dir.mkdir(parents=True, exist_ok=True)
print(audio_cache_dir, type(audio_cache_dir))

# ===================== 配置区：自定义音频文件路径，按需修改 =====================
AUDIO_CFG = {
    "order": str(audio_cache_dir / "order.wav"),
    "close_profit": str(audio_cache_dir / "close_profit.wav"),
    "close_loss": str(audio_cache_dir / "close_loss.wav"),
    "warn": str(audio_cache_dir / "warn.wav")
}

# 尝试加载playsound
USE_PLAYSOUND = False
try:
    from playsound import playsound
    USE_PLAYSOUND = True
    # print_context("音效模块：加载playsound成功")
except ImportError:
    print_context("音效模块：playsound未安装，音频播放不可用")

def _play_audio(key: str):
    """内部播放函数，后台线程异步，不阻塞量化主程序"""
    wav_path = AUDIO_CFG[key]
    print_context(f"【音效调试】key={key}, path={wav_path}, exists={os.path.isfile(wav_path)}")
    if not USE_PLAYSOUND:
        print_context("【音效模块】playsound不可用，跳过播放")
        return
    if not os.path.isfile(wav_path):
        print_context(f"【音效模块】文件不存在：{wav_path}")
        return
    try:
        # 开独立线程播放，异步不阻塞
        t = threading.Thread(target=playsound, args=(wav_path,))
        t.daemon = True
        t.start()
    except Exception as e:
        print_context(f"【音效模块】播放异常：{str(e)}")

def sound_order():
    """下单（开仓）声音"""
    _play_audio("order")

def sound_close_profit():
    """盈利平仓声音"""
    _play_audio("close_profit")

def sound_close_loss():
    """亏损平仓声音"""
    _play_audio("close_loss")

def sound_warn():
    """警告告警声音（线程超时、控件异常、委托失败）"""
    _play_audio("warn")

if __name__ == '__main__':
    import time
    # sound_warn()
    # sound_order()
    sound_close_profit()
    # sound_close_loss()

    time.sleep(1.5)