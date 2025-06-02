#!/bin/bash

# First, ensure we have a Python virtual environment
if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv .venv
    
    # Activate the virtual environment
    source .venv/bin/activate
    
    # Upgrade pip and install requirements
    echo "Installing Python dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt
else
    # Activate the virtual environment
    source .venv/bin/activate
fi

# Make sure UI directory exists
mkdir -p app/ui

# Install Playwright browsers
if ! command -v playwright &> /dev/null; then
    echo "Installing Playwright browsers..."
    pip install playwright
    playwright install
fi

# Start the UI server directly (not via the Python module)
echo "Starting OpenManus UI Server..."
python3 -c "from app.ui.server import OpenManusUI; server = OpenManusUI(); server.run()"

# Keep the terminal open to see logs
read -p "Press Enter to exit..."

# Deactivate virtual environment on exit
deactivate
