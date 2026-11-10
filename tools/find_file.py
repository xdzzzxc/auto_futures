"""
本模块主要功能：在项目中查找指定的文件，返回文件绝对路径
"""
from pathlib import Path
import time

def find_file(file_name: str, folder_path: str = r"E:\auto_futures") -> str | None:
    start_time = time.time()
    BASE_DIR = Path(folder_path)
    if not BASE_DIR.exists():
        raise NotADirectoryError(f"根目录不存在：{BASE_DIR}")
    if not BASE_DIR.is_dir():
        raise NotADirectoryError(f"不是目录：{BASE_DIR}")

    # 黑名单：路径中包含这些片段直接丢弃
    exclude_keywords = {".venv", "__pycache__", ".git", "site-packages", ".idea", "dist", "build"}

    for f in BASE_DIR.rglob("*"):
        if f.is_file() and f.name == file_name:
            # 判断路径是否命中黑名单
            fp_str = str(f).lower()
            if any(k in fp_str for k in exclude_keywords):
                continue
            end_time = time.time()
            print(f"全程耗时：{round(end_time - start_time, 2)}秒")
            return str(f.resolve())

    end_time = time.time()
    print(f"全程耗时：{round(end_time - start_time, 2)}秒，未找到文件")
    return None

if __name__ == '__main__':
    res = find_file("trade.py")
    print(res)
