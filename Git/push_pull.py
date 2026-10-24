from pathlib import Path
from public.shared_data import get_data_cache_dir
from git import Repo

project_path = Path(get_data_cache_dir()).parent.parent
print(f"git工作目录 >>> {project_path}")


def git_push_files(file_list: list, branch="main", commit_msg="auto futures update"):
    """
    只提交并推送指定文件列表
    :param file_list: list[Path/str]，文件相对/绝对路径，例如 ["data/a.json", Path("config/setting.yaml")]
    :param branch: 推送分支
    :param commit_msg: 提交备注
    :return: bool
    """
    try:
        repo = Repo(project_path)
        # 把路径转为相对于仓库根目录的字符串
        rel_files = []
        for fp in file_list:
            p = Path(fp)
            if p.is_absolute():
                rel_p = p.relative_to(project_path)
            else:
                rel_p = p
            rel_files.append(str(rel_p))

        # add 指定文件，不再 add(all=True)
        repo.git.add(rel_files)

        # 【优化】仅判断本次待提交文件是否存在变更，不受仓库其他untracked文件干扰
        has_change = False
        for f in rel_files:
            if repo.is_dirty(path=f, untracked_files=True):
                has_change = True
                break
        if has_change:
            repo.index.commit(commit_msg)
        else:
            print("文件无变更，无需提交推送")
            return True

        print("正在推送远程更新......")
        origin = repo.remote("origin")
        origin.push(branch)
        print("\r✅ 指定文件推送完毕！", flush=True, end="")
        return True
    except Exception as e:
        print(f"\r推送异常：{e}", flush=True, end="")
        return False


def git_pull_single_file(file_path, branch="main"):
    """
    单独拉取远程分支上的单个文件，覆盖本地对应文件
    不会拉取整个分支、不会重置整个仓库，只覆盖这一个文件
    :param file_path: str/Path 文件路径，相对仓库根目录
    :param branch: 远程分支名
    :return: bool
    """
    try:
        repo = Repo(project_path)
        origin = repo.remote("origin")
        # 只fetch目标分支，不抓取全部远程分支
        origin.fetch(branch)

        p = Path(file_path)
        if p.is_absolute():
            rel_p = p.relative_to(project_path)
        else:
            rel_p = p
        rel_p = str(rel_p)

        # 保护：检测目标文件本地是否存在未提交修改，防止意外覆盖丢失代码
        changed_files = [item.a_path for item in repo.index.diff(None)]
        untracked_files = repo.untracked_files
        if rel_p in changed_files or rel_p in untracked_files:
            print(f"\r⚠️ 本地文件 {rel_p} 存在未提交改动，禁止覆盖，请先提交或备份", flush=True, end="")
            return False

        # 检出远程分支上该文件，覆盖本地
        repo.git.checkout(f"origin/{branch}", "--", rel_p)
        print(f"\r✅ 文件 {rel_p} 已从远程{branch}覆盖本地", flush=True, end="")
        return True
    except Exception as e:
        print(f"\r单独拉取文件异常：{e}", flush=True, end="")
        return False


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
    git_push()  # 将本地文件上传到GIT仓库
    # git_pull()  # 从GIT仓库拉取文件到本地项目文件夹
    # 单独拉取文件
    # git_pull_single_file("core/monitor.py", branch="main")
    pass
