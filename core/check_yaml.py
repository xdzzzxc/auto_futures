# check_yaml.py
import yaml
import os

YAML_FILE = "cfg_pool.yaml"

def validate_yaml(filepath: str):
    if not os.path.exists(filepath):
        print(f"❌文件不存在: {filepath}")
        return False
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        print(f"✅YAML语法校验通过，下面是[{filepath}]配置文件解析结果：\n{data}")
        print(f"顶层key列表：{list(data.keys())}")
        # 简单业务校验：检查是否存在common_conditions
        if "common_conditions" in data:
            cc = data["common_conditions"]
            if not isinstance(cc, list):
                print("⚠️业务校验警告：common_conditions必须是列表（带-）")
        return True
    except yaml.YAMLError as e:
        print("❌YAML语法错误！")
        if hasattr(e, "problem_mark"):
            mark = e.problem_mark
            print(f"错误行号：Line {mark.line+1}, Column {mark.column+1}")
            print(f"错误描述：{e.problem}")
        print(e)
        return False

if __name__ == "__main__":
    validate_yaml(YAML_FILE)
