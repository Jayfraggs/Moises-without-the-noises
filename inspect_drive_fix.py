import json
from pathlib import Path
p = Path(r'C:\Users\Olabode Nathaniel\Code\Moises without the noises\colab\mwtn_notebook.ipynb')
nb = json.loads(p.read_text(encoding='utf-8'))
cell = nb['cells'][7]
src = ''.join(cell.get('source', []))
for token in ['DRIVE_OUTPUT_FOLDER', 'DRIVE_OUTPUT_DIR', 'WHISPER_MODEL', 'SEPARATION_ENGINE']:
    print(token, token in src)
