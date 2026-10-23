# tests/unit/module_utils/test_postconf.py

from ansible_collections.koichirok.postconf.plugins.module_utils.postconf import guess_separator, dict_config_str, str_config_dict


def test_guess_separator():
    assert guess_separator("cyrus_sasl_config_path", "") == ":"
    assert guess_separator("canonical_classes", "envelope_sender, envelope_recipient, header_sender, header_recipient") == ", "
    assert guess_separator("lmtp_pix_workarounds", "disable_esmtp,delay_dotcrlf") == ", "
    assert guess_separator("postmulti_stop_commands", "stop abort drain quick-stop") == " "


def test_dict_config_str(sample_config_str, sample_config_dict):
    d = dict_config_str(sample_config_str)
    assert d["mail_version"] == "3.8.6"
    assert d["myhostname"] == "mail.example.com"
    assert d["config_directory"] == "/etc/postfix"
    assert d == sample_config_dict


def test_str_config_dict(sample_config_dict, sample_config_str):
    s = str_config_dict(sample_config_dict)
    assert s == sample_config_str.rstrip()
