#!/bin/sh
# Run once on the VM from /opt/tldr_linebot after creating .env.
set -eu
cd "$(dirname "$0")/.."
test -f .env || { echo "create .env from .env.example first" >&2; exit 1; }
sudo cp deploy/*.service deploy/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now duckdns-update.timer tldr-update.timer
sudo systemctl start duckdns-update.service tldr-update.service
docker compose ps
