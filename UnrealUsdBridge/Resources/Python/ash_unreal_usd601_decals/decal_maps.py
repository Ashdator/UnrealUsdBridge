"""Precompute fixed, UV-only decal arithmetic; leave receiver graphs editable."""
import hashlib
import json
import re
import struct
import zlib
from pathlib import Path

from .decal_regions import np
from .graph import evaluate, Constant, Sample, Unsupported, INPUTS


def image_backend():
    try:
        from PIL import Image
    except ModuleNotFoundError:
        import sys
        from pxr import Usd
        archive = next(Path(Usd.__file__).resolve().parents[3].glob('omni.kit.pip_archive*/pip_prebundle'))
        sys.path.insert(0, str(archive))
        from PIL import Image
    return Image

SUPPORTED = {'constant', 'uv', 'texture', 'mask', 'append', 'add', 'subtract',
             'multiply', 'divide', 'power', 'one_minus', 'clamp', 'lerp', 'if',
             'abs', 'frac', 'normalize', 'dot', 'desaturate', 'sin', 'cos'}


def image_path(root, ref):
    path = (root/ref['file']).resolve()
    if root.resolve() not in path.parents or not path.is_file():
        raise Unsupported('Decal texture is missing or outside the conversion folder')
    return path


def inspect(node, images):
    if isinstance(node, dict):
        op = node.get('op')
        if op and op not in SUPPORTED:
            raise Unsupported('Context-dependent or unsupported decal operation: '+op)
        if op == 'texture': images.add(node['texture'])
        for child in node.values(): inspect(child, images)
    elif isinstance(node, list):
        for child in node: inspect(child, images)


def linear(rgb):
    return np.where(rgb <= .04045, rgb/12.92, ((rgb+.055)/1.055)**2.4)


def srgb(rgb):
    return np.where(rgb <= .0031308, rgb*12.92, 1.055*np.maximum(rgb, 0)**(1/2.4)-.055)


class Evaluator:
    def __init__(self, root, textures):
        self.root, self.textures, self.images = root, textures, {}

    def load(self, key):
        Image = image_backend()
        if key not in self.images:
            with Image.open(image_path(self.root, self.textures[key])) as image:
                if image.mode not in ('RGB', 'RGBA', 'L', 'LA', 'P'):
                    raise Unsupported('Decal precomputation requires an ordinary 8-bit source image')
                self.images[key] = np.array(image.convert('RGBA'), dtype=np.uint8)
        return self.images[key]

    def stripe(self, node, width, height, start, stop):
        cache = {}
        u, v = np.meshgrid((np.arange(width, dtype=np.float32)+.5)/width,
                          1-(np.arange(start, stop, dtype=np.float32)+.5)/height)
        def run(n):
            key = json.dumps(n, sort_keys=True, separators=(',', ':'))
            if key in cache: return cache[key]
            op = n['op']
            def child(field): return run(n[field])
            if op == 'constant':
                a = np.asarray(n['value'], dtype=np.float32).reshape(1, 1, -1)
            elif op == 'uv':
                scale = n.get('scale', [1, 1])
                a = np.stack((u*scale[0], v*scale[1]), axis=-1)
            elif op == 'texture':
                pixels = self.load(n['texture']); h, w = pixels.shape[:2]
                uv = run(n.get('uv', {'op':'uv'})); xy = [uv[..., 0], 1-uv[..., 1]]
                indices = []; weights = []
                for coordinate, size, wrap in zip(xy, (w, h), (n.get('wrap_s', 'repeat'), n.get('wrap_t', 'repeat'))):
                    p = coordinate*size-.5; lo = np.floor(p).astype(np.int64)
                    weights.append((p-lo)[..., None].astype(np.float32))
                    pair = [lo, lo+1]
                    if wrap == 'repeat': pair = [i % size for i in pair]
                    elif wrap == 'clamp': pair = [np.clip(i, 0, size-1) for i in pair]
                    elif wrap == 'mirror':
                        pair = [np.where(i % (2*size) < size, i % (2*size), 2*size-1-i % (2*size)) for i in pair]
                    else: raise Unsupported('Unsupported decal addressing')
                    indices.append(pair)
                def texel(x, y):
                    value = pixels[indices[1][y], indices[0][x]].astype(np.float32)/255
                    if n.get('color_space', 'raw') == 'sRGB': value[..., :3] = linear(value[..., :3])
                    elif n.get('color_space', 'raw') != 'raw': raise Unsupported('Unsupported decal color space')
                    return value
                wx, wy = weights
                a = (texel(0, 0)*(1-wx)+texel(1, 0)*wx)*(1-wy)+(texel(0, 1)*(1-wx)+texel(1, 1)*wx)*wy
                if n.get('normal_map'):
                    a[..., :3] = a[..., :3]*2-1
                    if n.get('flip_green'): a[..., 1] *= -1
            elif op == 'mask': a = child('input')[..., n['channels']]
            elif op == 'append':
                left, right = np.broadcast_arrays(child('a')[..., :1], child('b')[..., :1])
                shape = left.shape[:2]
                a = np.concatenate([np.broadcast_to(child(f), shape+(child(f).shape[-1],)) for f in ('a', 'b')], axis=-1)
            elif op in ('add', 'subtract', 'multiply', 'divide', 'power', 'dot'):
                left, right = child('a'), child('b')
                if op == 'add': a = left+right
                elif op == 'subtract': a = left-right
                elif op == 'multiply': a = left*right
                elif op == 'divide': a = left/right
                elif op == 'power': a = np.maximum(left, 0)**right
                else: a = np.sum(left*right, axis=-1, keepdims=True)
            elif op == 'one_minus': a = 1-child('input')
            elif op == 'clamp': a = np.minimum(np.maximum(child('input'), child('min')), child('max'))
            elif op == 'lerp': a = child('a')+(child('b')-child('a'))*child('alpha')
            elif op == 'if':
                left, right = child('a')[..., :1], child('b')[..., :1]
                a = np.where(np.abs(left-right) <= n.get('threshold', 1e-5), child('equal'),
                             np.where(left > right, child('greater'), child('less')))
            elif op == 'normalize':
                a = child('input'); length = np.linalg.norm(a, axis=-1, keepdims=True)
                a = np.divide(a, length, out=np.zeros_like(a), where=length > 1e-20)
            elif op == 'abs': a = np.abs(child('input'))
            elif op == 'frac': a = child('input')-np.floor(child('input'))
            elif op == 'desaturate':
                value = child('input'); gray = np.sum(value[..., :3]*np.asarray(n['weights']), axis=-1, keepdims=True)
                a = value+(gray-value)*child('fraction')
            elif op in ('sin', 'cos'): a = getattr(np, op)(child('input')*n.get('frequency', 1))
            else: raise Unsupported('Unsupported decal operation: '+op)
            cache[key] = a
            return a
        with np.errstate(divide='ignore', invalid='ignore', over='ignore'):
            return np.broadcast_to(run(node), (stop-start, width, run(node).shape[-1]))


