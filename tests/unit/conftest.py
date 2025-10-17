from __future__ import annotations
from ansible.module_utils.testing import patch_module_args
import typing as t
from os import path
from collections import OrderedDict
import pytest


@pytest.fixture
def set_module_args() -> t.Iterator[t.Callable[[t.Optional[dict[str, t.Any]]], None]]:
    ctx: t.Optional[t.ContextManager] = None

    def set_module_args(args: t.Optional[dict[str, t.Any]] = None) -> None:
        nonlocal ctx

        args["_ansible_remote_tmp"] = "/tmp"  # type: ignore
        args["_ansible_keep_remote_files"] = False  # type: ignore

        ctx = t.cast(t.ContextManager, patch_module_args(args))
        ctx.__enter__()

    try:
        yield set_module_args
    finally:
        if ctx:
            ctx.__exit__(None, None, None)


@pytest.fixture
def sample_config_str():
    return (
        "mail_version = 3.8.6\n"
        "config_directory = /etc/postfix\n"
        "myhostname = mail.example.com\n"
        "mydestination = $myhostname, localhost.$mydomain, localhost\n"
        "relayhost = \n"
    )


@pytest.fixture
def sample_config_dict():
    return OrderedDict(
        [
            ("mail_version", "3.8.6"),
            ("config_directory", "/etc/postfix"),
            ("myhostname", "mail.example.com"),
            ("mydestination", "$myhostname, localhost.$mydomain, localhost"),
            ("relayhost", ""),
        ]
    )
