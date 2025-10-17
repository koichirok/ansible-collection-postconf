# tests/test_postconf_Postconf.py

import pytest
from collections import OrderedDict
from library.postconf import Postconf


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
        _ = pc.config_directory


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


def test_postconf_make_update_config_commands_argmax(sample_config_str):
    # Simulate a small ARG_MAX to force splitting
    pc = Postconf("/usr/sbin/postconf", "/etc/postfix", arg_max=60)
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
