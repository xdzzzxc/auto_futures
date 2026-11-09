from pathlib import Path
import time

def find_file(file_name: str, folder_path: str = r"E:\auto_futures") -> str | None:
    start_time = time.time()
    BASE_DIR = Path(folder_path)
    if not BASE_DIR.exists():
        raise NotADirectoryError(f"根目录不存在：{BASE_DIR}")
    if not BASE_DIR.is_dir():
        raise NotADirectoryError(f"不是目录：{BASE_DIR}")

    for f in BASE_DIR.rglob("*"):
        if f.is_file() and f.name == file_name:
            end_time = time.time()
            print(f"全程耗时：{round(end_time - start_time, 2)}秒")
            return str(f.resolve())
    end_time = time.time()
    print(f"全程耗时：{round(end_time - start_time, 2)}秒")
    return None

if __name__ == '__main__':
    res = find_file("cfg_pool.yaml")
    print(res)
