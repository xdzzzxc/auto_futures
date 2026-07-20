import os

def batch_replace(root_dir, old_str, new_str):
    for dirpath, _, filenames in os.walk(root_dir):
        for fname in filenames:
            if fname.endswith(".py"):
                file_path = os.path.join(dirpath, fname)
                # 兼容多种编码读取
                content = None
                for enc in ["utf-8", "gbk", "gb2312"]:
                    try:
                        with open(file_path, "r", encoding=enc) as f:
                            content = f.read()
                        break
                    except UnicodeDecodeError:
                        continue
                if content is None:
                    print(f"跳过无法解码文件：{file_path}")
                    continue
                if old_str not in content:
                    continue
                new_content = content.replace(old_str, new_str)
                # 统一以utf-8覆盖写入
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print(f"已修改：{file_path}")

if __name__ == "__main__":
    project_root = r"E:\auto_futures"
    # 注意顺序：旧字符串在前，新字符串在后
    batch_replace(project_root, "is_trade_status", "is_trade_status")
    print("全局替换完成！")