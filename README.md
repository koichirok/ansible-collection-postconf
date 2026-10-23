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

Install the collection:

```sh
ansible-galaxy collection install koichirok.postconf
```

Or declare it in a collection requirements file:

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

Unknown parameters fail explicitly. Large updates are split into commands using
the OS argument budget, including encoded byte lengths, environment variables,
pointer overhead and a safety margin. Linux's per-argument limit is also checked.
A single parameter that cannot fit fails before backup or any update, including
in check mode. The conservative fallback for systems without `os.sysconf` is
262144 bytes; merely increasing it would not remove per-argument limits.

## Development and validation

From this collection directory, with ansible-core and the test requirements
installed:

```sh
ansible-test units --python 3.13 --requirements
ansible-test sanity --python 3.13 --requirements
```

For direct pytest in this checkout (whose collection namespace is under `/`):

```sh
PYTHONPATH=/ python3 -m pytest --cache-clear --import-mode=importlib
```

Adjust the Python executable to the environment containing ansible-core and
pytest. The import mode avoids name collisions between the module and
module-utils test files.

### Integration tests

The integration targets install Postfix and use temporary configuration
directories. They require root/package-install privileges and network access
to package repositories. Run them only in a disposable test host/container.
They never edit the system `main.cf` or explicitly start, reload or restart
Postfix. Package installation may run the distribution's service hooks.

Use ansible-test's disposable container environment, for example:

```sh
ansible-test integration 'postconf.*' --docker ubuntu2404 --requirements
```

Inside an already provisioned disposable host/container, run each target
separately to see both results even when one fails:

```sh
ansible-test integration postconf --local --allow-destructive
ansible-test integration postconf_no_unnecessary_changes --local --allow-destructive
```

#### Linux platform matrix

From a Linux controller with Docker and ansible-core 2.21.5 installed:

```sh
sh tests/integration/run-platforms.sh
```

This builds small SSH-enabled target images for Debian 13, Ubuntu 24.04,
Rocky Linux 9, AlmaLinux 9, Fedora 43, Alpine 3.23, Ubuntu 22.04 and Debian 12.
Ansible runs on the controller, not the targets, so the target's older Python
does not have to satisfy the controller's Python requirements. Both targets
run for every platform even when the no-change checks fail. The script returns
nonzero if any preparation or test fails and prints a `RESULT` line for each
target. These failures are not suppressed.

To select platforms:

```sh
sh tests/integration/run-platforms.sh rocky9 alma9 fedora43 alpine323 ubuntu2204 debian12
```

The other selectors are `debian13` and `ubuntu2404`. Runs are sequential because
ansible-test generates shared inventory and output files in the checkout.
Do not run multiple matrix scripts or other integration commands concurrently
in the same checkout. Target containers are managed by ansible-test; locally
built `postconf-integration:<platform>` images remain available for reuse.
Base-image tags and package repositories can change; the output reports the
actual distribution, Python and Postfix versions on each run.

#### FreeBSD VM

FreeBSD needs its own kernel; it cannot run as an ordinary Linux container.
The following runner starts a real FreeBSD 14.4 amd64 VM with QEMU inside
Docker, using the public [AnyVM image](https://github.com/anyvm-org/docker)
from the tooling used by
[vmactions/freebsd-vm](https://github.com/vmactions/freebsd-vm):

```sh
sh tests/integration/run-freebsd.sh
```

Requirements are Docker on a Linux host with accessible `/dev/kvm`, roughly
4 GiB of guest RAM and disk space/network access for the VM image and packages.
The container image digest, FreeBSD release and image-builder version are
pinned in the runner. It exposes no host ports, disables VNC/remote VNC, and
copies only a disposable checkout into the VM: AnyVM's copyback cannot alter
the real checkout. The container, VM and disposable copy are removed on exit.
It installs a Python 3.12 virtual environment with ansible-core 2.21.5 inside
the guest, and runs the same two integration targets. FreeBSD's separate
SQLite and cryptography Python packages are installed using `pkg` before
creating the virtual environment.

Run the Linux and FreeBSD commands separately and retain both exit statuses:
the known contract failures make each command return nonzero. The FreeBSD
runner can be used in a KVM-enabled Linux CI job without a separate FreeBSD
host. It has been executed locally; no GitHub Actions workflow is added.

#### Test coverage

- `postconf`: real command readback, string/integer/empty values, scalar
  conversions, list separators, preservation of unspecified parameters,
  check/diff modes, idempotency, disabled/custom/timestamped backups, and
  explicit errors without partial configuration writes.
- `postconf_no_unnecessary_changes`: submitting effective defaults or
  semantically equivalent list values must not report a change or a diff,
  rewrite `main.cf`, change its modification time/inode/mode, or create a
  backup or temporary file. Each case runs in both normal and check mode,
  in independent directories. Defaults come from the installed `postconf -d`,
  not a distribution-specific fixture. Comments and existing whitespace
  must survive a no-op byte for byte.

The no-change contract includes default comma-separated lists supplied as
lists, and explicitly configured comma-separated lists with or without
spaces. This is a requirement, not an assumption that the current module
already satisfies it. Keep genuine failures visible; do not skip them,
mark them as expected failures, or change the module just to pass them
without a separate decision. This does not claim to test every form of
Postfix expression or semantic equivalence.

The general target sets its own initial values rather than assuming Postfix
defaults. Assertions compare only relevant parameters across separate
command invocations: runtime values such as `process_id` can differ.
Both targets clean up their configuration directories even after failure.
ARG_MAX boundaries and backup-source disappearance are covered by unit
tests rather than timing-dependent integration scenarios.

#### Current integration results

Tested with ansible-core 2.21.5, Linux targets in disposable containers and
FreeBSD in a disposable QEMU VM:

| Environment | Target Python | Postfix | General target | No-unnecessary-changes target |
| --- | --- | --- | --- | --- |
| Debian 13 | 3.13.5 | 3.10.13 | Pass | 14 cases pass, 4 fail |
| Ubuntu 24.04 | 3.12.3 | 3.8.6 | Pass | 14 cases pass, 4 fail |
| Rocky Linux 9 | 3.9.25 | 3.5.25 | Pass | 14 cases pass, 4 fail |
| AlmaLinux 9 | 3.9.25 | 3.5.25 | Pass | 14 cases pass, 4 fail |
| Fedora 43 | 3.14.8 | 3.10.14 | Pass | 14 cases pass, 4 fail |
| Alpine 3.23 | 3.12.15 | 3.10.13 | Pass | 14 cases pass, 4 fail |
| Ubuntu 22.04 | 3.10.12 | 3.6.4 | Pass | 14 cases pass, 4 fail |
| Debian 12 | 3.11.2 | 3.7.11 | Pass | 14 cases pass, 4 fail |
| FreeBSD 14.4 | 3.12.15 | 3.11.7 | Pass | 14 cases pass, 4 fail |

The failures are `default_comma_list_as_list` and
`explicit_comma_list_without_spaces`, each in normal and check mode.
For example, the effective default `disable_esmtp,delay_dotcrlf` becomes
`disable_esmtp, delay_dotcrlf` when submitted as a list. The module compares
the strings literally and reports a change despite equivalent list contents.
In normal mode this rewrites the file and creates a backup; check mode reports
a change/diff without writing. These are unresolved contract failures, not
expected-failure exemptions. The module implementation is unchanged by this
integration-test work, pending a decision about equivalent-value comparison.

The collection is distributed under the MIT license.