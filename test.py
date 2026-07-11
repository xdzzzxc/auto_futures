from pathlib import Path

def get_data_cache_dir(marker=None):
    if marker is None:
        marker = [".git", "requirements.txt", "main.py"]
    p = Path(__file__).resolve()
    root_dir = None
    for parent in p.parents:
        if any((parent / m).exists() for m in marker):
            root_dir = parent
            break
    if root_dir is None:
        raise FileNotFoundError("找不到项目根目录标记文件")
    cache_folder = root_dir / "data" / "futures_data"
    cache_folder.mkdir(parents=True, exist_ok=True)
    return str(cache_folder)


if __name__ == '__main__':
    root = get_data_cache_dir()
    print(root)