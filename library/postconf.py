#!/usr/bin/python

# Copyright: (c) 2025 KIKUCHI Koichiro (@koichirok)
# MIT License (see LICENSE or https://opensource.org/license/mit/)
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: postconf
short_description: Manage Postfix configuration parameters
description:
  - This module allows you to manage Postfix configuration parameters using the postconf command.

options:
    config:
        description:
        - A dictionary of Postfix configuration parameters and their desired values.
        - If a parameter is not specified, its current value will be retained.
        - If a parameter is specified with a list value, it will be joined using an appropriate separator.
        type: dict
        required: false
        default: {}
    config_dir:
        description:
        - The directory containing the Postfix configuration files (e.g., main.cf).
        - If not specified, the module will attempt to determine it using postconf.
        type: path
        required: false
    postconf_path:
        description:
        - The path to the postconf command.
        - If not specified, the module will search for it in the system's PATH.
        type: path
        required: false
    backup:
        description:
        - Whether to create a backup of the main.cf file before making changes.
        - If set to true, a backup will be created if changes are made.
        - If set to false, no backup will be made.
        type: bool
        required: false
        default: false
    backup_suffix:
        description:
        - A custom suffix to append to the backup file name (e.g., '.bak').
        - If not specified and backup is true, a timestamp suffix will be used.
        - If specified, this suffix will be used instead of the timestamp.
        type: str
        required: false

author:
    - KIKUCHI Koichiro (@koichirok)
