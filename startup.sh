#!/bin/bash
# Startup script for Zalo API Service

echo "🚀 Starting Zalo API Service..."

# Create data directory if not exists
mkdir -p /app/data

# Check if session exists
if [ -f "/app/data/zalo_session.json" ]; then
    echo "✅ Session file found"
else
    echo "⚠️  No session file. Please login via /login/qr"
fi

# Start the server
echo "📡 Server starting on port 10000..."
exec python3 main.py
