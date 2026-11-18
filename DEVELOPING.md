# Development and validation

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

## Integration tests

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

### Linux platform matrix

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

The other selectors are `debian13` and `ubuntu2404`. Runs are sequential
because ansible-test generates shared inventory and output files in the
checkout. Do not run multiple matrix scripts or other integration commands
concurrently in the same checkout. Target containers are managed by
ansible-test; locally built `postconf-integration:<platform>` images remain
available for reuse. Base-image tags and package repositories can change; the
output reports the actual distribution, Python and Postfix versions on each
run.

### FreeBSD VM

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
each command returns nonzero if preparation or either target fails. The
Linux platform matrix runs in GitHub Actions for pull requests and pushes to
`main`. The FreeBSD VM runner remains a manual check on a KVM-enabled Linux
host.

### Test coverage

- `postconf`: real command readback, string/integer/empty values, scalar
  conversions, list separators, preservation of unspecified parameters,
  check/diff modes, idempotency, disabled/custom/timestamped backups, and
  explicit errors without partial configuration writes.
- `postconf_no_unnecessary_changes`: submitting effective defaults or
  semantically equivalent list values must not report a change or a diff,
  rewrite `main.cf`, change its modification time/inode/mode, or create a
  backup or temporary file. Each case runs in both normal and check mode, in
  independent directories. Defaults come from the installed `postconf -d`,
  not a distribution-specific fixture. Comments and existing whitespace must
  survive a no-op byte for byte.

The no-change contract includes default comma-separated lists supplied as
lists, and explicitly configured comma-separated lists with or without
spaces. Keep genuine failures visible; do not skip them, mark them as expected
failures, or weaken the assertions. This does not claim to test every form of
Postfix expression or semantic equivalence.

The general target sets its own initial values rather than assuming Postfix
defaults. Assertions compare only relevant parameters across separate command
invocations: runtime values such as `process_id` can differ. Both targets clean
up their configuration directories even after failure. ARG_MAX boundaries and
backup-source disappearance are covered by unit tests rather than
timing-dependent integration scenarios.

The unit suite also covers no-op list assignments (including normal/check
mode, timestamped/custom backup selection and unchanged diffs), order/element
changes, duplicates, empty lists, space/comma/colon separators, conservative
handling of complex syntax and unrelated parameters, and reverting to the
original spelling.

Validation on 2026-10-23: `ansible-test units --python 3.13` passes all 105
tests (62 existing tests plus 43 added regression cases). Before the fix, the
expanded suite reproduced 17 failures. Two existing fixture assertions that
required adding spaces to an unchanged list now require preserving the
original value and updating only the genuinely changed parameter.
On 2026-11-17, `ansible-test sanity --python 3.13` passes with Ansible 2.22.0.
The `validate-modules` GPLv3-header finding is explicitly ignored for Ansible
2.21 and 2.22 because the module is MIT-licensed. The environment lacks
`shellcheck`, so that optional check is not exercised.

### Current integration results

Re-tested on 2026-10-23 with ansible-core 2.21.5, Linux targets in disposable
containers and FreeBSD in a disposable QEMU/KVM VM. Both runner commands
exited successfully:

| Environment | Target Python | Postfix | General target | No-unnecessary-changes target |
| --- | --- | --- | --- | --- |
| Debian 13 | 3.13.5 | 3.10.13 | Pass | 18 cases pass |
| Ubuntu 24.04 | 3.12.3 | 3.8.6 | Pass | 18 cases pass |
| Rocky Linux 9 | 3.9.25 | 3.5.25 | Pass | 18 cases pass |
| AlmaLinux 9 | 3.9.25 | 3.5.25 | Pass | 18 cases pass |
| Fedora 43 | 3.14.8 | 3.10.14 | Pass | 18 cases pass |
| Alpine 3.23 | 3.12.15 | 3.10.13 | Pass | 18 cases pass |
| Ubuntu 22.04 | 3.10.12 | 3.6.4 | Pass | 18 cases pass |
| Debian 12 | 3.11.2 | 3.7.11 | Pass | 18 cases pass |
| FreeBSD 14.4 | 3.12.15 | 3.11.7 | Pass | 18 cases pass |

The previously failing `default_comma_list_as_list` and
`explicit_comma_list_without_spaces` cases now pass in both normal and check
mode on all nine environments. The root cause was joining list inputs with
`", "` and comparing that result literally with the effective value before
deciding whether to write. The limited list comparison described above now
retains the original spelling, including built-in defaults with no explicit
entry in `main.cf`. All existing integration assertions are unchanged: no
skip, xfail or relaxed expectation is used. The 18 cases per environment
verify identical diffs, unchanged content/mtime/inode/mode, and no new backup
or temporary file.
