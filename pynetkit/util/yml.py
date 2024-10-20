#  Copyright (c) Kuba Szczodrzyński 2024-10-19.

import re

import yaml


class MyDumper(yaml.Dumper):
    def increase_indent(self, flow=False, **_):
        return super(MyDumper, self).increase_indent(flow, False)


# noinspection DuplicatedCode
def yaml_dump(data: dict | list) -> str:
    # copied from upk2esphome
    text = yaml.dump(data, sort_keys=False, Dumper=MyDumper)
    text = re.sub(r"'!(\w+) (.+)'", r"!\1 \2", text)
    text = re.sub(r"\n([a-z])", r"\n\n\1", text)
    text = text.replace("'", '"')
    # generate comments for quoted strings with _\d+ keys
    text = re.sub(r'_\d+: "(.+?)"', r"# \1", text)
    # generate comments for unquoted strings _\d+ keys
    text = re.sub(r"_\d+: (.+?)", r"# \1", text)
    # text = text.replace(" {}", "")
    # text = text.replace("{}", "")
    return text.strip()


def yaml_load(data: str) -> dict | list:
    return yaml.safe_load(data)
