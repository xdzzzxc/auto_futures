# dir_printer.py
import os
from typing import List, Optional


def print_directory_tree(root_dir: str, prefix: str = "", is_last: bool = True) -> None:
    """
    【功能1】仅打印目录树形结构，不读取任何文件内容
    :param root_dir: 根目录路径
    :param prefix: 树形渲染前缀，递归内部使用
    :param is_last: 是否同级最后一个节点，递归内部使用
    """
    root_dir = os.path.abspath(root_dir)
    basename = os.path.basename(root_dir)
    connector = "└── " if is_last else "├── "
    print(f"{prefix}{connector}{basename}")

    if not os.path.isdir(root_dir):
        return

    # 跳过需要忽略的目录，可自行扩展
    ignore_names = {"__pycache__", ".git", "venv", ".venv", ".idea"}
    children = []
    for name in sorted(os.listdir(root_dir)):
        if name not in ignore_names:
            children.append(name)

    total = len(children)
    for idx, name in enumerate(children):
        full_path = os.path.join(root_dir, name)
        child_last = (idx == total - 1)
        new_prefix = prefix + ("    " if is_last else "│   ")
        print_directory_tree(full_path, new_prefix, child_last)


def print_files_content_by_ext(
    root_dir: str,
    exts: List[str],
    max_file_size: int = 1024 * 1024
) -> None:
    """
    【功能2】递归遍历目录(含子目录)，打印匹配扩展名的文件内容；不打印目录树
    :param root_dir: 扫描根目录
    :param exts: 后缀列表，如 [".py", ".yaml"]，大小写不敏感
    :param max_file_size: 最大允许读取文件字节数，防止大文件刷屏，默认1MB
    """
    root_dir = os.path.abspath(root_dir)
    ext_lower = {e.lower() for e in exts}

    ignore_names = {"__pycache__", ".git", "venv", ".venv", ".idea"}

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # 修改dirnames原地过滤，os.walk不再进入忽略文件夹
        dirnames[:] = [d for d in dirnames if d not in ignore_names]

        for filename in filenames:
            _, ext = os.path.splitext(filename)
            if ext.lower() not in ext_lower:
                continue

            file_path = os.path.join(dirpath, filename)

            # 文件大小校验
            try:
                file_size = os.path.getsize(file_path)
            except Exception:
                print(f"\n[SKIP] 获取文件大小失败: {file_path}")
                continue

            if file_size > max_file_size:
                print(f"\n[SKIP] 文件超过大小限制({file_size} bytes): {file_path}")
                continue

            # 读取并打印内容
            print(f"\n{'='*70}")
            print(f"FILE: {file_path}")
            print(f"{'='*70}")
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    print(content)
            except UnicodeDecodeError:
                print(f"[SKIP] 二进制/非UTF‑8文件，跳过")
            except PermissionError:
                print(f"[SKIP] 权限不足，无法读取")
            except OSError as e:
                print(f"[SKIP] IO异常: {str(e)}")


if __name__ == "__main__":
    # ----------- 模块自测示例 -----------
    target_project = r"E:\auto_futures"
    target_folder = r"E:\auto_futures\core"
    print("===== 打印目录树 =====")
    print_directory_tree(target_project)

    # print("\n\n===== 打印匹配后缀文件内容 =====")
    # print_files_content_by_ext(target_folder, exts=[".py", ".yaml"])
