from unittest.mock import patch, DEFAULT, MagicMock, call
import pytest

from ansible_collections.koichirok.postconf.plugins.modules.postconf import PostconfModule
from ansible_collections.koichirok.postconf.plugins.module_utils.postconf import Postconf


@pytest.fixture
def mock_PostconfModule(request, sample_config_str):
    def mock_run_command(cmd):
        if "-e" in cmd:
            if "permission" in cmd[0] and "denied" in cmd[0]:
                return (1, "", "postconf: fatal: open /etc/postfix/main.cf.tmp: Permission denied")  # Simulate permission error
            return (0, "", "")  # Update command succeeds
        elif "-h" in cmd and "config_directory" in cmd:
            return (0, "/etc/postfix", "")  # Config directory command
        elif "nonexistent" in cmd[0]:
            return (1, "", f"No such file or directory: {cmd[0]}")  # Simulate command not found
        return (0, sample_config_str, "")  # Load command

    mock_props = dict(
        run_command=mock_run_command,
        get_bin_path="/usr/sbin/postconf",
        backup_local=lambda src: f"{src}.YYYY-MM-DD@HH:MM:SS~",
        preserved_copy=DEFAULT,
        exit_json=DEFAULT,
        fail_json=DEFAULT,
    )
    if hasattr(request, "param") and isinstance(request.param, dict):
        mock_props.update(request.param)

    with patch.multiple(
        "ansible_collections.koichirok.postconf.plugins.modules.postconf.PostconfModule", **{k: DEFAULT for k, v in mock_props.items()}
    ) as mock:
        for k, v in mock_props.items():
            if k not in mock or v is DEFAULT:
                continue
            if isinstance(v, MagicMock):
                mock[k].side_effect = v.side_effect
                mock[k].return_value = v.return_value
            elif isinstance(v, dict):
                for sub_k, sub_v in v.items():
                    setattr(mock[k], sub_k, sub_v)
            elif callable(v) or isinstance(v, Exception):
                mock[k].side_effect = v
            else:
                mock[k].return_value = v
        yield mock


@pytest.fixture
def mock_main_cf_exists():
    with patch("os.path.isfile", return_value=True):
        yield


@pytest.fixture
def mock_Postconf():
    """Returns a constructor and load() method mocked Postconf class."""
    with patch.object(Postconf, "load", MagicMock()), patch(
        "ansible_collections.koichirok.postconf.plugins.modules.postconf.Postconf"
    ) as mock:
        mock.side_effect = Postconf
        yield mock


def test_PostconfModule_with_default_params(set_module_args, mock_PostconfModule, mock_Postconf):
    """Test PostconfModule constructor with default parameters"""
    set_module_args({})
    mock_Postconf.load = MagicMock()

    module = PostconfModule.newinstance()

    # Verify basic initialization
    assert hasattr(module, "conf")
    assert hasattr(module, "diff")
    assert module.diff == {}

    mock_PostconfModule["get_bin_path"].assert_called_once_with("postconf", required=True)
    mock_PostconfModule["run_command"].assert_called_once()
    mock_PostconfModule["fail_json"].assert_not_called()
    mock_Postconf.assert_called_once_with("/usr/sbin/postconf", None)
    assert isinstance(module.conf.load, MagicMock)
    module.conf.load.assert_called_once()


def test_PostconfModule_with_custom_postconf_path(set_module_args, mock_PostconfModule):
    """Test PostconfModule constructor with custom postconf path"""
    custom_path = "/custom/bin/postconf"
    set_module_args({"postconf_path": custom_path})

    module = PostconfModule.newinstance()
    mock_PostconfModule["get_bin_path"].assert_not_called()
    assert module.conf._bin_path == custom_path


def test_PostconfModule_with_config_dir(set_module_args, mock_PostconfModule):
    """Test PostconfModule constructor with custom config directory"""
    custom_config_dir = "/custom/etc/postfix"
    set_module_args({"config_dir": custom_config_dir})

    module = PostconfModule.newinstance()

    mock_PostconfModule["run_command"].assert_called_once()
    assert mock_PostconfModule["run_command"].call_args[0][0] == ["/usr/sbin/postconf", "-c", custom_config_dir]


