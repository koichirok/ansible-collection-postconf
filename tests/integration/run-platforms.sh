#!/bin/sh
set -eu

cd "$(dirname "$0")/../.."

if [ "$#" -eq 0 ]; then
    set -- debian13 ubuntu2404 rocky9 alma9 fedora43 alpine323 ubuntu2204 debian12
fi

status=0
for platform do
    case "$platform" in
        debian13) base=debian:trixie-slim; python=3.13 ;;
        ubuntu2404) base=ubuntu:24.04; python=3.12 ;;
        rocky9) base=rockylinux:9; python=3.9 ;;
        alma9) base=almalinux:9; python=3.9 ;;
        fedora43) base=fedora:43; python=3.14 ;;
        alpine323) base=alpine:3.23; python=3.12 ;;
        ubuntu2204) base=ubuntu:22.04; python=3.10 ;;
        debian12) base=debian:bookworm-slim; python=3.11 ;;
        *)
            echo "Unknown platform: $platform" >&2
            exit 2
            ;;
    esac

    image="postconf-integration:$platform"
    if ! docker build --build-arg "BASE_IMAGE=$base" -t "$image" tests/integration/containers; then
        echo "RESULT $platform PREPARATION FAILED" >&2
        status=1
        continue
    fi
    for target in postconf postconf_no_unnecessary_changes; do
        echo "=== $platform: $target ==="
        if ansible-test integration "$target" --allow-destructive --allow-root \
            --target "docker:$image,python=$python@/usr/bin/python3,cgroup=none,audit=none"; then
            echo "RESULT $platform $target PASS"
        else
            rc=$?
            echo "RESULT $platform $target FAIL (exit $rc)" >&2
            status=1
        fi
    done
done
exit "$status"
