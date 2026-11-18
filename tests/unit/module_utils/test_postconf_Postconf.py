# tests/test_postconf_Postconf.py

import pytest
import os
import struct
import sys
from pathlib import Path
from collections import OrderedDict
from ansible_collections.koichirok.postconf.plugins.module_utils.postconf import Postconf, dict_config_str


def test_postconf_load_and_str(sample_config_str, sample_config_dict):
    pc = Postconf("/usr/sbin/postconf")
    pc.load(sample_config_str)
    assert pc.config == sample_config_dict
    assert str(pc) == (
        "mail_version = 3.8.6\n"
        "config_directory = /etc/postfix\n"
        "myhostname = mail.example.com\n"
        "mydestination = $myhostname, localhost.$mydomain, localhost\n"
        "relayhost ="
    )


def test_postconf_config_directory_property(sample_config_str):
    pc = Postconf("/usr/sbin/postconf", "/usr/local/etc/postfix")
    pc.load(sample_config_str)
    # Should return the config_directory from config
    assert pc.config_directory == "/usr/local/etc/postfix"


def test_postconf_config_directory_omitted_in_constructor(sample_config_str):
    # Omit config_dir in constructor, should fallback to config value after load
    pc = Postconf("/usr/sbin/postconf")
    pc.load(sample_config_str)
    assert pc.config_directory == "/etc/postfix"
    pc.load(sample_config_str.replace("/etc/postfix", "/another/dir"))
    assert pc.config_directory == "/another/dir"


def test_postconf_config_directory_omitted_and_missing_in_config(sample_config_str):
    # Omit config_dir in constructor and remove from config, should raise
    pc = Postconf("/usr/sbin/postconf")
    pc.load(sample_config_str)
    # Remove config_directory from config to trigger error
    pc.config.pop("config_directory")
    with pytest.raises(RuntimeError):
        pc.config_directory


def test_postconf_get_setitem_and_changed(sample_config_str):
    pc = Postconf("/usr/sbin/postconf")
    pc.load(sample_config_str)
    assert pc["myhostname"] == "mail.example.com"
    assert not pc.changed

    # Change a value
    pc["myhostname"] = "mail2.example.com"
    assert pc["myhostname"] == "mail2.example.com"
    assert pc.changed
    assert pc.new_params == OrderedDict([("myhostname", "mail2.example.com")])

    # Setting back to original removes from new_params
    pc["myhostname"] = "mail.example.com"
    assert not pc.changed
    assert pc.new_params == OrderedDict()


def test_postconf_setitem_list_value(sample_config_str):
    pc = Postconf("/usr/sbin/postconf")
    pc.load(sample_config_str)
    # mydestination uses ", " as separator
    pc["mydestination"] = ["host1", "host2", "host3"]
    assert pc["mydestination"] == "host1, host2, host3"
    assert pc.changed


@pytest.mark.parametrize("value, expected", [(2, "2"), (True, "True"), (False, "False"), (None, "None")])
def test_postconf_scalar_values_are_strings_and_idempotent(value, expected):
    pc = Postconf("/usr/sbin/postconf")
    pc.load("parameter = old")
    pc["parameter"] = value
    assert pc["parameter"] == expected
    assert pc.new_params == {"parameter": expected}
    assert dict_config_str(str(pc)) == pc.config
    pc.load(str(pc))
    pc["parameter"] = value
    assert not pc.changed


def test_postconf_repeated_assignments_and_reverts():
    pc = Postconf("/usr/sbin/postconf")
    pc.load("parameter = 2")
    for value in (3, 3, 4, 2, 2, 5, 2):
        pc["parameter"] = value
        assert pc.changed is (value != 2)
        assert pc.new_params == ({"parameter": str(value)} if value != 2 else {})


def test_postconf_list_separator_compatibility():
    pc = Postconf("/usr/sbin/postconf")
    pc.load("parameter = a,b\ncyrus_sasl_config_path = /a:/b")
    pc["parameter"] = ["c", "d"]
    pc["cyrus_sasl_config_path"] = ["/c", "/d"]
    assert pc["parameter"] == "c, d"
    assert pc["cyrus_sasl_config_path"] == "/c:/d"


