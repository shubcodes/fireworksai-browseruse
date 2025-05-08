#!/bin/bash

# First, ensure we have a Python virtual environment
if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv .venv
fi

# Activate the virtual environment
source .venv/bin/activate

# Make sure UI directory exists
mkdir -p app/ui

# Start the UI server directly (not via the Python module)
echo "Starting OpenManus UI Server..."
python3 -c "from app.ui.server import OpenManusUI; server = OpenManusUI(); server.run()"

# Keep the terminal open to see logs
read -p "Press Enter to exit..."

# Deactivate virtual environment on exit
deactivate
