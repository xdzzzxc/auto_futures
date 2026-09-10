import os

def search_project_string(
    target: str,
    root_dir: str,
    exts: tuple = (".py", ".yaml", ".yml", ".txt", ".md"),
    exclude_dirs: list = None,
    case_sensitive: bool = False
):
    """
    在项目中递归搜索目标字符串
    :param target: 需要查找的字符串
    :param root_dir: 可以传入【目录路径】递归扫描；也可以直接传入【单个文件完整路径】只扫描该文件
    :param exts: 只扫描这些后缀的文件（单文件模式下该参数依然生效，后缀不匹配直接跳过）
    :param exclude_dirs: 需要跳过的目录
    :param case_sensitive: 是否大小写敏感
    """
    if exclude_dirs is None:
        exclude_dirs = [".git", "__pycache__", ".venv", "venv", ".idea"]

    target_raw = target if case_sensitive else target.lower()

    def scan_single_file(file_path: str):
        """扫描单个文件内部"""
        if not file_path.endswith(exts):
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line_no, line in enumerate(f, start=1):
                    line_text = line if case_sensitive else line.lower()
                    if target_raw in line_text:
                        print(f"\n✅ Found -> {file_path} : line {line_no}")
                        print(f"    {line.rstrip()}")
        except UnicodeDecodeError:
            return
        except Exception as e:
            print(f"⚠️ skip file {file_path}, error: {str(e)}")

    # 判断传入是文件还是目录
    if os.path.isfile(root_dir):
        scan_single_file(root_dir)
    elif os.path.isdir(root_dir):
        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
            for fname in filenames:
                full_path = os.path.join(dirpath, fname)
                scan_single_file(full_path)
    else:
        print(f"❌路径不存在: {root_dir}")


# ============ 使用示例 ============
if __name__ == "__main__":
    # 示例1：整个项目目录搜索
    # project_root = r"e:\auto_futures"
    # search_project_string(
    #     target="shared_data.ts_code =",
    #     root_dir=project_root,
    #     case_sensitive=True
    # )

    # 示例2：只查单个指定文件（直接传入文件完整路径）
    search_project_string(
        target="send_msg",
        root_dir=r"e:\auto_futures",
        case_sensitive=True
    )
