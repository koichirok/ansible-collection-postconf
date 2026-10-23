#!/bin/sh
set -eu

cd "$(dirname "$0")/../.."
work=$(mktemp -d "${TMPDIR:-/tmp}/postconf-freebsd.XXXXXX")
trap 'rm -r "$work"' EXIT HUP INT TERM
mkdir "$work/source"
tar --exclude=.git --exclude=.venv --exclude=tests/output --exclude=.pytest_cache \
    --exclude=__pycache__ -cf - . | tar -C "$work/source" -xf -

# Sync only a disposable copy: AnyVM copies guest changes back after execution.
docker run --rm --device /dev/kvm:/dev/kvm:rw --entrypoint python3 \
    --mount "type=bind,src=$work/source,dst=/source" \
    ghcr.io/anyvm-org/anyvm@sha256:57b136734c84c23c7ef5395ce593c60b15912382e03e5df58335bc74c21e1685 \
    /anyvm.org/anyvm.py --data-dir /data \
    --os freebsd --release 14.4 --builder 2.2.8 --cpu 2 --mem 4096 \
    --vnc off --remote-vnc no --sync tar -v /source:/source \
    -- 'sh /source/tests/integration/freebsd-guest.sh'
