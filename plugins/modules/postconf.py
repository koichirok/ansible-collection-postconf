#!/usr/bin/python

# Copyright: (c) 2025 KIKUCHI Koichiro (@koichirok)
# MIT License (see LICENSE or https://opensource.org/license/mit/)

from __future__ import absolute_import, division, print_function

__metaclass__ = type


DOCUMENTATION = r"""
module: postconf
author:
    - KIKUCHI Koichiro (@koichirok)
short_description: Manage Postfix configuration parameters
notes: []
description:
  - Manage Postfix configuration parameters using the postconf command.
requirements:
  - postfix
options:
    config:
        description:
        - A dictionary of Postfix configuration parameters and their desired values.
        - If a parameter is not specified, its current value will be retained.
        - If a parameter is specified with a list value, it will be joined using an appropriate separator.
        - Other values are converted to strings using Python's C(str), including booleans and null.
        - Use quoted C('yes') and C('no') for Postfix boolean settings, and C('') for an empty value.
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
        default: postconf
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
"""

EXAMPLES = r"""
- name: Set multiple Postfix parameters
  koichirok.postconf.postconf:
    config:
      myhostname: mail.example.com
      mydomain: example.com
      mynetworks: 127.0.0.0/8 192.168.1.0/24

- name: Set parameter with backup
  koichirok.postconf.postconf:
    config:
      smtpd_banner: $myhostname ESMTP $mail_name
    backup: true
"""

RETURN = r"""
changed:
    description: Whether the module made any changes
    type: bool
    returned: always
    sample: true
diff:
    description: What changed when C(diff) mode is enabled
    type: dict
    returned: when diff mode is enabled
    contains:
        before:
            description: Configuration before changes
            type: str
            returned: success
        after:
            description: Configuration after changes
            type: str
            returned: success
"""

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_text
from ansible_collections.koichirok.postconf.plugins.module_utils.postconf import Postconf, str_config_dict
import os
import shutil
from typing import Any


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
        if not os.path.isfile(src):
            self.fail_json(msg=f"main.cf not found in {self.conf.config_directory}")
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
            except KeyError as e:
                self.fail_json(msg=to_text(e.args[0]))

    def build_diff(self):
        before = self.conf.backup if self.conf.backup is not None else self.conf.config
        self.diff["before"] = str_config_dict(before)
        self.diff["after"] = str(self.conf)

    def apply_changes(self):
        for cmd in self.conf.make_update_config_commands():
            rc, out, err = self.run_command(cmd)
            if rc != 0:
                self.fail_json(msg=f"Failed to apply new configuration: {err}", rc=rc)

    def run(self) -> None:
        self.update_config()

        try:
            self.conf.make_update_config_commands()
        except ValueError as e:
            self.fail_json(msg=to_text(e))

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
        result["config"] = dict(self.conf.config)
        self.exit_json(**result)


def main():
    module = PostconfModule.newinstance()
    module.run()


if __name__ == "__main__":
    main()
