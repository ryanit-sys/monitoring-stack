#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
if [[ ! -f .env ]]; then
    cp .env.example .env
    fresh=1
else
    fresh=0
fi
tmp=$(mktemp .env.XXXXXX)
trap 'rm -f "$tmp"' EXIT
cp .env "$tmp"
set_secret() {
    local key="$1" value
    value=$(openssl rand -hex "$2")
    sed -i "/^${key}=/d" "$tmp"
    printf '\n%s=%s\n' "$key" "$value" >> "$tmp"
}
if [[ "$fresh" == 1 ]]; then
    set_secret GRAFANA_ADMIN_PASSWORD 32
    set_secret INFLUXDB_PASSWORD 32
    set_secret INFLUXDB_ADMIN_TOKEN 48
fi
value=$(sed -n 's/^PROMETHEUS_CONFIG_PASSWORD=//p' "$tmp" | tail -n 1)
if [[ ${#value} -lt 16 || "$value" == CHANGE_ME* ]]; then
    set_secret PROMETHEUS_CONFIG_PASSWORD 32
fi
chmod 600 "$tmp"
mv "$tmp" .env
echo '.env prepared; existing database credentials preserved.'