"""

EXAMPLES = r"""
TBD
"""

RETURN = r"""
TBD
"""

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils._text import to_text
import os
import shutil
from collections import OrderedDict
from typing import Optional, Union, Any


def guess_separator(param: str, value: str, default: str = ", ") -> str:
    """Guess the separator for parameters that can take multiple values.

    Args:
        param: The Postfix configuration parameter name.
        value: The sample value to analyze.
        default: The default separator to return if no specific one is found.
    Returns:
        The guessed separator.
    """
    if param == "cyrus_sasl_config_path":
        return ":"
    elif value.find(", ") >= 0:
        return ", "
    elif value.find(",") >= 0:
        # I'm not sure if this is ever used
        return ","
    elif value.find(" ") >= 0:
        return " "
    return default


def str_config_dict(configdict: dict) -> str:
    """Convert a dictionary representation of Postfix configuration to a string as in postconf output.

    Args:
        configdict: The dictionary to convert.
    Returns:
        The string representation.
    """
    return "\n".join([f"{k} =" + (f" {v}" if v else "") for k, v in configdict.items()])


def dict_config_str(configstr: str) -> "OrderedDict[str, str]":
    """Convert a string representation of Postfix configuration as in postconf output to a dictionary.

    Args:
        configstr: The string to convert.
    Returns:
        The dictionary representation.
    """
    configdict = OrderedDict()
    for line in configstr.strip().split("\n"):
        if "=" in line:
            key, value = line.split("=", 1)
            configdict[key.strip()] = value.strip()
    return configdict


class Postconf:
    def __init__(self, bin_path: str, config_dir: Optional[str] = None, arg_max: Optional[int] = None):
        self.config: OrderedDict[str, str] = OrderedDict()
        self.backup: Optional[OrderedDict[str, str]] = None
        self.new_params: OrderedDict[str, str] = OrderedDict()
        self._bin_path: str = bin_path
        self._config_dir: Optional[str] = config_dir
        self.arg_max: int = arg_max if arg_max is not None else os.sysconf("SC_ARG_MAX") if hasattr(os, "sysconf") else 262144

    def __getitem__(self, name: str) -> str:
        return self.config[name]

    def __setitem__(self, name: str, value: Union[str, "list[str]"]):
        if name not in self.config:
            raise KeyError(f"Unknown Postfix parameter: {name}")

        if isinstance(value, list):
            value = guess_separator(name, self.config[name]).join(map(str, value))

        if self.config[name] != value:
            if self.backup is None:
                self.backup = self.config.copy()
            self.config[name] = value
            # Track changed parameters
            if self.backup[name] != value:
                self.new_params[name] = value
            else:
                del self.new_params[name]

    def __contains__(self, name: str) -> bool:
        return name in self.config

    def __str__(self) -> str:
        return str_config_dict(self.config)

    @property
    def changed(self) -> bool:
        return bool(self.new_params)

    def load(self, configstr: str):
        self.config = dict_config_str(configstr)
        self.backup = None
        self.new_params = OrderedDict()

    @property
    def config_directory(self) -> str:
        if self._config_dir is not None:
            return self._config_dir
        if self.config is not None and "config_directory" in self.config:
            return self.config["config_directory"]
        raise RuntimeError("failed to determine config_directory")

    @property
    def main_cf_path(self) -> str:
        return os.path.join(self.config_directory, "main.cf")

    def _make_command_base(self) -> "list[str]":
        cmd = [self._bin_path]
        if self._config_dir is not None:
            cmd.extend(["-c", self._config_dir])
        return cmd

    def make_get_config_dir_command(self) -> "list[str]":
        return [self._bin_path, "-h", "config_directory"]

    def make_get_all_config_command(self) -> "list[str]":
        return self._make_command_base()

    def make_update_config_commands(self) -> "list[list[str]]":
        cmds = []
        cmd = self._make_command_base()
        cmd.append("-e")
        base_command_length = sum(len(i) for i in cmd) + len(cmd) - 1
        params = []
        cmd_length = base_command_length
        for k, v in self.new_params.items():
            param = f"{k}={v}"
            param_length = 1 + len(param)  # space + param
            if cmd_length + param_length > self.arg_max:
                cmds.append(cmd + params)
                params = []
                cmd_length = base_command_length
            params.append(param)
            cmd_length += param_length
        if params:
            cmds.append(cmd + params)
        return cmds


class PostconfModule(AnsibleModule):
    @staticmethod
    def newinstance() -> "PostconfModule":
        return PostconfModule(
            argument_spec=dict(
                config=dict(type="dict", required=False, default={}),
                config_dir=dict(type="path", required=False),
                postconf_path=dict(type="path", required=False, default="postconf"),
                backup=dict(type="bool", required=False, default=False),
                backup_suffix=dict(type="str", required=False),
            ),
            supports_check_mode=True,
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.diff = {}

        postconf: str = self.params["postconf_path"]
        if not os.path.isabs(postconf):
            postconf = self.get_bin_path(postconf, required=True)  # type: ignore
        self.conf: Postconf = Postconf(postconf, self.params["config_dir"])

        rc, out, err = self.run_command(self.conf.make_get_all_config_command())
        if rc != 0:
            self.fail_json(msg=f"Failed to execute postconf: {err}", rc=rc)
        self.conf.load(out)

    @property
    def changed(self) -> bool:
        return self.conf.changed

    def make_backup(self):
        src = self.conf.main_cf_path
        suffix = self.params["backup_suffix"]
        if suffix is None:
            # Use AnsibleModule's built-in backup mechanism
            dest = self.backup_local(src)
        else:
            dest = src + suffix
            try:
                self.preserved_copy(src, dest)
            except (shutil.Error, IOError) as e:
                self.fail_json(msg="Could not make backup of %s to %s: %s" % (src, dest, to_text(e)))
        return dest

    def update_config(self):
        for param, value in self.params["config"].items():
            try:
                self.conf[param] = value
            except Exception as e:
                self.fail_json(msg=to_text(e))

    def build_diff(self):
        if self.conf.backup is not None:
            self.diff["before"] = str_config_dict(self.conf.backup)
        self.diff["after"] = str(self.conf)

    def apply_changes(self):
        for cmd in self.conf.make_update_config_commands():
            rc, out, err = self.run_command(cmd)
            if rc != 0:
                self.fail_json(msg=f"Failed to apply new configuration: {err}", rc=rc)

    def run(self) -> None:
        self.update_config()

        if self._diff:
            self.build_diff()

        result: dict[str, Any] = {"changed": self.changed}

        if result["changed"]:
            if not self.check_mode:
                if self.params["backup"]:
                    self.make_backup()
                self.apply_changes()
        if self._diff and self.diff:
            result["diff"] = self.diff
        self.exit_json(**result)


def main():
    module = PostconfModule.newinstance()
    module.run()


if __name__ == "__main__":
    main()
