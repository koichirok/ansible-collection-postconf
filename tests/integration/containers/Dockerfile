ARG BASE_IMAGE=debian:trixie-slim
FROM ${BASE_IMAGE}

COPY prepare.sh /prepare-integration.sh
RUN sh /prepare-integration.sh

CMD ["sh", "-c", "mkdir -p /run/sshd && exec /usr/sbin/sshd -D -e"]
