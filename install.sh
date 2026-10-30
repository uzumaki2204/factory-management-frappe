#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
INSTALLER_DIR="$SCRIPT_DIR/installer"
source "$INSTALLER_DIR/messages.sh"

LANGUAGE="${LC_ALL:-${LC_MESSAGES:-${LANG:-en}}}"
if [[ "$LANGUAGE" == vi* ]]; then
    MESSAGE_LANGUAGE=vi
else
    MESSAGE_LANGUAGE=en
fi

msg() {
    local key="$1"
    if [[ "$MESSAGE_LANGUAGE" == vi ]]; then
        printf '%s\n' "${MSG_VI[$key]:-$key}"
    else
        printf '%s\n' "${MSG_EN[$key]:-$key}"
    fi
}

msgf() {
    local key="$1"
    shift
    if [[ "$MESSAGE_LANGUAGE" == vi ]]; then
        printf "${MSG_VI[$key]:-$key}\n" "$@"
    else
        printf "${MSG_EN[$key]:-$key}\n" "$@"
    fi
}

fail() {
    msg "$1" >&2
    exit 1
}

FRAPPE_USER="${FRAPPE_USER:-frappe}"
FRAPPE_BENCH_DIR="${FRAPPE_BENCH_DIR:-/opt/frappe-bench}"
FRAPPE_SITE_NAME="${FRAPPE_SITE_NAME:-}"
DB_ADMIN_USER="frappe_installer"

[[ "$EUID" -eq 0 ]] || fail not_root
[[ -f /etc/os-release ]] || fail unsupported_os
# shellcheck disable=SC1091
source /etc/os-release

