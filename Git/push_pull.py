from pathlib import Path
from public.shared_data import get_data_cache_dir
from git import Repo

project_path = Path(get_data_cache_dir()).parent.parent
print(project_path)

def git_push(branch="main", commit_msg="auto futures update"):
    try:
        repo = Repo(project_path)
        # git add .
        repo.git.add(all=True)
        # 存在变更才提交，避免空提交报错
        if repo.is_dirty(untracked_files=True):
            repo.index.commit(commit_msg)
        print("正在推送远程更新......")
        origin = repo.remote("origin")
        origin.push(branch)
        print("\r✅ 推送完毕！", flush=True, end="")
        return True
    except Exception as e:
        print(f"\r推送异常：{e}", flush=True, end="")
        return False

def git_pull(branch="main"):
    try:
        repo = Repo(project_path)
        origin = repo.remote("origin")
        print("正在拉取远程完整代码并覆盖本地...")
        # 1. 拉取远程所有最新提交
        origin.fetch()
        # 2. 硬重置本地分支，完全对齐远程，丢弃本地所有修改
        repo.index.reset(commit=f"origin/{branch}", hard=True)
        # 3. 删除本地未跟踪的文件/文件夹，彻底清理多余本地文件
        repo.git.clean("-fd")
        print("\r✅ 远程代码已完全覆盖本地", flush=True, end="")
        return True
    except Exception as e:
        print(f"\r拉取覆盖异常：{e}", flush=True, end="")
        return False


if __name__ == '__main__':
    pass
    git_push()
    # git_pull()