@pytest.mark.parametrize(
    "name, current, value",
    [
        ("lmtp_pix_workarounds", "disable_esmtp,delay_dotcrlf", ["disable_esmtp", "delay_dotcrlf"]),
        ("lmtp_pix_workarounds", "disable_esmtp,\t delay_dotcrlf", ["disable_esmtp", "delay_dotcrlf"]),
        ("mydestination", "mail.example.test,localhost", ["mail.example.test", "localhost"]),
        ("mydestination", "$myhostname ,\tlocalhost", ["$myhostname", "localhost"]),
        ("mydestination", "mail.example.test \t localhost", ["mail.example.test", "localhost"]),
        ("mydestination", "a, b\tc", ["a", "b", "c"]),
        ("postmulti_stop_commands", "stop \t abort", ["stop", "abort"]),
        ("cyrus_sasl_config_path", "/first:/second", ["/first", "/second"]),
        ("mydestination", "", []),
        ("postmulti_stop_commands", "", []),
        ("cyrus_sasl_config_path", "", []),
        ("mydestination", "2,True,None", [2, True, None]),
    ],
)
def test_postconf_equivalent_lists_preserve_original(name, current, value):
    pc = Postconf("/usr/sbin/postconf")
    pc.load(f"{name} = {current}")
    before = str(pc)
    pc[name] = value
    assert not pc.changed
    assert pc[name] == current
    assert str(pc) == before
    assert pc.backup is None
    assert pc.new_params == {}
    assert pc.make_update_config_commands() == []


@pytest.mark.parametrize(
    "name, current, value, expected",
    [
        ("mydestination", "a,b", ["b", "a"], "b, a"),
        ("lmtp_pix_workarounds", "disable_esmtp,delay_dotcrlf", ["disable_esmtp"], "disable_esmtp"),
        ("mydestination", "a,b", ["a", "c"], "a, c"),
        ("mydestination", "a,b", ["a", "a", "b"], "a, a, b"),
        ("mydestination", "a,b", [], ""),
        ("postmulti_stop_commands", "stop abort", [], ""),
        ("cyrus_sasl_config_path", "/first:/second", [], ""),
        ("postmulti_stop_commands", "stop \t abort", ["abort", "stop"], "abort stop"),
        ("cyrus_sasl_config_path", "/first: /second", ["/first", "/second"], "/first:/second"),
        ("cyrus_sasl_config_path", "/first:/second", ["/second", "/first"], "/second:/first"),
        ("smtpd_banner", "hello,world", ["hello", "world"], "hello, world"),
        ("parameter", "a,b", ["a", "b"], "a, b"),
        ("mydestination", "a,,b", ["a", "b"], "a, b"),
        ("mydestination", "a,b,", ["a", "b"], "a, b"),
        ("mydestination", "a,b", ["a", "", "b"], "a, , b"),
        ("mydestination", "a,b", ["a ", "b"], "a , b"),
        ("mydestination", "{a,b}", ["{a", "b}"], "{a, b}"),
        ("mydestination", "${name?{a,b}:{c,d}}", ["${name?{a", "b}:{c", "d}}"], "${name?{a, b}:{c, d}}"),
        ("mydestination", "(a,b)", ["(a", "b)"], "(a, b)"),
        ("mydestination", '"a,b"', ['"a', 'b"'], '"a, b"'),
        ("mydestination", "a\\,b", ["a\\", "b"], "a\\, b"),
        ("mydestination", "a,b", "a, b", "a, b"),
    ],
)
def test_postconf_non_equivalent_or_complex_values_still_change(name, current, value, expected):
    pc = Postconf("/usr/sbin/postconf")
    pc.load(f"{name} = {current}")
    pc[name] = value
    assert pc.changed
    assert pc[name] == expected
    assert pc.backup == {name: current}
    assert pc.new_params == {name: expected}
    assert pc.make_update_config_commands() == [["/usr/sbin/postconf", "-e", f"{name}={expected}"]]


def test_postconf_list_revert_restores_original_spelling():
    pc = Postconf("/usr/sbin/postconf")
    pc.load("mydestination = a,b")
    pc["mydestination"] = ["c", "d"]
    pc["mydestination"] = ["a", "b"]
    assert pc["mydestination"] == "a,b"
    assert not pc.changed
    assert pc.make_update_config_commands() == []


def test_postconf_setitem_unknown_param(sample_config_str):
    pc = Postconf("/usr/sbin/postconf")
    pc.load(sample_config_str)
    with pytest.raises(KeyError):
        pc["unknown_param"] = "value"


def test_postconf_main_cf_path(sample_config_str):
    pc = Postconf("/usr/sbin/postconf")
    pc.load(sample_config_str)
    assert pc.main_cf_path == "/etc/postfix/main.cf"


