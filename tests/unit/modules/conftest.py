from __future__ import annotations
from ansible.module_utils.testing import patch_module_args
import typing as t
import pytest


@pytest.fixture
def set_module_args() -> t.Iterator[t.Callable[[t.Optional[dict[str, t.Any]]], None]]:
    """Fixture to set module args for AnsibleModule tests.
    Obtained from Ansible's own test utilities.
    """
    ctx: t.Optional[t.ContextManager] = None

    def set_module_args(args: t.Optional[dict[str, t.Any]] = None) -> None:
        nonlocal ctx

        if args is None:
            args = {}

        args["_ansible_remote_tmp"] = "/tmp"  # type: ignore
        args["_ansible_keep_remote_files"] = False  # type: ignore

        ctx = t.cast(t.ContextManager, patch_module_args(args))
        ctx.__enter__()

    try:
        yield set_module_args
    finally:
        if ctx:
            ctx.__exit__(None, None, None)
