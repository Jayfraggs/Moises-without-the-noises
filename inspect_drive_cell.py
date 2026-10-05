import json
from pathlib import Path
p = Path(r'C:\Users\Olabode Nathaniel\Code\Moises without the noises\colab\mwtn_notebook.ipynb')
nb = json.loads(p.read_text(encoding='utf-8'))
for i, cell in enumerate(nb.get('cells', []), 1):
    src = ''.join(cell.get('source', []))
    if 'DRIVE_OUTPUT_DIR' in src or 'Save to Google Drive' in src or 'DRIVE_OUTPUT_FOLDER' in src:
        print('--- CELL', i, '---')
        print(src[:5000])
        print('--- END CELL ---\n')