def test_PostconfModule_postconf_command_failure(set_module_args, mock_PostconfModule):
    """Test PostconfModule constructor when postconf command fails"""
    set_module_args({"postconf_path": "/nonexistent/path/postconf"})
    module = PostconfModule.newinstance()

    mock_PostconfModule["run_command"].assert_called_once()
    mock_PostconfModule["fail_json"].assert_called_once()
    call_args = mock_PostconfModule["fail_json"].call_args[1]

    assert "Failed to execute postconf" in call_args["msg"]


def test_PostconfModule_relative_postconf_path_resolution(set_module_args, mock_PostconfModule):
    """Test PostconfModule constructor resolves relative postconf path"""
    set_module_args({"postconf_path": "postconf"})  # Relative path

    module = PostconfModule.newinstance()

    mock_PostconfModule["get_bin_path"].assert_called_once_with("postconf", required=True)
    assert module.conf._bin_path == "/usr/sbin/postconf"


def test_PostconfModule_initializes_postconf_instance(set_module_args, mock_PostconfModule, sample_config_dict):
    """Test PostconfModule constructor properly initializes Postconf instance"""
    set_module_args({"postconf_path": "/usr/local/sbin/postconf", "config_dir": "/usr/local/etc/postfix"})

    module = PostconfModule.newinstance()

    # Verify Postconf instance is created correctly
    assert hasattr(module, "conf")
    assert module.conf is not None

    # Verify Postconf instance has correct configuration
    from ansible_collections.koichirok.postconf.plugins.modules.postconf import Postconf

    assert isinstance(module.conf, Postconf)
    assert module.conf._bin_path == "/usr/local/sbin/postconf"
    assert module.conf._config_dir == "/usr/local/etc/postfix"

    # Verify configuration was loaded
    assert module.conf.config == sample_config_dict


def test_PostconfModule_changed_property_delegation(set_module_args, mock_PostconfModule):
    """Test PostconfModule constructor sets up changed property delegation correctly"""
    set_module_args({})

    module = PostconfModule.newinstance()

    assert not module.changed

    # After modifying configuration, should be changed
    module.conf["myhostname"] = "newhost.example.com"
    assert module.changed


def test_PostconfModule_update_config(set_module_args, mock_PostconfModule):
    """Test PostconfModule.update_config method"""
    set_module_args({"config": {"myhostname": "newhost.example.com", "mydestination": ["host1", "host2"]}})

    module = PostconfModule.newinstance()

    # Initially should not be changed
    assert not module.changed
    assert module.conf["myhostname"] == "mail.example.com"
    assert module.conf["mydestination"] == "$myhostname, localhost.$mydomain, localhost"

    # Call update_config
    module.update_config()

    # Should be changed after update
    assert module.changed
    assert module.conf["myhostname"] == "newhost.example.com"
    # List values should be joined appropriately
    assert "host1" in module.conf["mydestination"]
    assert "host2" in module.conf["mydestination"]


def test_PostconfModule_update_config_unknown_parameter(set_module_args, mock_PostconfModule):
    """Test PostconfModule.update_config with unknown parameter"""
    set_module_args({"config": {"unknown_parameter": "value"}})

    module = PostconfModule.newinstance()
    module.update_config()

    # Should call fail_json for unknown parameter
    mock_PostconfModule["fail_json"].assert_called_once()
    call_args = mock_PostconfModule["fail_json"].call_args[1]
    assert call_args["msg"] == "Unknown Postfix parameter: unknown_parameter"


def test_PostconfModule_run_unchanged_diff(set_module_args, mock_PostconfModule):
    set_module_args({"config": {"myhostname": "mail.example.com"}, "_ansible_diff": True})
    module = PostconfModule.newinstance()
    module.run()
    result = mock_PostconfModule["exit_json"].call_args.kwargs
    assert result["changed"] is False
    assert result["diff"]["before"] == result["diff"]["after"]
    mock_PostconfModule["run_command"].assert_called_once()


def test_PostconfModule_build_diff(set_module_args, mock_PostconfModule):
    """Test PostconfModule.build_diff method"""
    set_module_args({"config": {"myhostname": "newhost.example.com"}})

    module = PostconfModule.newinstance()
    module.update_config()

    # Build diff
    module.build_diff()

    # Should have before and after in diff
    assert "before" in module.diff
    assert "after" in module.diff
    assert "myhostname = mail.example.com" in module.diff["before"]
    assert "myhostname = newhost.example.com" in module.diff["after"]


