python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r ../python_gui/requirements.txt
pyinstaller --onefile --windowed --name TextWatermarkStudioDesktop ../python_gui/app.py