def test_postconf_make_get_config_dir_command():
    pc = Postconf("/usr/sbin/postconf")
    assert pc.make_get_config_dir_command() == ["/usr/sbin/postconf", "-h", "config_directory"]


def test_postconf__make_command_base_default_config_dir(sample_config_str):
    pc = Postconf("/usr/sbin/postconf")
    # config_directory not set in constructor, fallback to config value
    pc.load(sample_config_str)
    base = pc._make_command_base()
    assert base == ["/usr/sbin/postconf"]


def test_postconf__make_command_base_with_config_dir():
    pc = Postconf("/usr/sbin/postconf", "/custom/dir")
    base = pc._make_command_base()
    assert base == ["/usr/sbin/postconf", "-c", "/custom/dir"]


def test_postconf__make_command_base_with_non_default_binary():
    pc = Postconf("/opt/postfix/bin/postconf", "/etc/postfix")
    base = pc._make_command_base()
    assert base == ["/opt/postfix/bin/postconf", "-c", "/etc/postfix"]


def test_postconf_make_get_all_config_command():
    pc = Postconf("/usr/sbin/postconf")
    assert pc.make_get_all_config_command() == ["/usr/sbin/postconf"]


def test_postconf_make_get_all_config_command_with_custom_config_dir():
    pc = Postconf("/usr/sbin/postconf", "/custom/dir")
    assert pc.make_get_all_config_command() == ["/usr/sbin/postconf", "-c", "/custom/dir"]


def test_postconf_make_update_config_commands_argmax(sample_config_str, monkeypatch):
    # Simulate a small ARG_MAX to force splitting
    monkeypatch.setattr(os, "environ", {})
    pc = Postconf("/usr/sbin/postconf", "/etc/postfix", arg_max=2200)
    pc.load(sample_config_str)
    pc["myhostname"] = "host1"
    pc["mydestination"] = "a, b, c, d, e, f, g"
    cmds = pc.make_update_config_commands()
    # Should split into two commands due to arg_max
    assert len(cmds) == 2
    assert cmds[0][:3] == ["/usr/sbin/postconf", "-c", "/etc/postfix"]
    assert "-e" in cmds[0]
    assert any("myhostname=host1" in arg for arg in cmds[0])
    assert any("mydestination=a, b, c, d, e, f, g" in arg for arg in cmds[1])


@pytest.mark.parametrize("value", ["x" * 80, "\u3042" * 40])
def test_postconf_command_budget_includes_environment_and_bytes(monkeypatch, value):
    monkeypatch.setattr(os, "environ", {"POSTCONF_TEST": "\u3042" * 10})
    pc = Postconf("/postconf", arg_max=2300)
    pc.load("a = old\nb = old")
    pc["a"] = value
    pc["b"] = value
    commands = pc.make_update_config_commands()
    assert len(commands) == 2
    pointer_size = struct.calcsize("P")
    environment_size = len(os.fsencode("POSTCONF_TEST=" + "\u3042" * 10)) + 1 + pointer_size
    for command in commands:
        size = sum(len(os.fsencode(arg)) + 1 + pointer_size for arg in command)
        assert size + environment_size + 2 * pointer_size + 2048 <= pc.arg_max
        assert len(command) == 3


def test_postconf_rejects_parameter_larger_than_command_budget(monkeypatch):
    monkeypatch.setattr(os, "environ", {})
    pc = Postconf("/postconf", arg_max=2200)
    pc.load("a = old")
    pc["a"] = "x" * 1000
    with pytest.raises(ValueError, match="a.*argument budget"):
        pc.make_update_config_commands()


@pytest.mark.skipif(sys.platform != "linux", reason="Linux per-string argument limit")
def test_postconf_rejects_single_oversized_argument():
    pc = Postconf("/postconf", arg_max=2 * 1024 * 1024)
    pc.load("a = old")
    pc["a"] = "x" * (os.sysconf("SC_PAGESIZE") * 32)
    with pytest.raises(ValueError, match="a.*single-argument limit"):
        pc.make_update_config_commands()


def test_postconf_no_changes_does_not_emit_empty_command():
    pc = Postconf("/postconf", arg_max=1)
    assert pc.make_update_config_commands() == []