def test_PostconfModule_make_backup_default(set_module_args, mock_PostconfModule, mock_main_cf_exists):
    """Test PostconfModule.make_backup method with default suffix"""
    set_module_args({"backup": True})
    module = PostconfModule.newinstance()
    backup_path = module.make_backup()

    mock_PostconfModule["backup_local"].assert_called_once_with("/etc/postfix/main.cf")
    assert backup_path == "/etc/postfix/main.cf.YYYY-MM-DD@HH:MM:SS~"


def test_PostconfModule_make_backup_custom_suffix(set_module_args, mock_PostconfModule, mock_main_cf_exists):
    """Test PostconfModule.make_backup method with custom suffix"""
    set_module_args({"backup": True, "backup_suffix": ".custom"})

    module = PostconfModule.newinstance()
    backup_path = module.make_backup()

    # Should call preserved_copy with custom suffix
    mock_PostconfModule["preserved_copy"].assert_called_once_with("/etc/postfix/main.cf", "/etc/postfix/main.cf.custom")
    assert backup_path == "/etc/postfix/main.cf.custom"


@pytest.mark.parametrize("mock_PostconfModule", [{"preserved_copy": IOError("Permission denied")}], indirect=True)
def test_PostconfModule_make_backup_copy_error(set_module_args, mock_PostconfModule, mock_main_cf_exists):
    """Test PostconfModule.make_backup method when copy fails"""
    set_module_args({"backup": True, "backup_suffix": ".custom"})

    module = PostconfModule.newinstance()
    module.make_backup()

    # Should call fail_json when copy fails
    mock_PostconfModule["fail_json"].assert_called_once()
    call_args = mock_PostconfModule["fail_json"].call_args[1]
    assert "Could not make backup" in call_args["msg"]


@pytest.mark.parametrize("suffix", [None, ".bak"])
def test_PostconfModule_missing_backup_source(set_module_args, mock_PostconfModule, tmp_path, suffix):
    set_module_args({"config_dir": str(tmp_path), "backup": True, "backup_suffix": suffix})
    module = PostconfModule.newinstance()
    with patch("os.path.isfile", return_value=False), patch.object(module, "fail_json", side_effect=SystemExit):
        with pytest.raises(SystemExit):
            module.make_backup()
        module.fail_json.assert_called_once_with(msg=f"main.cf not found in {tmp_path}")
    mock_PostconfModule["backup_local"].assert_not_called()
    mock_PostconfModule["preserved_copy"].assert_not_called()


@pytest.mark.parametrize("check_mode", [False, True])
def test_PostconfModule_invalid_command_fails_before_backup(set_module_args, mock_PostconfModule, check_mode):
    set_module_args({"config": {"myhostname": "x" * 1000}, "backup": True, "_ansible_check_mode": check_mode})
    module = PostconfModule.newinstance()
    module.conf.arg_max = 1
    with patch.object(module, "fail_json", side_effect=SystemExit), patch.object(module, "make_backup") as backup:
        with pytest.raises(SystemExit):
            module.run()
        assert "argument budget" in module.fail_json.call_args.kwargs["msg"]
        backup.assert_not_called()
    mock_PostconfModule["run_command"].assert_called_once()


def test_PostconfModule_apply_changes_success(set_module_args, mock_PostconfModule):
    """Test PostconfModule.commit method success"""
    set_module_args({"config": {"myhostname": "newhost.example.com"}})

    module = PostconfModule.newinstance()
    module.update_config()
    module.apply_changes()

    # Should have called run_command multiple times
    assert mock_PostconfModule["run_command"].call_args_list == [
        call(["/usr/sbin/postconf"]),
        call(["/usr/sbin/postconf", "-e", "myhostname=newhost.example.com"]),
    ]


def test_PostconfModule_apply_changes_failure(set_module_args, mock_PostconfModule):
    """Test PostconfModule.apply_changes method failure"""
    set_module_args({"config": {"myhostname": "newhost.example.com"}, "postconf_path": "/permission/denied/sbin/postconf"})

    module = PostconfModule.newinstance()
    module.update_config()
    module.apply_changes()

    # Should call fail_json when apply_changes fails
    mock_PostconfModule["fail_json"].assert_called_once()
    call_args = mock_PostconfModule["fail_json"].call_args[1]
    assert "Failed to apply new configuration" in call_args["msg"]


