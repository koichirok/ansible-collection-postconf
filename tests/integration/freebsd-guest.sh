#!/bin/sh
set -eu

export ASSUME_ALWAYS_YES=yes
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
pkg install --yes expat python312 py312-pip py312-cryptography py312-sqlite3 git
python3.12 -m venv --system-site-packages /venv
/venv/bin/pip install ansible-core==2.21.5
mkdir -p /work/ansible_collections/koichirok/postconf
cp -R /source/. /work/ansible_collections/koichirok/postconf/
cd /work/ansible_collections/koichirok/postconf
export PATH="/venv/bin:$PATH"
uname -a
python --version
ansible-test --version
status=0
for target in postconf postconf_no_unnecessary_changes; do
    if ansible-test integration "$target" --local --allow-destructive; then
        echo "RESULT freebsd14 $target PASS"
    else
        rc=$?
        echo "RESULT freebsd14 $target FAIL (exit $rc)" >&2
        status=1
    fi
done
postconf mail_version
exit "$status"
