import json
from pathlib import Path
p = Path(r'C:\Users\Olabode Nathaniel\Code\Moises without the noises\colab\mwtn_notebook.ipynb')
nb = json.loads(p.read_text(encoding='utf-8'))
cell = nb['cells'][7]
src = ''.join(cell.get('source', []))
for token in ['WHISPER_MODEL', 'WHISPER_LANGUAGE', 'SEPARATION_MODEL', 'SEPARATION_ENGINE']:
    print(token, token in src)
print(src[src.find('if \'MODEL\''):src.find('# -- Google Drive output folder')])
