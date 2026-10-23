#!/bin/sh
set -eu

if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y python3 python3-apt openssh-server openssh-client procps rsync tar gzip
elif command -v dnf >/dev/null 2>&1; then
    dnf install -y python3 openssh-server openssh-clients procps-ng rsync tar gzip
elif command -v apk >/dev/null 2>&1; then
    apk add --no-cache python3 openssh-server openssh-client procps rsync tar gzip
else
    echo "Unsupported container package manager" >&2
    exit 1
fi

mkdir -p /run/sshd
ssh-keygen -A
