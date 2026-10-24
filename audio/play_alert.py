import logging
import sys
from pathlib import Path
from public.shared_data import get_data_cache_dir

logger = logging.getLogger("sound_alert")
# audio/play_alert.py
"""
音频告警模块
对外暴露函数：sound_order / sound_profit_close / sound_loss_close / sound_warning
可在任意地方 import 调用，不会污染外部变量
"""
import logging
import threading
import sys
from pathlib import Path

logger = logging.getLogger("sound_alert")

# -------- 初始化 winsound，保证变量一定存在 --------
winsound = None
if sys.platform == "win32":
    try:
        import winsound
    except ImportError:
        winsound = None

# -------- 初始化 playsound，导入失败替换为空函数，杜绝NameError --------
try:
    from playsound import playsound
except ImportError:
    def playsound(*args, **kwargs):
        """playsound不可用时的空占位函数，调用不会报错"""
        pass

# -------- 音频目录与配置，沿用你原有逻辑 --------
def get_audio_config():
    """音频路径配置，只在本模块内部使用"""
    # 你原有获取缓存目录逻辑，保留
    from public.shared_data import get_data_cache_dir
    audio_cache_dir = Path(get_data_cache_dir()).parent.parent / "audio" / "audios"
    audio_cache_dir.mkdir(parents=True, exist_ok=True)
    logger.debug(f"audio dir: {audio_cache_dir}")
    AUDIO_CFG = {
        "order": str(audio_cache_dir / "order.wav"),
        "close_profit": str(audio_cache_dir / "close_profit.wav"),
        "close_loss": str(audio_cache_dir / "close_loss.wav"),
        "warn": str(audio_cache_dir / "warn.wav")
    }
    return AUDIO_CFG

AUDIO_CFG = get_audio_config()

# -------- 核心播放函数 --------
def play_alert_sound(sound_file: str, freq: int, duration: int):
    """
    优先播放wav音频文件；文件缺失/playsound异常，自动降级winsound蜂鸣
    :param sound_file: wav文件完整路径
    :param freq: 蜂鸣频率Hz
    :param duration: 蜂鸣时长ms
    """
    # 第一步：尝试播放wav
    try:
        playsound(sound_file)
        logger.debug(f"播放音频成功: {sound_file}")
        return
    except Exception as e:
        logger.warning(f"playsound播放失败，切换系统蜂鸣 | err={e}")

    # 第二步：兜底蜂鸣
    if winsound is not None:
        try:
            winsound.Beep(freq, duration)
            logger.debug(f"winsound蜂鸣 freq={freq}, duration={duration}")
        except Exception as e:
            logger.error(f"winsound蜂鸣失败 | err={e}")
    else:
        logger.info("无可用音频组件，跳过告警音")

# -------- 对外暴露接口，其他模块直接调用 --------
def sound_order():
    play_alert_sound(AUDIO_CFG["order"], freq=900, duration=200)

def sound_profit_close():
    play_alert_sound(AUDIO_CFG["close_profit"], freq=1200, duration=350)

def sound_loss_close():
    play_alert_sound(AUDIO_CFG["close_loss"], freq=400, duration=400)

def sound_warning():
    play_alert_sound(AUDIO_CFG["warn"], freq=600, duration=250)

def sound_warning_nonblock():
    """非阻塞版本，不会卡住调用的线程"""
    t = threading.Thread(target=sound_warning, daemon=True)
    t.start()

def sound_order_nonblock():
    t = threading.Thread(target=sound_order, daemon=True)
    t.start()

def sound_profit_close_nonblock():
    t = threading.Thread(target=sound_profit_close, daemon=True)
    t.start()

def sound_loss_close_nonblock():
    t = threading.Thread(target=sound_loss_close, daemon=True)
    t.start()

if __name__ == '__main__':
    sound_order()
    sound_profit_close()
# 音频缓存目录，沿用你这一段
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

# 预先初始化 winsound
winsound = None
if sys.platform == "win32":
    try:
        import winsound
    except ImportError:
        winsound = None

# 优先加载playsound，失败回退空函数
try:
    from playsound import playsound
except ImportError:
    def playsound(*args, **kwargs):
        pass


def play_alert_sound(sound_file: str, freq: int = 800, duration: int = 300):
    """
    播放告警音效
    :param sound_file: wav音频文件路径
    :param freq: winsound蜂鸣频率(Hz)
    :param duration: winsound蜂鸣时长(ms)
    """
    # 优先播放音频文件
    try:
        playsound(sound_file)
        logger.debug(f"播放音频成功: {sound_file}")
        return
    except Exception as e:
        logger.warning(f"playsound播放音频失败，切换蜂鸣: {e}")

    # 备选：系统蜂鸣兜底
    if winsound is not None:
        try:
            winsound.Beep(freq, duration)
            logger.debug(f"系统蜂鸣: freq={freq}, duration={duration}")
        except Exception as e:
            logger.error(f"winsound蜂鸣失败: {e}")
    else:
        logger.info("无可用音频播放组件，跳过告警音")


# 场景封装：直接读取AUDIO_CFG配置
def sound_order():
    play_alert_sound(sound_file=AUDIO_CFG["order"], freq=900, duration=200)

def sound_profit_close():
    play_alert_sound(sound_file=AUDIO_CFG["close_profit"], freq=1200, duration=350)

def sound_loss_close():
    play_alert_sound(sound_file=AUDIO_CFG["close_loss"], freq=400, duration=400)

def sound_warning():
    play_alert_sound(sound_file=AUDIO_CFG["warn"], freq=600, duration=250)


if __name__ == "__main__":
    # 自测
    sound_order()
    sound_profit_close()
    sound_loss_close()
    sound_warning()
