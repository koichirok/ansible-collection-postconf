from __future__ import annotations
from collections import OrderedDict
import pytest


@pytest.fixture
def sample_config_str():
    """Sample postconf configuration string"""
    return (
        "mail_version = 3.8.6\n"
        "config_directory = /etc/postfix\n"
        "myhostname = mail.example.com\n"
        "mydestination = $myhostname, localhost.$mydomain, localhost\n"
        "relayhost = \n"
    )


@pytest.fixture
def sample_config_dict():
    """Dictionary representation of sample postconf configuration"""
    return OrderedDict(
        [
            ("mail_version", "3.8.6"),
            ("config_directory", "/etc/postfix"),
            ("myhostname", "mail.example.com"),
            ("mydestination", "$myhostname, localhost.$mydomain, localhost"),
            ("relayhost", ""),
        ]
    )
