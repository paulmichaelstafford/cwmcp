#!/usr/bin/env bash
# Setup script for cwmcp — prompts for credentials and content path,
# then writes ~/.cwmcp/config.properties

set -e

CONFIG_DIR="$HOME/.cwmcp"
CONFIG_FILE="$CONFIG_DIR/config.properties"

echo "cwmcp setup"
echo "==========="
echo ""

if [ -f "$CONFIG_FILE" ]; then
    read -p "Config already exists at $CONFIG_FILE. Overwrite? [y/N] " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
fi

read -p "cwbe user (email): " cwbe_user
read -s -p "cwbe password: " cwbe_password
echo ""
read -p "content path (directory with onetime/ and continuous/): " content_path

# Expand ~ if used
content_path="${content_path/#\~/$HOME}"

if [ ! -d "$content_path" ]; then
    echo "Warning: '$content_path' does not exist yet."
    read -p "Continue anyway? [y/N] " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 1
    fi
fi

# Optional: Grafana — only used by query_logs for cwbe debugging.
echo ""
echo "Grafana (optional, for query_logs / cwbe debugging — leave blank to skip):"
read -p "  grafana user: " grafana_user
grafana_password=""
if [ -n "$grafana_user" ]; then
    read -s -p "  grafana password: " grafana_password
    echo ""
fi

mkdir -p "$CONFIG_DIR"
cat > "$CONFIG_FILE" <<EOF
# cwmcp configuration
cwbe_user=$cwbe_user
cwbe_password=$cwbe_password
content_path=$content_path
grafana_url=https://grafana.collapsingwave.com
grafana_user=$grafana_user
grafana_password=$grafana_password
EOF

chmod 600 "$CONFIG_FILE"
echo ""
echo "Config written to $CONFIG_FILE"
