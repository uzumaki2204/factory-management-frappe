#!/usr/bin/env bash
set -Eeuo pipefail

FRAPPE_BENCH_DIR="${FRAPPE_BENCH_DIR:?missing FRAPPE_BENCH_DIR}"
FRAPPE_SITE_NAME="${FRAPPE_SITE_NAME:?missing FRAPPE_SITE_NAME}"
DB_ADMIN_USER="${DB_ADMIN_USER:?missing DB_ADMIN_USER}"
FRAPPE_GIT_COMMIT="${FRAPPE_GIT_COMMIT:?missing FRAPPE_GIT_COMMIT}"
APP_SOURCE_DIR="${APP_SOURCE_DIR:?missing APP_SOURCE_DIR}"

export PATH="$HOME/.local/bin:$PATH"

curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.14
uv tool install frappe-bench

curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
export NVM_DIR="$HOME/.nvm"
# shellcheck disable=SC1091
source "$NVM_DIR/nvm.sh"
nvm install 24
nvm use 24
npm install --global yarn

PYTHON_BIN="$(uv python find 3.14)"
bench init --frappe-branch version-16 --python "$PYTHON_BIN" "$FRAPPE_BENCH_DIR"
git -C "$FRAPPE_BENCH_DIR/apps/frappe" fetch --depth 1 origin "$FRAPPE_GIT_COMMIT"
git -C "$FRAPPE_BENCH_DIR/apps/frappe" checkout --detach "$FRAPPE_GIT_COMMIT"

TEMP_APP="$(mktemp -d)"
cleanup() {
    rm -rf -- "$TEMP_APP"
}
trap cleanup EXIT
cp -a "$APP_SOURCE_DIR/." "$TEMP_APP/"
rm -rf "$TEMP_APP/.git" "$TEMP_APP/build" "$TEMP_APP/dist" "$TEMP_APP/factory_management.egg-info"
find "$TEMP_APP" -type d -name __pycache__ -prune -exec rm -rf -- {} +
find "$TEMP_APP" -type f -name '*.pyc' -delete
git -C "$TEMP_APP" init --initial-branch main
git -C "$TEMP_APP" config user.name "Factory Management Installer"
git -C "$TEMP_APP" config user.email "installer@localhost"
git -C "$TEMP_APP" add .
git -C "$TEMP_APP" commit -m "Factory Management release"

cd "$FRAPPE_BENCH_DIR"
bench get-app --branch main factory_management "file://$TEMP_APP"
bench setup requirements
bench new-site "$FRAPPE_SITE_NAME" \
    --db-type mariadb \
    --db-root-username "$DB_ADMIN_USER"
bench --site "$FRAPPE_SITE_NAME" set-config server_script_enabled 1
bench --site "$FRAPPE_SITE_NAME" install-app factory_management
bench --site "$FRAPPE_SITE_NAME" migrate
bench build --app factory_management
bench use "$FRAPPE_SITE_NAME"
bench config dns_multitenant off
bench config serve_default_site on
