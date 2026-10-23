# Copyright: (c) 2025 KIKUCHI Koichiro (@koichirok)
# MIT License (see LICENSE or https://opensource.org/license/mit/)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import os
import struct
import sys
from collections import OrderedDict
from typing import Optional


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
    elif value.find(",") >= 0:
        return ", "
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

    def __setitem__(self, name: str, value: object):
        if name not in self.config:
            raise KeyError(f"Unknown Postfix parameter: {name}")

        if isinstance(value, list):
            value = guess_separator(name, self.config[name]).join(map(str, value))
        else:
            value = str(value)

        if self.config[name] != value:
            if self.backup is None:
                self.backup = self.config.copy()
            self.config[name] = value
            # Track changed parameters
            if self.backup[name] != value:
                self.new_params[name] = value
            else:
                self.new_params.pop(name, None)

    def __contains__(self, name: str) -> bool:
        return name in self.config

    def __str__(self) -> str:
        return str_config_dict(self.config)

    def __iter__(self):
        yield from self.config

    def keys(self):
        yield from self.config.keys()

    def items(self):
        yield from self.config.items()

    def values(self):
        yield from self.config.values()

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
        if not self.new_params:
            return []

        # execve counts encoded strings, NUL terminators and argv/envp pointers.
        pointer_size = struct.calcsize("P")
        environment_size = sum(len(os.fsencode(f"{k}={v}")) + 1 + pointer_size for k, v in os.environ.items())
        budget = self.arg_max - environment_size - 2 * pointer_size - 2048
        max_arg_length = 32 * os.sysconf("SC_PAGESIZE") if sys.platform == "linux" else None
        cmds = []
        cmd = self._make_command_base()
        cmd.append("-e")
        base_command_length = sum(len(os.fsencode(i)) + 1 + pointer_size for i in cmd)
        if max_arg_length is not None and any(len(os.fsencode(i)) + 1 > max_arg_length for i in cmd):
            raise ValueError("Postconf command path exceeds the single-argument limit")
        params = []
        cmd_length = base_command_length
        for k, v in self.new_params.items():
            param = f"{k}={v}"
            string_length = len(os.fsencode(param)) + 1
            if max_arg_length is not None and string_length > max_arg_length:
                raise ValueError(f"Postfix parameter {k} exceeds the single-argument limit ({max_arg_length} bytes)")
            param_length = string_length + pointer_size
            if base_command_length + param_length > budget:
                raise ValueError(f"Postfix parameter {k} exceeds the available command argument budget")
            if params and cmd_length + param_length > budget:
                cmds.append(cmd + params)
                params = []
                cmd_length = base_command_length
            params.append(param)
            cmd_length += param_length
        if params:
            cmds.append(cmd + params)
        return cmds
