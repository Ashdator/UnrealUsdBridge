"""Parse Python sources without importing Isaac/USD or generating caches."""
import ast,json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
files=list((root/'UnrealUsdBridge/Resources').rglob('*.py'))+list((root/'tests').glob('*.py'))+list((root/'scripts').glob('*.py'))
for path in files:ast.parse(path.read_text(encoding='utf-8-sig'),filename=str(path))
plugin=json.loads((root/'UnrealUsdBridge/UnrealUsdBridge.uplugin').read_text())
assert plugin['VersionName']=='0.6.6'
print(f'Parsed {len(files)} Python files; plugin version {plugin["VersionName"]}.')
