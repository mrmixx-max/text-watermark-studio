python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip
pip install -r ..\python_guiequirements.txt
pyinstaller --noconsole --windowed --onefile --name TextWatermarkStudioDesktop ..\python_guipp.py
