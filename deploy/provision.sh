#!/usr/bin/env bash
#
# Case Intel -- one-time server provisioning for a brand new Ubuntu 24.04 box.
#
# Captures, as code, the manual SSH setup that was previously done by hand on
# the current production EC2 instance (installing Ollama, pulling
# nomic-embed-text, installing spaCy's en_core_web_sm, configuring Nginx,
# writing a gunicorn systemd unit, creating swap, installing certbot, etc.).
# See PROVISIONING.md for the full path (RDS, EC2, DNS, this script, certbot,
# GitHub secrets, first deploy) and for what this script deliberately does
# NOT do.
#
# Safe to re-run: every step checks current state before changing anything.
# .github/workflows/deploy.yml assumes this script has already been run once
# -- it only handles ongoing code updates, not first-time setup.
#
# Usage:
#   cp deploy/provision.env.example deploy/provision.env   # then edit it
#   sudo ./deploy/provision.sh
#
# Or override any setting inline instead of using a config file:
#   sudo DOMAIN=example.com GIT_REPO_URL=https://github.com/you/fork.git ./deploy/provision.sh

set -euo pipefail

# ============================================================================
# Configuration -- override via deploy/provision.env or environment variables
# ============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/provision.env" ]; then
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/provision.env"
fi

DEPLOY_USER="${DEPLOY_USER:-${SUDO_USER:-$(whoami)}}"
DEPLOY_HOME="$(getent passwd "$DEPLOY_USER" | cut -d: -f6)"
PROJECT_DIR="${PROJECT_DIR:-$DEPLOY_HOME/CASE_INTEL}"
GIT_REPO_URL="${GIT_REPO_URL:-https://github.com/Bugs0007/CASE_INTEL.git}"
GIT_BRANCH="${GIT_BRANCH:-main}"
DOMAIN="${DOMAIN:-caseintel.duckdns.org}"
SERVICE_NAME="${SERVICE_NAME:-case-intel}"
GUNICORN_BIND="${GUNICORN_BIND:-127.0.0.1:8000}"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-2}"
GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-120}"
OLLAMA_EMBEDDING_MODEL="${OLLAMA_EMBEDDING_MODEL:-nomic-embed-text}"
SWAP_FILE="${SWAP_FILE:-/swapfile}"
SWAP_SIZE_MB="${SWAP_SIZE_MB:-1024}"

if [ "$(id -u)" -ne 0 ]; then
    echo "This script needs root (it installs packages, writes systemd units," >&2
    echo "and edits /etc/sudoers.d). Re-run with sudo." >&2
    exit 1
fi

if [ -z "$DEPLOY_HOME" ]; then
    echo "Could not resolve a home directory for DEPLOY_USER='$DEPLOY_USER'." >&2
    echo "Set DEPLOY_USER to an existing user (e.g. 'ubuntu') and re-run." >&2
    exit 1
fi

log() { echo -e "\n==> $*"; }

# ============================================================================
# 1. System packages
# ============================================================================
# Matches what this project actually needed this session: a Python venv +
# build toolchain (psycopg2/pgvector/ddddocr/onnxruntime compile native
# extensions), Nginx as the reverse proxy, the Postgres client (the DB itself
# is RDS, not local -- see PROVISIONING.md), and certbot for the eventual TLS
# cert.
log "Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y \
    python3-venv \
    python3-pip \
    git \
    nginx \
    postgresql-client \
    build-essential \
    libpq-dev \
    certbot \
    python3-certbot-nginx \
    curl

# ============================================================================
# 2. Swap file (1GB, matching this session's setup)
# ============================================================================
log "Checking swap"
if swapon --show=NAME --noheadings | grep -qx "$SWAP_FILE"; then
    echo "Swap already active at $SWAP_FILE -- skipping."
elif [ -f "$SWAP_FILE" ]; then
    echo "$SWAP_FILE already exists but isn't active -- enabling it."
    chmod 600 "$SWAP_FILE"
    swapon "$SWAP_FILE"
else
    echo "Creating ${SWAP_SIZE_MB}MB swap file at $SWAP_FILE"
    fallocate -l "${SWAP_SIZE_MB}M" "$SWAP_FILE" || dd if=/dev/zero of="$SWAP_FILE" bs=1M count="$SWAP_SIZE_MB"
    chmod 600 "$SWAP_FILE"
    mkswap "$SWAP_FILE"
    swapon "$SWAP_FILE"
    if ! grep -q "^$SWAP_FILE " /etc/fstab; then
        echo "$SWAP_FILE none swap sw 0 0" >> /etc/fstab
    fi
fi

# ============================================================================
# 3. Clone the repo (if not already present)
# ============================================================================
log "Setting up project directory at $PROJECT_DIR"
if [ -d "$PROJECT_DIR/.git" ]; then
    echo "Repo already present at $PROJECT_DIR -- leaving it as-is (this script never touches app code on a re-run)."
else
    sudo -u "$DEPLOY_USER" git clone --branch "$GIT_BRANCH" "$GIT_REPO_URL" "$PROJECT_DIR"
fi

# ============================================================================
# 4. Python venv + dependencies
# ============================================================================
log "Creating virtualenv and installing Python dependencies"
if [ ! -d "$PROJECT_DIR/.venv" ]; then
    sudo -u "$DEPLOY_USER" python3 -m venv "$PROJECT_DIR/.venv"