@pytest.mark.parametrize("release, version", [("jammy", "3.6.4"), ("noble", "3.8.6")])
def test_postconf_with_real_output_fixtures(release, version):
    fixture = Path(__file__).parents[2] / "fixtures" / f"postconf-output-{release}.txt"
    pc = Postconf("/usr/sbin/postconf")
    pc.load(fixture.read_text(encoding="utf-8"))
    assert pc["mail_version"] == version
    assert pc.config_directory == "/etc/postfix"
    assert pc["relayhost"] == ""
    pc["default_process_limit"] = 100
    assert not pc.changed
    original_workarounds = pc["lmtp_pix_workarounds"]
    pc["default_process_limit"] = 123
    pc["lmtp_pix_workarounds"] = ["disable_esmtp", "delay_dotcrlf"]
    assert pc["lmtp_pix_workarounds"] == original_workarounds
    assert pc.new_params == {"default_process_limit": "123"}
    pc.load(str(pc))
    pc["default_process_limit"] = 123
    pc["lmtp_pix_workarounds"] = ["disable_esmtp", "delay_dotcrlf"]
    assert not pc.changed


@pytest.mark.skipif(sys.platform != "linux", reason="Linux per-string argument limit")
def test_postconf_single_argument_at_limit():
    pc = Postconf("/postconf", arg_max=2 * 1024 * 1024)
    pc.load("a = old")
    limit = os.sysconf("SC_PAGESIZE") * 32
    pc["a"] = "x" * (limit - 3)
    commands = pc.make_update_config_commands()
    assert len(commands) == 1
    assert len(os.fsencode(commands[0][-1])) + 1 == limit


def test_postconf_iter(sample_config_str):
    """Test __iter__ method returns keys iterator"""
    pc = Postconf("/usr/sbin/postconf")
    pc.load(sample_config_str)

    # Test that we can iterate over the keys
    keys_from_iter = list(pc)
    expected_keys = ["mail_version", "config_directory", "myhostname", "mydestination", "relayhost"]
    assert keys_from_iter == expected_keys

    # Test that iteration works in for loop
    keys_from_loop = []
    for key in pc:
        keys_from_loop.append(key)
    assert keys_from_loop == expected_keys


def test_postconf_keys(sample_config_str):
    """Test keys() method returns all configuration keys"""
    pc = Postconf("/usr/sbin/postconf")
    pc.load(sample_config_str)

    keys = list(pc.keys())
    expected_keys = ["mail_version", "config_directory", "myhostname", "mydestination", "relayhost"]
    assert keys == expected_keys

    # Test that keys() returns generator
    keys_gen = pc.keys()
    assert hasattr(keys_gen, "__iter__")
    assert list(keys_gen) == expected_keys


def test_postconf_values(sample_config_str):
    """Test values() method returns all configuration values"""
    pc = Postconf("/usr/sbin/postconf")
    pc.load(sample_config_str)

    values = list(pc.values())
    expected_values = ["3.8.6", "/etc/postfix", "mail.example.com", "$myhostname, localhost.$mydomain, localhost", ""]
    assert values == expected_values

    # Test that values() returns generator
    values_gen = pc.values()
    assert hasattr(values_gen, "__iter__")
    assert list(values_gen) == expected_values


def test_postconf_items(sample_config_str):
    """Test items() method returns key-value pairs"""
    pc = Postconf("/usr/sbin/postconf")
    pc.load(sample_config_str)

    items = list(pc.items())
    expected_items = [
        ("mail_version", "3.8.6"),
        ("config_directory", "/etc/postfix"),
        ("myhostname", "mail.example.com"),
        ("mydestination", "$myhostname, localhost.$mydomain, localhost"),
        ("relayhost", ""),
    ]
    assert items == expected_items

    # Test that items() returns generator
    items_gen = pc.items()
    assert hasattr(items_gen, "__iter__")
    assert list(items_gen) == expected_items


def test_postconf_dict_conversion(sample_config_str):
    """Test that dict(postconf) creates a dictionary from the configuration"""
    pc = Postconf("/usr/sbin/postconf")
    pc.load(sample_config_str)

    config_dict = dict(pc)
    expected_dict = {
        "mail_version": "3.8.6",
        "config_directory": "/etc/postfix",
        "myhostname": "mail.example.com",
        "mydestination": "$myhostname, localhost.$mydomain, localhost",
        "relayhost": "",
    }
    assert config_dict == expected_dict

    # Test that the returned dict is independent
    config_dict["new_key"] = "new_value"
    assert "new_key" not in pc.config
