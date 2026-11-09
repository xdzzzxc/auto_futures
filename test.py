import os
from ruamel.yaml import YAML
from pathlib import Path

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CFG_POOL_PATH = os.path.join(_BASE_DIR, "cfg_pool.yaml")
_last_cfg_mtime = 0.0
print(CFG_POOL_PATH)

if __name__ == '__main__':
    pass