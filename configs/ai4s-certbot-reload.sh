#!/bin/sh
set -eu
if [ "${RENEWED_LINEAGE:-}" = /etc/letsencrypt/live/coder.my-rustdesk.xyz ]; then
    /usr/sbin/nginx -t
    systemctl reload nginx
fi
