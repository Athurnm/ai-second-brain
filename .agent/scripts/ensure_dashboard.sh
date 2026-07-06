#!/bin/bash

# Dashboard Server Service Script
# Ensures the local dashboard server is running on port 3737

PORT=3737
SERVER_SCRIPT="dashboard/server.py"
LOG_DIR="dashboard/logs"
STDOUT_LOG="$LOG_DIR/server_stdout.log"
STDERR_LOG="$LOG_DIR/server_stderr.log"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Check if port is already listening
if [ "$(uname -s)" = "Darwin" ]; then
    PORT_CHECK=$(lsof -i :$PORT -sTCP:LISTEN)
elif command -v ss >/dev/null 2>&1; then
    PORT_CHECK=$(ss -tuln | grep ":$PORT ")
elif command -v netstat >/dev/null 2>&1; then
    PORT_CHECK=$(netstat -tuln | grep ":$PORT ")
else
    PORT_CHECK=$(lsof -i :$PORT)
fi

if [ -n "$PORT_CHECK" ]; then
    echo "✅ Dashboard server already running on port $PORT"
    exit 0
fi

echo "🔄 Starting Dashboard server..."

# Check if server script exists
if [ ! -f "$SERVER_SCRIPT" ]; then
    echo "❌ Error: Server script $SERVER_SCRIPT not found in current directory."
    exit 1
fi

# Launch server in background
# Using nohup and redirecting logs
nohup python3 "$SERVER_SCRIPT" > "$STDOUT_LOG" 2> "$STDERR_LOG" &

# Wait up to 10 seconds for it to start
for i in {1..10}; do
    sleep 1
    if command -v ss >/dev/null 2>&1; then
        PORT_CHECK=$(ss -tuln | grep ":$PORT ")
    elif command -v netstat >/dev/null 2>&1; then
        PORT_CHECK=$(netstat -tuln | grep ":$PORT ")
    else
        PORT_CHECK=$(lsof -i :$PORT)
    fi
    
    if [ -n "$PORT_CHECK" ]; then
        echo "✅ Dashboard server started successfully at http://localhost:$PORT"
        exit 0
    fi
done

echo "❌ Error: Dashboard server failed to start within 10 seconds."
echo "Check logs at $STDERR_LOG"
exit 1
