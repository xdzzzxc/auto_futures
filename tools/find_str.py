import os
import ast
from typing import List, Optional


def extract_shared_data_members(module_path: str) -> dict:
    """
    解析 shared_data.py，【仅提取模块顶层】变量、类、函数名称，过滤函数内部局部变量
    返回 {"vars":[], "classes":[], "funcs":[]}
    """
    with open(module_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())

    vars_list = []
    class_list = []
    func_list = []

    for node in ast.iter_child_nodes(tree):
        # iter_child_nodes 只拿模块顶层节点，不会进入函数/类内部
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    # 过滤：下划线开头临时变量
                    if not name.startswith("_"):
                        vars_list.append(name)
        elif isinstance(node, ast.ClassDef):
            name = node.name
            if not name.startswith("_"):
                class_list.append(name)
        elif isinstance(node, ast.FunctionDef):
            name = node.name
            if not name.startswith("_"):
                func_list.append(name)

    # 去重+排序
    vars_list = sorted(list(set(vars_list)))
    class_list = sorted(list(set(class_list)))
    func_list = sorted(list(set(func_list)))
    return {
        "vars": vars_list,
        "classes": class_list,
        "funcs": func_list
    }


def scan_shared_data_refs(
    target: Optional[List[str]] = None,
    root_dir: str = r"e:\auto_futures",
    shared_data_file: str = r"e:\auto_futures\public\shared_data.py",
    exts: tuple = (".py", ".yaml", ".yml", ".txt", ".md"),
    exclude_dirs: list = None,
    case_sensitive: bool = True
):
    """
    批量检索shared_data模块成员在【外部其他模块】的引用
    :param target: 名称列表；为None时自动提取shared_data.py里所有顶层变量/类/函数作为搜索列表
    :param root_dir: 项目根目录
    :param shared_data_file: shared_data.py完整路径
    :param exts: 扫描文件后缀
    :param exclude_dirs: 跳过目录
    :param case_sensitive: 大小写敏感
    """
    if exclude_dirs is None:
        exclude_dirs = [".git", "__pycache__", ".venv", "venv", ".idea"]

    # 统一路径大小写，避免windows路径大小写不一致判断失误
    shared_data_file = os.path.normcase(os.path.abspath(shared_data_file))

    # 自动提取shared_data顶层成员，填充target列表
    if target is None:
        members = extract_shared_data_members(shared_data_file)
        target = []
        target.extend(members["vars"])
        target.extend(members["classes"])
        target.extend(members["funcs"])
        print(f"===== 自动从shared_data.py【顶层】提取待搜索对象 =====")
        print(f"变量: {members['vars']}")
        print(f"类: {members['classes']}")
        print(f"函数: {members['funcs']}")
        print(f"待检索总数量：{len(target)}\n")

    # 存储结果: key=对象名, value=[(文件路径,行号,行文本), ...]
    result_dict = {name: [] for name in target}

    def scan_single_file(file_path: str):
        """扫描单个文件，收集所有匹配项，跳过shared_data.py自身"""
        fp_abs = os.path.normcase(os.path.abspath(file_path))
        # 跳过shared_data.py本身，不统计定义行
        if fp_abs == shared_data_file:
            return

        if not file_path.endswith(exts):
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            return
        except Exception as e:
            print(f"⚠️ skip file {file_path}, error: {str(e)}")
            return

        for line_no, raw_line in enumerate(lines, start=1):
            line_text = raw_line if case_sensitive else raw_line.lower()
            for obj_name in target:
                obj_name_raw = obj_name if case_sensitive else obj_name.lower()
                if obj_name_raw in line_text:
                    result_dict[obj_name].append((file_path, line_no, raw_line.rstrip()))

    # 遍历项目目录
    if os.path.isdir(root_dir):
        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
            for fname in filenames:
                full_path = os.path.join(dirpath, fname)
                scan_single_file(full_path)
    else:
        print(f"❌项目根路径不存在: {root_dir}")
        return

    # ========== 输出汇总结果 ==========
    separator = "-" * 80
    for obj_name, hit_list in result_dict.items():
        print(f"\n{separator}")
        print(f"【对象名称】{obj_name}，外部模块总引用次数：{len(hit_list)}")
        if not hit_list:
            print("    → 仅在shared_data.py内定义，其他模块没有任何引用")
            continue
        for fp, ln, content in hit_list:
            print(f"    {fp} : line {ln}")
            print(f"        {content}")


# ====================== 你原来的原版函数，完整保留 ======================
def search_project_string(
    target: str,
    root_dir: str = r"e:\auto_futures",
    exts: tuple = (".py", ".yaml", ".yml", ".txt", ".md"),
    exclude_dirs: list = None,
    case_sensitive: bool = True
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
    # 优先级逻辑：
    # 1. find_str 不为空 → 优先执行【单个字符串搜索】search_project_string
    # 2. find_str为空、find_list非空 → 执行【指定列表批量查找shared_data成员】scan_shared_data_refs
    # 3. find_str为空、find_list为空 → 执行【全面扫描shared_data全部顶层变量/类/函数】scan_shared_data_refs(target=None)
    find_str = 'send_msg'
    find_list = []







    root = r"e:\auto_futures"
    sd_file = r"e:\auto_futures\public\shared_data.py"

    if find_str.strip() != "":
        print(f"===== 模式1：单字符串搜索，目标：{find_str} =====\n")
        search_project_string(target=find_str, root_dir=root, case_sensitive=True)
    elif len(find_list) > 0:
        print(f"===== 模式2：批量检索指定shared_data成员列表 {find_list} =====\n")
        scan_shared_data_refs(target=find_list, root_dir=root, shared_data_file=sd_file, case_sensitive=True)
    else:
        print("===== 模式3：全面扫描shared_data.py所有顶层变量/函数/类，统计外部引用 =====\n")
        scan_shared_data_refs(target=None, root_dir=root, shared_data_file=sd_file, case_sensitive=True)