fi
sudo -u "$DEPLOY_USER" "$PROJECT_DIR/.venv/bin/pip" install --upgrade pip
sudo -u "$DEPLOY_USER" "$PROJECT_DIR/.venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt"

# ============================================================================
# 5. Ollama + embedding model
# ============================================================================
# Required regardless of USE_GROQ: embeddings always go through Ollama's
# nomic-embed-text in this codebase (see CLAUDE.md gotcha) -- Groq only ever
# affects chat generation.
log "Installing Ollama"
if ! command -v ollama >/dev/null 2>&1; then
    curl -fsSL https://ollama.com/install.sh | sh
else
    echo "Ollama already installed -- skipping install."
fi

systemctl enable --now ollama

log "Pulling Ollama embedding model: $OLLAMA_EMBEDDING_MODEL"
if sudo -u "$DEPLOY_USER" ollama list 2>/dev/null | awk 'NR>1{print $1}' | grep -qE "^${OLLAMA_EMBEDDING_MODEL}(:latest)?$"; then
    echo "$OLLAMA_EMBEDDING_MODEL already pulled -- skipping."
else
    ollama pull "$OLLAMA_EMBEDDING_MODEL"
fi

# ============================================================================
# 6. spaCy language model
# ============================================================================
# core/services/document_processor.py silently falls back to a worse
# sentencizer if this is missing -- no hard crash, so easy to miss. Always
# re-run it; it's a no-op if already present.
log "Downloading spaCy en_core_web_sm model"
sudo -u "$DEPLOY_USER" "$PROJECT_DIR/.venv/bin/python" -m spacy download en_core_web_sm

# ============================================================================
# 7. gunicorn systemd unit
# ============================================================================
log "Writing gunicorn systemd unit ($SERVICE_NAME)"
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Case Intel gunicorn daemon
After=network.target

[Service]
User=$DEPLOY_USER
Group=$DEPLOY_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/.venv/bin/gunicorn \\
    --preload \\
    --workers $GUNICORN_WORKERS \\
    --timeout $GUNICORN_TIMEOUT \\
    --bind $GUNICORN_BIND \\
    case_intel_project.wsgi:application
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
echo "Unit written and enabled. Not starting it yet -- it needs $PROJECT_DIR/.env filled in first (see PROVISIONING.md)."

# ============================================================================
# 8. Nginx site config
# ============================================================================
log "Writing Nginx site config for $DOMAIN"
cat > "/etc/nginx/sites-available/${SERVICE_NAME}" <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    client_max_body_size 50M;

    location /static/ {
        alias $PROJECT_DIR/staticfiles/;
    }

    location /media/ {
        alias $PROJECT_DIR/media/;
    }

    location / {
        proxy_pass http://$GUNICORN_BIND;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

ln -sf "/etc/nginx/sites-available/${SERVICE_NAME}" "/etc/nginx/sites-enabled/${SERVICE_NAME}"
# Remove the default site so it can't shadow this one on a fresh box.
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx || systemctl restart nginx

# ============================================================================
# 9. Sudoers -- narrow, restart-only rule for the deploy user
# ============================================================================
# NARROW on purpose: this session found the rule actually in place on
# production is "NOPASSWD: ALL", far broader than deploy.yml needs (it only
# ever runs `sudo systemctl restart case-intel`). Write only that.
log "Configuring narrow sudoers rule for $DEPLOY_USER"
SYSTEMCTL_PATH="$(command -v systemctl)"
SUDOERS_FILE="/etc/sudoers.d/${SERVICE_NAME}-restart"
SUDOERS_LINE="$DEPLOY_USER ALL=(ALL) NOPASSWD: $SYSTEMCTL_PATH restart $SERVICE_NAME"
TMP_SUDOERS="$(mktemp)"
echo "$SUDOERS_LINE" > "$TMP_SUDOERS"
if visudo -c -f "$TMP_SUDOERS" >/dev/null 2>&1; then
    install -m 0440 "$TMP_SUDOERS" "$SUDOERS_FILE"
    echo "Wrote $SUDOERS_FILE: $SUDOERS_LINE"
else
    echo "Generated sudoers line failed visudo validation -- NOT installed. Fix manually:" >&2
    echo "  $SUDOERS_LINE" >&2
    rm -f "$TMP_SUDOERS"
    exit 1
fi
rm -f "$TMP_SUDOERS"

# ============================================================================
# 10. Firewall / AWS security group -- CANNOT be automated from inside the
# instance. Open these in the AWS console (EC2 -> Security Groups):
#
#   22/tcp   (SSH)        -- ideally restricted to your own IP, not 0.0.0.0/0
#   80/tcp   (HTTP)       -- needed for the certbot HTTP-01 challenge
#   443/tcp  (HTTPS)      -- the actual production traffic
#
# Ubuntu's own `ufw`, if enabled, needs the same three ports allowed; this
# script does not touch ufw state (leaves whatever the box already has).
# ============================================================================

log "Provisioning complete."
cat <<EOF

Next steps (see PROVISIONING.md for the full checklist):
  1. Create/populate $PROJECT_DIR/.env (DB credentials, SECRET_KEY, API keys, etc.)
  2. cd $PROJECT_DIR && source .venv/bin/activate
  3. python manage.py migrate
  4. python manage.py collectstatic --noinput
  5. sudo systemctl start ${SERVICE_NAME}
  6. Once DNS for $DOMAIN resolves to this box: sudo certbot --nginx -d $DOMAIN
EOF
