#!/bin/sh
# Points $DOMAIN (a *.duckdns.org name) at this machine's public IP.
set -eu
. "$(dirname "$0")/../.env"
curl -fsS "https://www.duckdns.org/update?domains=${DOMAIN%.duckdns.org}&token=${DUCKDNS_TOKEN}&ip="
echo
