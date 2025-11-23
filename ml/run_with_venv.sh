#!/bin/bash
# Helper script to run ML scripts with the project's Python 3.10 venv

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/../.."
VENV_PYTHON="$PROJECT_ROOT/venv/bin/python"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ Virtual environment not found at $PROJECT_ROOT/venv"
    echo "   Please run: cd $PROJECT_ROOT && ./run.sh init"
    exit 1
fi

if [ -z "$1" ]; then
    echo "Usage: ./run_with_venv.sh <script.py>"
    echo ""
    echo "Available scripts:"
    echo "  - 2023_indoor_air_quality_dataset_germany.py"
    echo "  - export_temperature_model_to_c.py"
    echo ""
    echo "Or activate the venv and use directly:"
    echo "  source $PROJECT_ROOT/venv/bin/activate"
    exit 1
fi

echo "Running with Python 3.10 venv..."
cd "$SCRIPT_DIR"
"$VENV_PYTHON" "$@"
