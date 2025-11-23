# Python Virtual Environment Setup

## Overview

This project uses a Python virtual environment to manage dependencies separately from system Python packages.

## Virtual Environment Location

- **Path:** `/home/herocod/Documents/UniPi/IOT/IotProject/venv/`
- **Python Version:** 3.12.3

## Installed Packages

Key packages for this ML/IoT project:

- **TensorFlow 2.20.0** - Deep learning framework for LSTM models
- **scikit-learn 1.7.2** - Machine learning algorithms
- **pandas 2.3.3** - Data manipulation and analysis
- **numpy 2.3.5** - Numerical computing
- **matplotlib 3.10.7** - Data visualization
- **seaborn 0.13.2** - Statistical data visualization
- **pythermalcomfort 3.8.0** - Thermal comfort analysis
- **scipy 1.16.3** - Scientific computing
- **jupyter 1.1.1** - Interactive notebooks
- **ipykernel 7.1.0** - Jupyter kernel support

## Usage

### Automatic Activation in VS Code

VS Code is configured to automatically use this virtual environment for:

- Python file execution
- Jupyter notebooks
- Terminal sessions
- Debugging

### Manual Activation (Terminal)

If you need to manually activate the environment:

```bash
# From project root
source venv/bin/activate

# Verify activation (should show venv path)
which python

# Deactivate when done
deactivate
```

### Running Python Files

VS Code will automatically use the virtual environment. You can also run manually:

```bash
# Activate first
source venv/bin/activate

# Run Python scripts
python ml/airQualityGermany/2023_indoor_air_quality_dataset_germany.py

# Or use the full path
./venv/bin/python ml/airQualityGermany/2023_indoor_air_quality_dataset_germany.py
```

### Running Jupyter Notebooks

1. Open any `.ipynb` file in VS Code
2. Click "Select Kernel" in the top-right
3. Choose "Python Environments..."
4. Select the virtual environment at `./venv/bin/python`

The notebook will now use all installed packages from the virtual environment.

## Package Management

### Installing New Packages

```bash
source venv/bin/activate
pip install <package-name>

# Or add to requirements.txt and run:
pip install -r ml/airQualityGermany/requirements.txt
```

### Updating Packages

```bash
source venv/bin/activate
pip install --upgrade <package-name>
```

### Listing Installed Packages

```bash
source venv/bin/activate
pip list
```

### Exporting Requirements

If you add new packages, update the requirements file:

```bash
source venv/bin/activate
pip freeze > ml/airQualityGermany/requirements.txt
```

## Troubleshooting

### VS Code Not Using Virtual Environment

1. Press `Ctrl+Shift+P`
2. Type "Python: Select Interpreter"
3. Choose `./venv/bin/python`

### Import Errors

Make sure the virtual environment is activated:

```bash
source venv/bin/activate
which python  # Should show path to venv/bin/python
```

### Jupyter Kernel Not Found

Install ipykernel in the virtual environment:

```bash
source venv/bin/activate
pip install ipykernel
python -m ipykernel install --user --name=iot-venv
```

### TensorFlow Issues

If TensorFlow fails to load:

```bash
source venv/bin/activate
pip uninstall tensorflow
pip install tensorflow==2.20.0
```

## File Structure

```txt
IotProject/
├── venv/                          # Virtual environment (git-ignored)
│   ├── bin/
│   │   └── python                 # Python interpreter
│   └── lib/
│       └── python3.12/
│           └── site-packages/     # Installed packages
├── ml/
│   └── airQualityGermany/
│       └── requirements.txt       # Package dependencies
└── .vscode/
    └── settings.json              # VS Code configuration
```

## Notes

- The `venv/` directory is excluded from git (see `.gitignore`)
- VS Code settings are configured in `.vscode/settings.json`
- All Python scripts and Jupyter notebooks will automatically use this environment
- Environment activation happens automatically in VS Code terminals
