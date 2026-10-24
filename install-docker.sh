#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MESSAGE_FILE="$SCRIPT_DIR/installer/docker_messages.json"
LANGUAGE="${LC_ALL:-${LC_MESSAGES:-${LANG:-en}}}"
MESSAGE_LANGUAGE=en
[[ "$LANGUAGE" == vi* ]] && MESSAGE_LANGUAGE=vi

msg() {
    local key="$1"
    shift
    python3 - "$MESSAGE_FILE" "$MESSAGE_LANGUAGE" "$key" "$@" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    messages = json.load(stream)
print(messages[sys.argv[2]][sys.argv[3]].format(*sys.argv[4:]), end="")
PY
}

fail() {
    msg "$@" >&2
    printf '\n' >&2
    exit 1
}

[[ "$(uname -s)" == Linux ]] || fail not_linux
command -v docker >/dev/null 2>&1 || fail missing_docker
command -v python3 >/dev/null 2>&1 || fail missing_python
docker compose version >/dev/null 2>&1 || fail missing_compose
[[ -f "$SCRIPT_DIR/factory_management/hooks.py" && -f "$SCRIPT_DIR/pyproject.toml" ]] || fail env_invalid

BACKEND_CONTAINER="${FRAPPE_BACKEND_CONTAINER:-}"
if [[ -z "$BACKEND_CONTAINER" ]]; then
    mapfile -t BACKENDS < <(docker ps --filter 'label=com.docker.compose.service=backend' --format '{{.Names}}')
    ((${#BACKENDS[@]} > 0)) || fail backend_missing
    ((${#BACKENDS[@]} == 1)) || fail backend_ambiguous
    BACKEND_CONTAINER="${BACKENDS[0]}"
fi
docker inspect "$BACKEND_CONTAINER" >/dev/null 2>&1 || fail backend_missing

PROJECT_DIR="$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' "$BACKEND_CONTAINER")"
PROJECT_NAME="$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' "$BACKEND_CONTAINER")"
COMPOSE_FILES_LABEL="$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project.config_files" }}' "$BACKEND_CONTAINER")"
[[ -n "$PROJECT_DIR" && -n "$PROJECT_NAME" && -n "$COMPOSE_FILES_LABEL" ]] || fail bad_compose_metadata
ENV_FILE="$PROJECT_DIR/.env"
[[ -f "$ENV_FILE" ]] || fail env_missing

IFS=',' read -r -a COMPOSE_FILE_PATHS <<< "$COMPOSE_FILES_LABEL"
COMPOSE_ARGS=(--project-directory "$PROJECT_DIR" --project-name "$PROJECT_NAME")
for compose_file in "${COMPOSE_FILE_PATHS[@]}"; do
    [[ "$compose_file" == /* ]] || compose_file="$PROJECT_DIR/$compose_file"
    [[ -f "$compose_file" ]] || fail compose_file_missing
    COMPOSE_ARGS+=(-f "$compose_file")
done
compose() {
    docker compose "${COMPOSE_ARGS[@]}" "$@"
}

read_env() {
    python3 - "$ENV_FILE" "$1" <<'PY'
import pathlib
import re
import sys

pattern = re.compile(r"^" + re.escape(sys.argv[2]) + r"=(.*)$")
for line in pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    match = pattern.match(line)
    if match:
        value = match.group(1).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        print(value)
        break
PY
}

CUSTOM_IMAGE="$(read_env CUSTOM_IMAGE)"
CUSTOM_TAG="$(read_env CUSTOM_TAG)"
PULL_POLICY="$(read_env PULL_POLICY)"
[[ -n "$CUSTOM_IMAGE" && -n "$CUSTOM_TAG" && -n "$PULL_POLICY" ]] || fail env_invalid
[[ "$PULL_POLICY" == never ]] || fail pull_policy
BASE_IMAGE="$CUSTOM_IMAGE:$CUSTOM_TAG"
docker image inspect "$BASE_IMAGE" >/dev/null 2>&1 || fail image_missing
IMAGE_ARCH="$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$BASE_IMAGE")"
[[ "$IMAGE_ARCH" == linux/amd64 ]] || fail wrong_architecture "$IMAGE_ARCH"

REQUIRED_FRAPPE_VERSION="$(python3 - "$SCRIPT_DIR/release-manifest.json" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["frappe"]["version"])
PY
)"
APP_VERSION="$(python3 - "$SCRIPT_DIR/pyproject.toml" <<'PY'
import sys
import tomllib
with open(sys.argv[1], "rb") as stream:
    print(tomllib.load(stream)["project"]["version"])
PY
)"
RUNNING_FRAPPE_VERSION="$(docker exec "$BACKEND_CONTAINER" bash -lc 'cd /home/frappe/frappe-bench && bench version' | awk '$1 == "frappe" { print $2; exit }')"
[[ "$RUNNING_FRAPPE_VERSION" == "$REQUIRED_FRAPPE_VERSION" ]] || fail wrong_frappe_version "$REQUIRED_FRAPPE_VERSION" "$RUNNING_FRAPPE_VERSION"

mapfile -t SITES < <(docker exec "$BACKEND_CONTAINER" bash -lc 'find sites -mindepth 2 -maxdepth 2 -type f -name site_config.json -printf "%h\n" | sed "s#^sites/##" | sort')
((${#SITES[@]} > 0)) || fail site_missing
for site in "${SITES[@]}"; do
    [[ "$site" =~ ^[A-Za-z0-9.-]+$ ]] || fail bad_site_name
done
[[ -t 0 ]] || fail noninteractive
read -r -p "$(msg confirmation)" answer
[[ "$answer" =~ ^[Yy]$ ]] || { msg cancelled; printf '\n'; exit 0; }

APP_IMAGE_TAG="${CUSTOM_TAG}-fm-${APP_VERSION}"
APP_IMAGE="$CUSTOM_IMAGE:$APP_IMAGE_TAG"
BACKUP_DIR="${FRAPPE_BACKUP_DIR:-$PROJECT_DIR/backups/factory-management-$(date -u +%Y%m%dT%H%M%SZ)}"
install -d -m 0700 "$BACKUP_DIR"
cp --preserve=mode,ownership "$ENV_FILE" "$BACKUP_DIR/project.env"
chmod 0600 "$BACKUP_DIR/project.env"

TEMP_DIR="$(mktemp -d)"
ENV_UPDATED=0
cleanup() {
    status=$?
    if ((status != 0 && ENV_UPDATED == 1)); then
        msg rollback "$BACKUP_DIR" >&2
        printf '\n' >&2
        cp --preserve=mode,ownership "$BACKUP_DIR/project.env" "$ENV_FILE" || true
        compose up -d --no-deps --force-recreate configurator backend frontend websocket queue-short queue-long scheduler >/dev/null 2>&1 || true
    fi
    if ((ENV_UPDATED == 1)); then
        for site in "${SITES[@]}"; do
            compose exec -T backend bench --site "$site" set-maintenance-mode off >/dev/null 2>&1 || true
        done
    fi
    rm -rf -- "$TEMP_DIR"
    return "$status"
}
trap cleanup EXIT

msg backup_started
printf '\n'
for site in "${SITES[@]}"; do
    backup_path="/home/frappe/frappe-bench/sites/$site/private/backups"
    before="$(docker exec "$BACKEND_CONTAINER" find "$backup_path" -maxdepth 1 -type f -printf '%f\n' 2>/dev/null | sort || true)"
    compose exec -T backend bench --site "$site" backup --with-files
    after="$(docker exec "$BACKEND_CONTAINER" find "$backup_path" -maxdepth 1 -type f -printf '%f\n' | sort)"
    new_files="$(comm -13 <(printf '%s\n' "$before") <(printf '%s\n' "$after") | sed '/^$/d')"
    [[ -n "$new_files" ]] || fail backup_missing
    install -d -m 0700 "$BACKUP_DIR/$site"
    while IFS= read -r filename; do
        docker cp "$BACKEND_CONTAINER:$backup_path/$filename" "$BACKUP_DIR/$site/"
    done <<< "$new_files"
    (cd "$BACKUP_DIR/$site" && sha256sum * > SHA256SUMS)
done
msg backup_saved "$BACKUP_DIR"
printf '\n'

msg build_started
printf '\n'
mkdir -p "$TEMP_DIR/context"
cp -a "$SCRIPT_DIR/factory_management" "$TEMP_DIR/context/factory_management"
cp "$SCRIPT_DIR/pyproject.toml" "$TEMP_DIR/context/pyproject.toml"
cp "$SCRIPT_DIR/installer/docker/Containerfile" "$TEMP_DIR/context/Containerfile"
docker build --pull=false --build-arg "BASE_IMAGE=$BASE_IMAGE" -f "$TEMP_DIR/context/Containerfile" -t "$APP_IMAGE" "$TEMP_DIR/context"
docker run --rm --entrypoint /home/frappe/frappe-bench/env/bin/python "$APP_IMAGE" -c 'import importlib; [importlib.import_module("factory_management." + module) for module in ("api_management", "quality_control", "uqqc", "factory_management", "ktg_master_data")]'
msg build_complete "$APP_IMAGE"
printf '\n'

python3 - "$ENV_FILE" "$APP_IMAGE_TAG" <<'PY'
import os
import pathlib
import re
import stat
import sys
import tempfile

path = pathlib.Path(sys.argv[1])
new_value = sys.argv[2]
lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
pattern = re.compile(r"^CUSTOM_TAG=.*(?:\r?\n)?$")
matches = [index for index, line in enumerate(lines) if pattern.match(line)]
if len(matches) != 1:
    raise SystemExit("CUSTOM_TAG must occur exactly once in .env")
line = matches[0]
ending = "\r\n" if lines[line].endswith("\r\n") else "\n" if lines[line].endswith("\n") else ""
lines[line] = f"CUSTOM_TAG={new_value}{ending}"
metadata = path.stat()
fd, temp_name = tempfile.mkstemp(prefix=".env.factory-management.", dir=path.parent)
try:
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
        stream.write("".join(lines))
    os.chmod(temp_name, stat.S_IMODE(metadata.st_mode))
    try:
        os.chown(temp_name, metadata.st_uid, metadata.st_gid)
    except PermissionError:
        pass
    os.replace(temp_name, path)
except BaseException:
    try:
        os.unlink(temp_name)
    except FileNotFoundError:
        pass
    raise
PY
ENV_UPDATED=1

compose up -d --no-deps --force-recreate configurator backend frontend websocket queue-short queue-long scheduler
for attempt in $(seq 1 60); do
    if compose exec -T backend bench version >/dev/null 2>&1; then break; fi
    ((attempt < 60)) || fail backend_missing
    sleep 5
done

msg maintenance_started
printf '\n'
for site in "${SITES[@]}"; do
    compose exec -T backend bench --site "$site" set-maintenance-mode on
done
for site in "${SITES[@]}"; do
    compose exec -T backend bench --site "$site" set-config server_script_enabled 1
    if ! compose exec -T backend bench --site "$site" list-apps | awk '{print $1}' | grep -Fxq factory_management; then
        compose exec -T backend bench --site "$site" install-app factory_management
    fi
    compose exec -T backend bench --site "$site" migrate
done
for site in "${SITES[@]}"; do
    compose exec -T backend bench --site "$site" set-maintenance-mode off
done
ENV_UPDATED=0
msg complete "$APP_VERSION" "$APP_IMAGE" "$BACKUP_DIR"
printf '\n'
