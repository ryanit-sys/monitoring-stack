#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
command -v docker >/dev/null || { echo 'docker is required' >&2; exit 1; }
backup_dir="${1:-./backups/$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
container_id="$(docker compose ps -q influxdb)"
if [[ -z "$container_id" ]]; then
  echo 'InfluxDB is not running.' >&2; exit 1
fi
remote_path="/tmp/tig-backup-$(date -u +%Y%m%dT%H%M%SZ)"
docker compose exec -T -e BACKUP_DIR="$remote_path" influxdb sh -c \
  'influx backup --host http://localhost:8086 --token "$DOCKER_INFLUXDB_INIT_ADMIN_TOKEN" "$BACKUP_DIR"'
docker cp "$container_id:$remote_path" "$backup_dir/influxdb"
docker compose exec -T -e BACKUP_DIR="$remote_path" influxdb sh -c 'rm -rf "$BACKUP_DIR"'
echo "InfluxDB backup complete: $backup_dir/influxdb"
echo 'Back up Grafana named volume consistently and protect .env separately.'
