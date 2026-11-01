FROM ubuntu:22.04@sha256:0a9887931b0e38af2e3487ed39e29436b0535c4f3f52e57745baaf79d1898956
ARG UBUNTU_MIRROR

LABEL org.opencontainers.image.title="AI4S PyMOL Web"
LABEL org.opencontainers.image.description="Open-source PyMOL with a software-rendered X desktop and noVNC"

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    DISPLAY=:0 \
    VNC_PORT=5900 \
    NOVNC_PORT=6080 \
    NOVNC_HOST=0.0.0.0 \
    LIBGL_ALWAYS_SOFTWARE=1 \
    QT_X11_NO_MITSHM=1

# Ubuntu supplies matching PyMOL, Qt and Python packages.
RUN if [ -n "$UBUNTU_MIRROR" ]; then \
        sed -E -i "s#http://(archive.ubuntu.com/ubuntu|security.ubuntu.com/ubuntu|ports.ubuntu.com/ubuntu-ports)/?#${UBUNTU_MIRROR%/}/#g" /etc/apt/sources.list; \
    fi \
    && apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=30 update \
    && apt-get install -y --no-install-recommends \
        pymol xvfb x11-utils x11vnc novnc websockify fluxbox \
        fonts-dejavu-core libgl1-mesa-dri tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --user-group --uid 1000 --shell /bin/bash pymol \
    && mkdir /data \
    && chown pymol:pymol /data

COPY start.sh /usr/local/bin/start-pymol-web
RUN chmod 755 /usr/local/bin/start-pymol-web

USER pymol
WORKDIR /data
EXPOSE 6080

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/start-pymol-web"]
CMD []
