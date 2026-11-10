from ruamel.yaml import YAML
from public.shared_data import yaml_rlock
from public.shared_data import get_data_cache_dir
import os

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


def set_temp_param(sub_key: str, value, ts_code=None, skip_if_same: bool = False):
    """
    只修改 temp_params 下的字段，专门用于临时参数动态写入
    :param sub_key: temp_params 下面的子键，例如 temp_direction、temp_profit
    :param value: 写入值，str/int/float/None 都支持
    :param ts_code: 合约代码，不传操作主 cfg_pool.yaml
    :param skip_if_same: True = 新旧值相同则跳过写盘（减少文件刷新、避免VSCode冲突）；
                         False = 每次都强制覆写（默认，向后兼容）
    :return: bool
    """
    yaml_path = get_yaml_path(ts_code)

    with yaml_rlock:
        if os.path.exists(yaml_path):
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.load(f) or {}
        else:
            data = {}

        # 保证 temp_params 节点一定是 dict
        if "temp_params" not in data or not isinstance(data["temp_params"], dict):
            data["temp_params"] = {}

        # —— 新增：相同值跳过写盘 ——
        old_val = data["temp_params"].get(sub_key)
        if skip_if_same and old_val == value:
            # 没变化，直接返回，不碰磁盘，文件 mtime 不动
            return True

        data["temp_params"][sub_key] = value

        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

    print(f"✅临时参数写入 | {yaml_path} | temp_params.{sub_key} = {value}")
    return True


def get_temp_param(sub_key: str, default=None, ts_code=None):
    """配套读取函数，线程安全，读 temp_params 子字段"""
    yaml_path = get_yaml_path(ts_code)

    with yaml_rlock:
        if not os.path.exists(yaml_path):
            return default
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.load(f) or {}
        tp = data.get("temp_params", {})
        return tp.get(sub_key, default)


if __name__ == '__main__':
    set_temp_param("temp_direction", "rise")
