#!/bin/bash

# Script to set up virtual environment and continuously run the Python program
# located at ./src/main.py, restarting it upon exit.
#
# This script:
# 1. Detects available Python command (python or python3)
# 2. Creates a virtual environment (.venv) if it doesn't exist
# 3. Activates the virtual environment
# 4. Installs dependencies from requirements.txt if needed
# 5. Enters an infinite loop where it starts the specified Python program
#
# If the program exits, the script waits for 2 seconds and then restarts it.
# The loop can be interrupted by pressing Ctrl+C.
#
# Requirements:
# - Python 3.x installed and accessible via "python" or "python3" command
# - Intended for streaming or testing scenarios where automatic restarts are useful
# - Automatically manages virtual environment and dependencies

set -e  # Exit on any error

# Function to detect a supported Python command (prefers 3.10–3.12 for pygame wheels)
detect_python() {
    local candidates=("python3.12" "python3.11" "python3.10" "python3" "python")
    local fallback_cmd=""

    for cmd in "${candidates[@]}"; do
        if ! command -v "$cmd" &> /dev/null; then
            continue
        fi

        local version=$($cmd - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)

        local major=${version%%.*}
        local minor=${version#*.}

        # Prefer 3.10–3.12 because pygame publishes wheels there
        if [ "$major" -eq 3 ] && [ "$minor" -ge 10 ] && [ "$minor" -le 12 ]; then
            echo "$cmd"
            return 0
        fi

        # Track a 3.9 fallback to at least run the game (chat will be disabled later)
        if [ "$major" -eq 3 ] && [ "$minor" -eq 9 ] && [ -z "$fallback_cmd" ]; then
            fallback_cmd="$cmd"
        fi
    done

    # If we didn't find 3.10–3.12, fall back to 3.9 to let the game run without chat
    if [ -n "$fallback_cmd" ]; then
        echo "$fallback_cmd"
        return 0
    fi

    # Nothing suitable found
    echo ""
}

# Function to check if dependencies are installed
check_dependencies_installed() {
    if [ ! -f "./requirements.txt" ]; then
        echo "requirements.txt not found, skipping dependency check"
        return 0
    fi

    local venv_python=".venv/bin/python"

    # Read requirements.txt and check each package
    while IFS= read -r requirement; do
        # Skip comments and empty lines
        if [[ "$requirement" =~ ^[[:space:]]*# ]] || [[ -z "${requirement// }" ]]; then
            continue
        fi

        # Extract package name (before ==)
        package_name=$(echo "$requirement" | cut -d'=' -f1 | xargs)

        # Check if package is installed
        if ! "$venv_python" -m pip show "$package_name" &> /dev/null; then
            return 1
        fi
    done < "./requirements.txt"

    return 0
}

# Function to handle cleanup on script exit
cleanup() {
    echo -e "\nStopped by user."
    exit 0
}

# Set up signal handler
trap cleanup SIGINT SIGTERM

# Detect Python command
PYTHON_CMD=$(detect_python)

if [ -z "$PYTHON_CMD" ]; then
    echo "Error: No supported Python interpreter found. Install Python 3.10–3.12 (preferred) or 3.9 to run without chat control."
    exit 1
fi

PY_VERSION_RAW=$($PYTHON_CMD - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)

echo "Using Python command: $PYTHON_CMD (Python $PY_VERSION_RAW)"

# pygame wheels are only published up to Python 3.12 today; 3.13+ will try to
# compile SDL from source and fail without extra system libraries. Block early
# with a clear message so users can install a supported interpreter.
PY_MAJOR=${PY_VERSION_RAW%%.*}
PY_MINOR=${PY_VERSION_RAW#*.}
if [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -ge 13 ]; then
    echo "Error: Python $PY_VERSION_RAW detected. Please install Python 3.10–3.12 (recommended) so pygame wheels are available."
    echo "TikTok chat control also requires Python 3.10+; 3.9 will run the game but disables chat."
    exit 1
fi

if [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -le 9 ]; then
    echo "Warning: Python $PY_VERSION_RAW detected. The game will run, but TikTok chat control stays disabled on 3.9." >&2
fi

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    "$PYTHON_CMD" -m venv .venv
    if [ $? -ne 0 ]; then
        echo "Error: Failed to create virtual environment"
        exit 1
    fi
    echo "Virtual environment created successfully."
fi

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Check if dependencies need to be installed
if ! check_dependencies_installed; then
    echo "Installing dependencies..."
    .venv/bin/python -m pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "Error: Failed to install dependencies"
        exit 1
    fi
    echo "Dependencies installed successfully."
else
    echo "Dependencies already installed."
fi

# Run the application in a loop
while true; do
    echo "Starting program..."
    .venv/bin/python ./src/main.py
    exit_code=$?

    if [ $exit_code -eq 0 ]; then
        echo "Program was closed by user. Exiting..."
        break
    else
        echo "Program exited with error code $exit_code. Restarting in 2 seconds... Press Ctrl+C to stop."
        sleep 2
    fi
done
