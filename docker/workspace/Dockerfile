ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

ARG USER_UID=1000
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=3 update \
    && apt-get install -y --no-install-recommends curl git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 coder \
    && useradd --uid "${USER_UID}" --gid 1000 --create-home --shell /bin/bash coder

USER coder
WORKDIR /workspace/project
