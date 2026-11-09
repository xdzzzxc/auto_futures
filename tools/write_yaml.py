from ruamel.yaml import YAML
from public.shared_data import yaml_rlock

yaml = YAML()
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=2, offset=0)