def test_PostconfModule_run_no_changes(set_module_args, mock_PostconfModule):
    """Test PostconfModule.run method when no changes are made"""
    set_module_args({})

    module = PostconfModule.newinstance()
    module.run()

    # Should call exit_json with changed=False
    mock_PostconfModule["exit_json"].assert_called_once()
    call_args = mock_PostconfModule["exit_json"].call_args[1]
    assert call_args["changed"] is False


@pytest.mark.parametrize("mock_PostconfModule", [{"make_backup": DEFAULT}], indirect=True)
def test_PostconfModule_run_with_changes_normal_mode(set_module_args, mock_PostconfModule):
    """Test PostconfModule.run method with changes in normal mode"""
    set_module_args({"config": {"myhostname": "newhost.example.com"}})

    module = PostconfModule.newinstance()
    module.run()

    assert mock_PostconfModule["run_command"].call_args_list == [
        call(["/usr/sbin/postconf"]),
        call(["/usr/sbin/postconf", "-e", "myhostname=newhost.example.com"]),
    ]
    mock_PostconfModule["make_backup"].assert_not_called()
    mock_PostconfModule["exit_json"].assert_called_once()
    assert mock_PostconfModule["exit_json"].call_args[1]["changed"] is True
    assert "diff" not in mock_PostconfModule["exit_json"].call_args[1]


@pytest.mark.parametrize("mock_PostconfModule", [{"make_backup": DEFAULT}], indirect=True)
def test_PostconfModule_run_with_changes_check_mode_and_diff(set_module_args, mock_PostconfModule):
    """Test PostconfModule.run method with changes in check mode"""
    set_module_args({"config": {"myhostname": "newhost.example.com"}, "_ansible_check_mode": True, "_ansible_diff": True})

    module = PostconfModule.newinstance()
    assert module.check_mode is True
    assert module._diff is True
    module.run()

    mock_PostconfModule["run_command"].assert_called_once_with(["/usr/sbin/postconf"])
    mock_PostconfModule["make_backup"].assert_not_called()
    mock_PostconfModule["exit_json"].assert_called_once()
    result = mock_PostconfModule["exit_json"].call_args[1]
    assert result["changed"] is True
    assert "diff" in result


@pytest.mark.parametrize("mock_PostconfModule", [{"make_backup": DEFAULT}], indirect=True)
def test_PostconfModule_run_with_backup_enabled(set_module_args, mock_PostconfModule):
    """Test PostconfModule.run method with backup enabled"""
    set_module_args({"config": {"myhostname": "newhost.example.com"}, "backup": True})
    module = PostconfModule.newinstance()
    module.run()

    # Should create backup when changes are made
    mock_PostconfModule["make_backup"].assert_called_once()
    assert mock_PostconfModule["run_command"].call_args_list == [
        call(["/usr/sbin/postconf"]),
        call(["/usr/sbin/postconf", "-e", "myhostname=newhost.example.com"]),
    ]
    mock_PostconfModule["exit_json"].assert_called_once()
    assert mock_PostconfModule["exit_json"].call_args[1]["changed"] is True


@pytest.mark.parametrize("mock_PostconfModule", [{"make_backup": DEFAULT}], indirect=True)
def test_PostconfModule_run_with_diff_enabled(set_module_args, mock_PostconfModule):
    """Test PostconfModule.run method with diff enabled"""
    set_module_args({"config": {"myhostname": "newhost.example.com"}, "_ansible_diff": True})

    module = PostconfModule.newinstance()
    module.run()

    assert mock_PostconfModule["run_command"].call_args_list == [
        call(["/usr/sbin/postconf"]),
        call(["/usr/sbin/postconf", "-e", "myhostname=newhost.example.com"]),
    ]
    mock_PostconfModule["make_backup"].assert_not_called()
    mock_PostconfModule["exit_json"].assert_called_once()
    result = mock_PostconfModule["exit_json"].call_args[1]
    assert result["changed"] is True
    assert "diff" in result
    assert "before" in result["diff"]
    assert "after" in result["diff"]
