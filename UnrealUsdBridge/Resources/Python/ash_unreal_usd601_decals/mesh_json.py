"""Read legacy Unreal mesh JSON, repairing only non-finite UV coordinates."""
import json
import math
import re
from pathlib import Path

# Match complete strings first so asset names containing 'nan' stay untouched.
_tokens = re.compile(r'"(?:[^"\\]|\\.)*"|(?<![\w.])[+-]?(?:nan|inf(?:inity)?)(?![\w.])', re.I)

def load_mesh(path):
    text = Path(path).read_text(encoding='utf-8-sig')
    try:
        mesh = json.loads(text)
    except json.JSONDecodeError:
        text = _tokens.sub(lambda m: m[0] if m[0].startswith('"') else 'NaN', text)
        mesh = json.loads(text)  # Other malformed/truncated JSON remains an error.
    count = 0
    for channel in mesh.get('uvs', []):
        for uv in channel:
            for axis, value in enumerate(uv):
                if not math.isfinite(value):
                    uv[axis] = 0.0
                    count += 1
    def check(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f'{path}: non-finite mesh data outside UVs; re-extract or repair the source mesh')
        if isinstance(value, dict):
            for item in value.values(): check(item)
        elif isinstance(value, list):
            for item in value: check(item)
    check(mesh)
    if count:
        mesh['repaired_uv_coordinates'] = count
        print(f'Mesh UV repair: {path}: replaced {count} non-finite coordinates with zero; inspect source UV channels', flush=True)
    return mesh
