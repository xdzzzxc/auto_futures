from ruamel.yaml import YAML, YAMLError
from public.shared_data import yaml_rlock
from public.shared_data import get_data_cache_dir
import os
from typing import Any, Optional

yaml = YAML()
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=2, offset=0)
yaml.sort_base_mapping_type_on_output = False   # 防止保存时节点顺序被重排

base_file_name = "cfg_pool.yaml"

def get_yaml_path(ts_code=None):
    yaml_file_path = ""
    if ts_code is not None:
        yaml_file_name = ts_code[:-4] + "_" + base_file_name
    else:
        yaml_file_name = base_file_name
    yaml_file_path = os.path.join(get_data_cache_dir(folder=1), "yaml", yaml_file_name)
    if yaml_file_path == "":
        print("没有找到策略文件，请手动重启量化策略应用程序！")
        return
    else:
        return yaml_file_path


def read_yaml(ts_code: Optional[str] = None):
    yaml_path = get_yaml_path(ts_code)
    print(f"读取路径: {yaml_path}")
    try:
        with yaml_rlock:
            with open(yaml_path, "r", encoding="utf-8") as f:
                cfg = yaml.load(f)
    except YAMLError as e:
        print(f"YAML解析错误：{e}")
        return None
    if cfg is None:
        cfg = {}
    return cfg

def write_cfg(
    ts_code: Optional[str] = None,
    root_key: str = "temp_params",
    sub_key: str = "",
    new_value: Any = None
) -> bool:
    """
    修改yaml配置：指定顶层一级节点root_key，修改它下面的sub_key的值
    :param ts_code: 传给get_yaml_path，可选
    :param root_key: 第一层节点名，如 "temp_params" / "strategy_001"
    :param sub_key: root_key下的子key，如 "temp_direction"
    :param new_value: 实时外部传入的值
    :return: bool 是否写入成功
    """
    yaml_path = get_yaml_path(ts_code)
    if yaml_path is None or yaml_path == "":
        return False
    print(f"写入路径: {yaml_path}, root={root_key}, sub={sub_key}, val={new_value}")

    # 1. 读取配置
    cfg = read_yaml(ts_code)
    if cfg is None:
        print("配置读取失败，放弃写入")
        return False

    # 2. 判断一级节点是否存在，不存在则新建
    if root_key not in cfg:
        print(f"警告：顶层节点 [{root_key}] 不存在，自动创建")
        cfg[root_key] = {}

    root_node = cfg[root_key]
    # 要求root节点必须是字典（不能是列表，common_conditions是列表，这个函数不适合改列表元素）
    if not isinstance(root_node, dict):
        print(f"错误：[{root_key}] 不是字典类型，不能按 sub_key 修改（common_conditions是列表，不适用本函数）")
        return False

    # 3. 修改子节点值
    root_node[sub_key] = new_value

    # 4. 写回文件
    try:
        with yaml_rlock:
            with open(yaml_path, "w", encoding="utf-8") as f:
                yaml.dump(cfg, f)
    except Exception as e:
        print(f"写入文件失败：{e}")
        return False
    print("✅ 写入完成")
    return True


if __name__ == '__main__':
    # set_temp_param("temp_direction", "rise")
    read_yaml()
    res = write_cfg(root_key="temp_params", new_value="sideways", sub_key="temp_direction")
    print(res)