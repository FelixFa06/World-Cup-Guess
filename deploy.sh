#!/bin/bash
#
# One-click deploy script for World Cup Guess on Ubuntu 22.04
# Run as root: sudo bash deploy.sh
#

set -e

PROJECT_DIR="/opt/world-cup-guess"
APP_NAME="world-cup-guess"
VENV_DIR="$PROJECT_DIR/venv"

echo "=== World Cup Guess - Deployment Script ==="
echo ""

# 1. System updates & dependencies
echo "[1/6] Installing system dependencies..."
apt update -y
apt install -y python3 python3-pip python3-venv nginx

# 2. Create project directory
echo "[2/6] Setting up project directory..."
mkdir -p $PROJECT_DIR

# 3. Copy project files (assuming script runs from project root)
echo "[3/6] Copying project files..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ "$SCRIPT_DIR" != "$PROJECT_DIR" ]; then
    cp -r "$SCRIPT_DIR"/* $PROJECT_DIR/
fi

# 4. Setup Python virtual environment
echo "[4/6] Setting up Python environment..."
python3 -m venv $VENV_DIR
source $VENV_DIR/bin/activate
pip install --upgrade pip
pip install -r $PROJECT_DIR/requirements.txt
pip install gunicorn

# 5. Initialize database
echo "[5/6] Initializing database..."
cd $PROJECT_DIR
source $VENV_DIR/bin/activate
python3 init_db.py

# 6. Setup systemd service
echo "[6/6] Setting up systemd service..."
cat > /etc/systemd/system/$APP_NAME.service << EOF
[Unit]
Description=World Cup Guess Flask App
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=$PROJECT_DIR
Environment="SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
Environment="ADMIN_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_hex(8))')"
ExecStart=$VENV_DIR/bin/gunicorn --workers 2 --bind 127.0.0.1:8000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Setup Nginx
cat > /etc/nginx/sites-available/$APP_NAME << EOF
server {
    listen 80;
    server_name _;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /static {
        alias $PROJECT_DIR/static;
        expires 7d;
    }
}
EOF

# Enable site
ln -sf /etc/nginx/sites-available/$APP_NAME /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Set permissions
chown -R www-data:www-data $PROJECT_DIR

# Start services
systemctl daemon-reload
systemctl enable $APP_NAME
systemctl restart $APP_NAME
systemctl restart nginx

# Firewall
ufw allow 22/tcp
ufw allow 80/tcp
ufw --force enable

echo ""
echo "=== Deployment Complete! ==="
echo ""
echo "Access your app at: http://$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')"
echo ""
echo "Admin nickname: $(grep ADMIN_NICKNAME $PROJECT_DIR/config.py | head -1 | cut -d'"' -f2)"
echo "Admin password: check config.py or environment variable ADMIN_PASSWORD"
echo ""
echo "Useful commands:"
echo "  systemctl status $APP_NAME   # Check app status"
echo "  journalctl -u $APP_NAME -f    # View app logs"
echo "  systemctl restart $APP_NAME   # Restart app"
