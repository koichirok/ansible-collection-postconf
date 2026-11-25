# koichirok.postconf

This collection provides the `koichirok.postconf.postconf` module for managing
Postfix configuration parameters.

The module is designed to work with the Postfix configuration already present
on the host: it reads the current values and changes only the parameters you
specify, using `postconf`. It does not replace `main.cf` with a role-provided
template, install Postfix, or reload or restart the service. Unspecified
parameters are left as they are. Check mode, diff mode, and optional backups are
supported.

## Requirements and installation

- ansible-core 2.16.14 or later on the controller.
- Postfix and Python 3.6 or later on the managed host. The selected ansible-core
  release may require a newer managed-host Python; its requirements also apply.
  Python 2 and Python 3.5 or earlier are not supported.
- Permission to update the selected Postfix configuration directory.

EL7's default Python 2 is not supported. EL8's platform Python 3.6 meets this
collection's minimum but not the managed-host requirements of newer ansible-core
releases. Install a suitable Python and set `ansible_python_interpreter` when
necessary; do not select an obsolete ansible-core solely to retain an old Python.

To install from a source checkout before publishing to Ansible Galaxy, run from
the collection directory:

```sh
ansible-galaxy collection build
ansible-galaxy collection install ./koichirok-postconf-1.0.0.tar.gz
```

Once the collection is published to Ansible Galaxy, install it with:

```sh
ansible-galaxy collection install koichirok.postconf
```

Or, after publication, declare it in a collection requirements file:

```yaml
collections:
  - name: koichirok.postconf
```

This is a collection, not a standalone role-library module. When migrating from
`rworks.postfix`, install the collection and replace the short module name
`postconf` in the role's tasks with `koichirok.postconf.postconf`. Role dependencies
and collection requirements are separate; a role dependency does not install this
collection.

## Usage

```yaml
- name: Configure Postfix
  become: true
  koichirok.postconf.postconf:
    config:
      myhostname: mail.example.com
      default_process_limit: 100
      smtpd_sasl_auth_enable: "yes"
      mydestination:
        - $myhostname
        - localhost
      relayhost: ""
    backup: true
```

Use `config_dir` to select a configuration directory and `postconf_path` to
select the executable. With `backup: true`, changes create a timestamped backup
unless `backup_suffix` is specified, for example `.bak`. Backups are not made
in check mode or when there are no changes. A missing `main.cf` is an error when
a backup is requested for a change.

Values other than lists are converted using Python's `str()`, as in the original
Rworks module: `2` becomes `"2"`, booleans become `"True"` / `"False"`, and null
becomes `"None"`. These are literal strings, not Postfix boolean or empty-value
conversions. Quote `"yes"` and `"no"` for Postfix boolean parameters, and use `""`
to clear a value. List elements are stringified and joined with `", "` for
comma-separated values, `" "` for space-separated values, and `":"` for
`cyrus_sasl_config_path`.

List inputs also have a deliberately limited equivalence comparison:

- For `mydestination` and `lmtp_pix_workarounds`, commas (with optional spaces
  or tabs), spaces and tabs separate simple tokens.
- For `postmulti_stop_commands`, spaces and tabs separate simple tokens.
- Simple tokens contain only ASCII letters, digits, `_`, `.`, `$`, `/` and `-`.
  Both the current value and every stringified input element must fit this
  grammar. Elements must be nonempty; order and duplicates are preserved.
  Repeated/trailing commas, expressions, braces, parentheses, quotes, escapes
  and whitespace inside input elements are not normalized.
- Other parameters and complex values retain the existing exact string
  comparison after joining. In particular, `cyrus_sasl_config_path` still uses
  `:` and does not strip whitespace from paths. Scalar inputs are not normalized.
  An empty list still joins to an empty string.

When a list is equivalent within this scope, the existing representation is
retained and that parameter is not updated. If no other parameter changes, the
module reports `changed=false`, produces an identical diff before/after, and
does not run `postconf -e`, rewrite the configuration, or create or overwrite
a backup. This also applies when the effective value comes from a built-in
default reported by `postconf -d` rather than an explicit setting in `main.cf`;
no explicit override is added. Actual element or order changes still use the
existing separator-selection and update behavior. This is not a general
Postfix expression parser or an attempt to evaluate variable expansions.

Unknown parameters fail explicitly. Large updates are split into commands using
the OS argument budget, including encoded byte lengths, environment variables,
pointer overhead and a safety margin. Linux's per-argument limit is also checked.
A single parameter that cannot fit fails before backup or any update, including
in check mode. The conservative fallback for systems without `os.sysconf` is
262144 bytes; merely increasing it would not remove per-argument limits. If an
update requires multiple commands and a later command fails, earlier commands
may already have changed the configuration; updates are not transactional.

## Development

Contributor setup, testing instructions, and platform validation details are
in [DEVELOPING.md](DEVELOPING.md).

## License

This collection is distributed under the MIT license.
