#!/bin/bash

# --- Helper function to check if a command exists ---
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# --- Find Python ---
PYTHON_CMD="python3"
if ! command_exists $PYTHON_CMD; then
    PYTHON_CMD="python"
    if ! command_exists $PYTHON_CMD; then
        echo "Error: Python not found." >&2
        echo "Please install Python 3." >&2
        echo "Note: After installing Python, you might also need a package for virtual environment support," >&2
        echo "      such as 'python3-venv' on Debian/Ubuntu systems." >&2
        exit 1
    fi
fi
echo "Using Python command: $PYTHON_CMD"

# --- Check Python Version (Optional but recommended) ---
# You might want to add a check here for a minimum required Python version
# $PYTHON_CMD --version

# --- Check/Install Pip ---
echo "Checking for pip..."
if ! $PYTHON_CMD -m pip --version >/dev/null 2>&1; then
    echo "pip not found. Attempting to install it using ensurepip..."
    if $PYTHON_CMD -m ensurepip --default-pip; then
        echo "pip installed via ensurepip."
        # Re-check if pip command is now available after ensurepip
        if ! $PYTHON_CMD -m pip --version >/dev/null 2>&1; then
             echo "Error: pip command still not found after ensurepip."
             echo "Please install pip for your Python distribution."
             echo "e.g., 'sudo apt update && sudo apt install python3-pip' (Debian/Ubuntu)"
             echo "      'sudo yum install python3-pip' (Fedora/CentOS)"
             exit 1
        fi
    else
        echo "Error: Failed to install pip using ensurepip."
        echo "Please install pip for your Python distribution manually."
        echo "e.g., 'sudo apt update && sudo apt install python3-pip' (Debian/Ubuntu)"
        echo "      'sudo yum install python3-pip' (Fedora/CentOS)"
        exit 1
    fi
else
    echo "pip found. Upgrading..."
    $PYTHON_CMD -m pip install --upgrade pip --quiet
fi

# --- Check/Create Virtual Environment ---
VENV_DIR="venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment in '$VENV_DIR'..."
    if ! $PYTHON_CMD -m venv "$VENV_DIR"; then
        echo "Error: Failed to create virtual environment using '$PYTHON_CMD -m venv'." >&2
        echo "This might happen if the 'venv' module is not included in your Python installation." >&2
        echo "Try installing the appropriate package for your distribution:" >&2
        echo "  - Debian/Ubuntu: sudo apt update && sudo apt install python3-venv" >&2
        # Add other distribution examples if known, e.g., Fedora: sudo dnf install python3-venv
        echo "Or ensure your Python installation includes the 'venv' module." >&2
        exit 1
    fi
    echo "Virtual environment created."

    # --- Activate and Install Requirements (Only on creation) ---
    echo "Activating virtual environment..."
    # shellcheck source=/dev/null # SC1090: Can't follow non-constant source. Use a directive to specify location.
    # shellcheck source=venv/bin/activate # SC1091: Not following: venv/bin/activate was not specified as input (see shellcheck -x).
    source "$VENV_DIR/bin/activate"

    echo "Installing requirements..."
    REQUIREMENTS_FILE="requirements.txt"
    if [ -f "$REQUIREMENTS_FILE" ]; then
        echo "Found requirements.txt, installing packages..."
        pip install -r "$REQUIREMENTS_FILE"
        if [ $? -ne 0 ]; then
            echo "Error: Failed to install packages from requirements.txt." >&2
            # Consider deactivating or providing more specific error info
            exit 1
        fi
    else
        echo "'$REQUIREMENTS_FILE' not found. Installing common packages directly..."
        # Ensure tkinterdnd2-universal is included as per main.py dependencies
        pip install opencv-python numpy pillow tkinterdnd2-universal
        if [ $? -ne 0 ]; then
            echo "Error: Failed to install fallback packages." >&2
            exit 1
        fi
    fi

    echo "Setup complete!"
    echo ""
    # No need to deactivate here, we run the script next

else
    # --- Activate Existing Environment ---
    echo "Activating existing virtual environment..."
    # shellcheck source=/dev/null
    # shellcheck source=venv/bin/activate
    source "$VENV_DIR/bin/activate"
fi

# --- Check if tkinter is available ---
echo "Checking for tkinter module..."
if ! "$PYTHON_CMD" -c "import tkinter" > /dev/null 2>&1; then
    echo "Error: Python's tkinter module is missing." >&2
    echo "This is required for the application's user interface." >&2
    echo "" >&2
    echo "Please install the appropriate package for your Linux distribution." >&2
    echo "Examples:" >&2
    echo "  - Debian/Ubuntu: sudo apt update && sudo apt install python3-tk" >&2
    echo "  - Fedora:      sudo dnf install python3-tkinter" >&2
    echo "  - CentOS/RHEL: sudo yum install python3-tkinter" >&2
    echo "  - Arch Linux:  sudo pacman -S tk" >&2
    echo "" >&2
    echo "After installing, please re-run this script (./start.sh)." >&2
    # Optional: Pause before exiting
    read -n 1 -s -r -p "Press any key to exit..."
    echo ""
    # Deactivate if needed
    if command -v deactivate >/dev/null 2>&1; then
        deactivate
    fi
    exit 1
else
    echo "tkinter module found."
fi

# --- Run the main application ---
echo "Running main application (main.py)..."
"$PYTHON_CMD" main.py

# --- Check Exit Status ---
exit_status=$?
if [ $exit_status -ne 0 ]; then
    echo ""
    echo "The application exited with an error (code: $exit_status)."
    # Pause equivalent (read any key)
    read -n 1 -s -r -p "Press any key to close this terminal..."
    echo ""
fi

# --- Deactivate Environment (Optional, good practice) ---
# Check if deactivate function exists before calling it
if command -v deactivate >/dev/null 2>&1; then
    deactivate
fi

exit $exit_status 