def write_png(path, width, height, channels, stripes):
    # Streaming 16-bit PNG keeps precision without a full float output buffer.
    def chunk(file, kind, payload):
        file.write(struct.pack('>I', len(payload))+kind+payload+struct.pack('>I', zlib.crc32(kind+payload)&0xffffffff))
    partial = path.with_suffix('.partial')
    try:
        with partial.open('wb') as file:
            file.write(b'\x89PNG\r\n\x1a\n')
            chunk(file, b'IHDR', struct.pack('>IIBBBBB', width, height, 16, {1:0, 3:2, 4:6}[channels], 0, 0, 0))
            compressor = zlib.compressobj(3)
            for values in stripes:
                if not np.isfinite(values).all() or values.min() < -1e-5 or values.max() > 1+1e-5:
                    raise Unsupported('Decal output is outside PNG range; retaining its original graph')
                rows = np.rint(np.clip(values, 0, 1)*65535).astype('>u2')
                for row in rows:
                    payload = compressor.compress(b'\0'+row.tobytes())
                    if payload: chunk(file, b'IDAT', payload)
            chunk(file, b'IDAT', compressor.flush()); chunk(file, b'IEND', b'')
        partial.replace(path)
    finally:
        # Non-recursive cleanup of this function's own incomplete output only.
        if partial.exists(): partial.unlink()


