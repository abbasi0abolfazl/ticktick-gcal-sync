#!/usr/bin/env bash
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/.config/ticktick-gcal-sync"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
BIN_DIR="$HOME/.local/bin"

echo "=== Installing TickTick <-> Google Calendar Sync ==="

mkdir -p "$CONFIG_DIR" "$SYSTEMD_USER_DIR" "$BIN_DIR"

# 1. Setup virtual environment
if [ ! -d "$REPO_DIR/.venv" ]; then
    echo "Creating Python virtual environment..."
    if command -v uv &> /dev/null; then
        uv venv "$REPO_DIR/.venv"
        uv pip install --python "$REPO_DIR/.venv/bin/python" -r "$REPO_DIR/requirements.txt"
    else
        python3 -m venv "$REPO_DIR/.venv"
        "$REPO_DIR/.venv/bin/pip" install --upgrade pip
        "$REPO_DIR/.venv/bin/pip" install -r "$REPO_DIR/requirements.txt"
    fi
else
    echo "Virtual environment already exists."
fi

# 2. Setup CLI command in ~/.local/bin
cat <<EOF > "$BIN_DIR/sync-task"
#!/usr/bin/env bash
exec "$REPO_DIR/.venv/bin/python" "$REPO_DIR/sync_manager.py" "\$@"
EOF
chmod +x "$BIN_DIR/sync-task"
chmod +x "$REPO_DIR/sync_manager.py"

echo "✓ CLI installed at: $BIN_DIR/sync-task"

# 3. Setup systemd units
cp "$REPO_DIR/systemd/ticktick-gcal-sync.service" "$SYSTEMD_USER_DIR/"
cp "$REPO_DIR/systemd/ticktick-gcal-sync.timer" "$SYSTEMD_USER_DIR/"

systemctl --user daemon-reload
systemctl --user enable --now ticktick-gcal-sync.timer

echo "✓ Systemd user timer enabled and started (runs every 10 min)."
echo ""
echo "=== Setup Complete! ==="
echo "Next steps:"
echo "1. Place your Google Cloud OAuth 'credentials.json' at:"
echo "   $CONFIG_DIR/credentials.json"
echo "2. Run Google authorization:"
echo "   sync-task auth-google"
echo "3. Test synchronization:"
echo "   sync-task sync"