version_at_least() {
    local actual_major actual_minor minimum_major minimum_minor

    [[ "${1:-}" =~ ^([0-9]+)\.([0-9]+)(\.[0-9]+)?$ ]] || return 1
    actual_major="${BASH_REMATCH[1]}"
    actual_minor="${BASH_REMATCH[2]}"
    [[ "${2:-}" =~ ^([0-9]+)\.([0-9]+)$ ]] || return 1
    minimum_major="${BASH_REMATCH[1]}"
    minimum_minor="${BASH_REMATCH[2]}"

    (( 10#$actual_major > 10#$minimum_major || (10#$actual_major == 10#$minimum_major && 10#$actual_minor >= 10#$minimum_minor) ))
}

[[ "${ID:-}" == ubuntu ]] && version_at_least "${VERSION_ID:-}" "24.04" || fail unsupported_os
[[ "$(uname -m)" == x86_64 ]] || fail unsupported_arch
[[ -f "$SCRIPT_DIR/factory_management/hooks.py" && -f "$SCRIPT_DIR/pyproject.toml" ]] || fail invalid_bundle
[[ ! -e "$FRAPPE_BENCH_DIR" ]] || fail bench_exists
[[ -t 0 ]] || fail interactive_required

if version_at_least "$VERSION_ID" "26.04"; then
    WKHTMLTOX_URL="https://github.com/newinnovations/wkhtml-packaging/releases/download/2026-05-06/wkhtmltox_0.12.6.1-resolute_amd64.deb"
    WKHTMLTOX_SHA256="e759ea5856bdb36c909663ace6c51bac1aaa5b294b2c2c9803511b1f4a32978a"
elif version_at_least "$VERSION_ID" "24.10"; then
    WKHTMLTOX_URL="https://github.com/newinnovations/wkhtml-packaging/releases/download/2026-05-06/wkhtmltox_0.12.6.1-noble_amd64.deb"
    WKHTMLTOX_SHA256="9f68c989869640f35d83018e79a4d2197e1d8ec0dffc92ea371090c76260b08e"
else
    WKHTMLTOX_URL="https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-3/wkhtmltox_0.12.6.1-3.jammy_amd64.deb"
    WKHTMLTOX_SHA256="4f723b2691ad8638a9df960e0421d346d7315083e3583a334f33362280ddbba15"
fi

command -v apt-get >/dev/null || fail missing_apt
command -v curl >/dev/null || fail missing_curl
command -v python3 >/dev/null || fail missing_python
command -v sudo >/dev/null || fail missing_sudo
FRAPPE_GIT_COMMIT="$(python3 -c 'import json, pathlib, sys; print(json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))["frappe"]["git_commit"])' "$SCRIPT_DIR/release-manifest.json")"

if [[ -z "$FRAPPE_SITE_NAME" ]]; then
    DEFAULT_SITE_IP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}')"
    [[ -n "$DEFAULT_SITE_IP" ]] || DEFAULT_SITE_IP="192.168.1.100"
    read -r -p "$(msg site_ip_prompt) [$DEFAULT_SITE_IP]: " FRAPPE_SITE_NAME
    FRAPPE_SITE_NAME="${FRAPPE_SITE_NAME:-$DEFAULT_SITE_IP}"
fi
python3 - "$FRAPPE_SITE_NAME" <<'PY' || fail invalid_site_ip
import ipaddress
import sys

try:
    ipaddress.IPv4Address(sys.argv[1])
except ipaddress.AddressValueError:
    raise SystemExit(1)
PY

msg install_started
msg apt_dependencies
apt-get update
apt-get install -y --no-install-recommends \
    ca-certificates curl git build-essential pkg-config \
    libmariadb-dev libmariadb-dev-compat mariadb-client libltdl7 libkrb5-3 libgssapi-krb5-2 \
    redis-server supervisor nginx cron xvfb libfontconfig1 \
    python3 python3-venv python3-dev libffi-dev libssl-dev \
    iproute2 sudo gnupg

MARIADB_SETUP=""
WKHTMLTOX_PACKAGE=""
cleanup_temp_files() {
    if [[ -n "$MARIADB_SETUP" ]]; then
        rm -f -- "$MARIADB_SETUP"
    fi
    if [[ -n "$WKHTMLTOX_PACKAGE" ]]; then
        rm -f -- "$WKHTMLTOX_PACKAGE"
    fi
}
trap cleanup_temp_files EXIT

msg wkhtmltopdf
WKHTMLTOX_PACKAGE="$(mktemp --suffix=.deb)"
if ! curl -fsSL "$WKHTMLTOX_URL" -o "$WKHTMLTOX_PACKAGE"; then
    fail wkhtmltopdf_download
fi
printf '%s  %s\n' \
    "$WKHTMLTOX_SHA256" \
    "$WKHTMLTOX_PACKAGE" | sha256sum --check --status || fail wkhtmltopdf_checksum
DEBIAN_FRONTEND=noninteractive apt-get install -y "$WKHTMLTOX_PACKAGE"

msg mariadb_repo
MARIADB_SETUP="$(mktemp)"
curl -fsSL https://r.mariadb.com/downloads/mariadb_repo_setup -o "$MARIADB_SETUP"
bash "$MARIADB_SETUP" --mariadb-server-version="mariadb-11.8"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y mariadb-server
systemctl enable --now mariadb redis-server supervisor nginx cron

if ! id "$FRAPPE_USER" >/dev/null 2>&1; then
    useradd --create-home --shell /bin/bash "$FRAPPE_USER"
fi
install -d -o "$FRAPPE_USER" -g "$FRAPPE_USER" -m 0750 "$FRAPPE_BENCH_DIR"

read -r -s -p "$(msg db_password_prompt): " DB_ADMIN_PASSWORD
printf '\n'
read -r -s -p "$(msg db_password_confirm): " DB_ADMIN_PASSWORD_CONFIRM
printf '\n'
[[ -n "$DB_ADMIN_PASSWORD" && "$DB_ADMIN_PASSWORD" == "$DB_ADMIN_PASSWORD_CONFIRM" ]] || fail db_password_mismatch
[[ "${#DB_ADMIN_PASSWORD}" -ge 16 ]] || fail db_password_too_short
SQL_DB_ADMIN_PASSWORD="$(printf '%s' "$DB_ADMIN_PASSWORD" | python3 -c 'import sys; print(sys.stdin.read().replace("\\", "\\\\").replace("\x27", "\x27\x27"), end="")')"
unset DB_ADMIN_PASSWORD DB_ADMIN_PASSWORD_CONFIRM

msg db_user_setup
mariadb <<SQL
CREATE USER '${DB_ADMIN_USER}'@'localhost' IDENTIFIED BY '${SQL_DB_ADMIN_PASSWORD}';
GRANT ALL PRIVILEGES ON *.* TO '${DB_ADMIN_USER}'@'localhost' WITH GRANT OPTION;
FLUSH PRIVILEGES;
SQL
unset SQL_DB_ADMIN_PASSWORD

msg user_runtime_setup
sudo -H -u "$FRAPPE_USER" env \
    FRAPPE_USER="$FRAPPE_USER" \
    FRAPPE_BENCH_DIR="$FRAPPE_BENCH_DIR" \
    FRAPPE_SITE_NAME="$FRAPPE_SITE_NAME" \
    DB_ADMIN_USER="$DB_ADMIN_USER" \
    FRAPPE_GIT_COMMIT="$FRAPPE_GIT_COMMIT" \
    APP_SOURCE_DIR="$SCRIPT_DIR" \
    bash "$INSTALLER_DIR/setup-bench.sh"

msg production_setup
export PATH="/home/$FRAPPE_USER/.local/bin:$PATH"
cd "$FRAPPE_BENCH_DIR"
bench setup production "$FRAPPE_USER"
systemctl enable --now supervisor nginx
supervisorctl reread
supervisorctl update
systemctl reload nginx

msgf install_complete "$FRAPPE_SITE_NAME"