def prepare(data, root, progress=lambda _:None):
    root = Path(root); results = []
    keys = sorted({d['material'] for d in data.get('decals', []) if d.get('visible', True)})
    for index, key in enumerate(keys):
        material = data['materials'].get(key)
        if not material or material.get('issues'): continue
        evaluator = Evaluator(root, data['textures'])
        channels = set(material.get('decal_channels', material.get('inputs', {}))) | {'opacity'}
        for field in sorted(channels & set(INPUTS)):
            # Preserve HDR emission graph values; this PNG16 path is normalized
            # color/data storage and must not clip emission above one.
            if field=='emissive': continue
            node = material.get('inputs', {}).get(field)
            if node is None: continue
            # Preserve simple original texture/normal maps and constant values.
            try:
                if isinstance(evaluate(node), (Constant, Sample)): continue
            except Unsupported: pass
            entry = {'material':key, 'name':material.get('name', key), 'channel':field}
            try:
                opacity = material.get('inputs', {}).get('opacity', {'op':'constant', 'value':[1]}) if field == 'base_color' else None
                images = set(); inspect(node, images)
                if opacity is not None: inspect(opacity, images)
                if not images: raise Unsupported('No UV image inputs to precompute')
                digest = hashlib.sha256(json.dumps((node, opacity), sort_keys=True).encode()+b'decal-maps-2')
                for texture in sorted(images):
                    with image_path(root, data['textures'][texture]).open('rb') as file:
                        for block in iter(lambda:file.read(1024*1024), b''): digest.update(block)
                    evaluator.load(texture)
                width = max(evaluator.images[t].shape[1] for t in images)
                height = max(evaluator.images[t].shape[0] for t in images)
                # UE opacity expressions may exceed [0,1] before the final
                # amount/mask multiplication. Clipping here changes intensity.
                # Store a normalized alpha and reconstruct its original range.
                opacity_scale, opacity_bias = 1.0, 0.0
                if opacity is not None:
                    low, high = float('inf'), float('-inf')
                    for start in range(0, height, 32):
                        alpha = evaluator.stripe(opacity, width, height, start, min(start+32, height))[..., :1]
                        if not np.isfinite(alpha).all():
                            raise Unsupported('Non-finite decal opacity; retaining its original graph')
                        low, high = min(low, float(alpha.min())), max(high, float(alpha.max()))
                    opacity_bias = min(0.0, low)
                    opacity_scale = max(1.0, high-opacity_bias)
                    if opacity_scale > 64:
                        raise Unsupported('Opacity range is too broad for a precise 16-bit map; retaining its original graph')
                    if opacity_scale != 1 or opacity_bias != 0:
                        digest.update(b'alpha-range-3')
                label = re.sub('[^A-Za-z0-9_]', '_', material.get('name', 'Decal'))[:45]
                leaf = 'DecalMap_'+label+'_'+field+'_'+digest.hexdigest()[:16]
                path = root/'textures'/(leaf+'.png'); path.parent.mkdir(exist_ok=True)
                progress(f'Preparing decal map {index+1}/{len(keys)}: {material.get("name", key)} {field}')
                count = 4 if opacity is not None else 3 if field == 'normal' else 1
                def stripes():
                    for start in range(0, height, 32):
                        stop = min(start+32, height)
                        components = 3 if field in ('base_color', 'normal') else 1
                        value = evaluator.stripe(node, width, height, start, stop)[..., :components]
                        if value.shape[-1] == 1 and components == 3: value = np.repeat(value, 3, axis=-1)
                        if field == 'normal':
                            length = np.linalg.norm(value, axis=-1, keepdims=True)
                            if np.any(length < 1e-20): raise Unsupported('Zero decal normal; retaining original graph')
                            value = (value/length+1)*.5
                        elif field == 'base_color':
                            alpha = evaluator.stripe(opacity, width, height, start, stop)[..., :1]
                            value = np.concatenate((srgb(value), (alpha-opacity_bias)/opacity_scale), axis=-1)
                        yield value
                # Always regenerate: source graph changes and interrupted runs
                # cannot accidentally reuse a partially written map.
                write_png(path, width, height, count, stripes())
                texture = 'decal_map_'+digest.hexdigest()[:20]+'_'+field
                data['textures'][texture] = {'file':path.relative_to(root).as_posix(), 'source':'/Bridge/DecalMaps/'+leaf}
                sample = {'op':'texture', 'texture':texture, 'color_space':'sRGB' if field == 'base_color' else 'raw',
                          'normal_map':field == 'normal', 'flip_green':False, 'wrap_s':'repeat', 'wrap_t':'repeat'}
                material['inputs'][field] = {'op':'mask', 'input':sample, 'channels':list(range(3 if field in ('base_color', 'normal') else 1))}
                if opacity is not None:
                    alpha = {'op':'mask', 'input':dict(sample), 'channels':[3]}
                    if opacity_scale != 1:
                        alpha = {'op':'multiply', 'a':alpha, 'b':{'op':'constant', 'value':[opacity_scale]}}
                    if opacity_bias != 0:
                        alpha = {'op':'add', 'a':alpha, 'b':{'op':'constant', 'value':[opacity_bias]}}
                    material['inputs']['opacity'] = alpha
                    entry['packed_channels'] = ['base_color', 'opacity']
                    if opacity_scale != 1 or opacity_bias != 0:
                        entry['opacity_decode'] = {'scale':opacity_scale, 'bias':opacity_bias}
                entry.update(status='precomputed', file=path.relative_to(root).as_posix(), width=width, height=height, bit_depth=16)
            except (Unsupported, KeyError, ValueError, OSError) as exc:
                entry.update(status='original_graph', reason=str(exc))
            results.append(entry)
        evaluator.images.clear()
    return results
