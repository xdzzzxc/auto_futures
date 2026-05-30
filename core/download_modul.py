from modelscope.hub.snapshot_download import snapshot_download
import os

def download_model(save_dir=r"E:\auto_futures\qwen1_8b"):
    # 创建保存目录
    os.makedirs(save_dir, exist_ok=True)

    # 下载模型（国内高速，自动断点续传）
    model_local_path = snapshot_download(
        "qwen/Qwen-1_8B",
        cache_dir=save_dir
    )

    print("模型下载完成，保存路径：", model_local_path)
    return model_local_path

# 调用下载
if __name__ == "__main__":
    download_model()