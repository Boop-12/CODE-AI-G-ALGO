#!/usr/bin/env bash
# Install under /etc/letsencrypt/renewal-hooks/deploy/gnkalgo-docker.sh.
# Certbot runs this as root after successful renewal; no private key is printed.
set -euo pipefail
lineage=${RENEWED_LINEAGE:-/etc/letsencrypt/live/gnkalgo.com}
[[ "$lineage" == /etc/letsencrypt/live/gnkalgo.com ]] || exit 0
tls_dir=/opt/gnkalgo/tls
test -d "$tls_dir"
openssl x509 -in "$lineage/fullchain.pem" -noout -checkhost gnkalgo.com >/dev/null
openssl x509 -in "$lineage/fullchain.pem" -noout -checkhost www.gnkalgo.com >/dev/null
openssl x509 -in "$lineage/fullchain.pem" -noout -checkhost app.gnkalgo.com >/dev/null
owner_uid=$(stat -c %u "$tls_dir")
owner_gid=$(stat -c %g "$tls_dir")
install -o "$owner_uid" -g "$owner_gid" -m 644 "$lineage/fullchain.pem" "$tls_dir/origin.pem"
install -o "$owner_uid" -g "$owner_gid" -m 600 "$lineage/privkey.pem" "$tls_dir/origin.key"
if [[ "$(docker inspect -f '{{.State.Running}}' gnkalgo-nginx-1 2>/dev/null || true)" == true ]]; then
    docker exec gnkalgo-nginx-1 nginx -t
    docker exec gnkalgo-nginx-1 nginx -s reload
fi
