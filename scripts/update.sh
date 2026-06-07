#!/bin/bash
#
# Incremental update script for World Cup Guess
# Run as root on the server: sudo bash scripts/update.sh
#
# Unlike deploy.sh, this does NOT regenerate secrets or reinitialize the database.
# Player data in instance/guess.db is preserved.
#

set -e

PROJECT_DIR="/opt/world-cup-guess"
VENV_DIR="$PROJECT_DIR/venv"

echo "=== World Cup Guess - Update ==="
echo ""

# 1. Pull latest code
echo "[1/4] Pulling latest code..."
cd $PROJECT_DIR
git pull origin main

# 2. Install/update dependencies
echo "[2/4] Installing dependencies..."
source $VENV_DIR/bin/activate
pip install -r requirements.txt -q

# 3. Run database migrations (safe to re-run, uses try/except)
echo "[3/4] Running database migrations..."
python scripts/init_db.py

# 4. Restart service
echo "[4/4] Restarting service..."
systemctl restart world-cup-guess

echo ""
echo "=== Update Complete! ==="
systemctl status world-cup-guess --no-pager
