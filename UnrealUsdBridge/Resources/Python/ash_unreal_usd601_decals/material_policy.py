"""Choose a single surface backend and restore source main normal maps."""
import copy
import json
from .graph import Constant, Sample, Unsupported, evaluate


def _constant(node, value):
    try:
        result = evaluate(node)
        return isinstance(result, Constant) and result.value == tuple(value)
    except (Unsupported, ValueError):
        return False


def _same(a, b):
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def _rnm_base(node):
    """Recognize Unreal BlendAngleCorrectedNormals, not arbitrary math trees.

    normalize(t*dot(t,u) - t.z*u), t=(base.xy, base.z+1),
    u=(-detail.xy, detail.z). Return its base normal only after structural checks.
    """
    try:
        if node['op'] != 'normalize': return None
        sub = node['input']
        if sub['op'] != 'subtract': return None
        left, right = sub['a'], sub['b']
        if left['op'] != 'multiply' or right['op'] != 'multiply': return None
        t, dot = left['a'], left['b']
        if t['op'] != 'append' or dot['op'] != 'dot': return None
        xy, z = t['a'], t['b']
        if xy['op'] != 'mask' or xy['channels'] != [0,1]: return None
        base = xy['input']
        if z['op'] != 'add' or not _constant(z['b'], [1]): return None
        if z['a']['op'] != 'mask' or z['a']['channels'] != [2] or not _same(z['a']['input'], base): return None
        if not _same(dot['a'], t) or not _same(right['a'], z) or not _same(dot['b'], right['b']): return None
        u = dot['b']
        if u['op'] != 'append' or u['a']['op'] != 'multiply': return None
        detail_xy, negative = u['a']['a'], u['a']['b']
        detail_z = u['b']
        if not _constant(negative, [-1]): return None
        if detail_xy['op'] != 'mask' or detail_xy['channels'] != [0,1]: return None
        if detail_z['op'] != 'mask' or detail_z['channels'] != [2]: return None
        if not _same(detail_xy['input'], detail_z['input']): return None
        return base
    except (KeyError, TypeError):
        return None


def main_normals(material):
    """Keep source UVs and layer masks; remove flatten/detail normal helpers.

    Normal-strength parameters in lerp(normal, flat, alpha) are deliberately
    bypassed. Alpha=1 removes detail, rather than representing unit strength.
    The original manifest is retained; every changed helper is reported.
    """
    result = copy.deepcopy(material)
    notes = set()
    if _constant(result.get('pixel_depth_offset'),[0]):
        marker='Connected Pixel Depth Offset is unsupported unless the captured value is provably zero'
        result['issues']=[issue for issue in result.get('issues',[]) if issue!=marker]
        notes.add('Pixel Depth Offset is provably zero at export; no depth displacement is required. Nonzero depth displacement remains unsupported.')
    legacy_world_issue='World-space normal materials are not translated'
    if legacy_world_issue in result.get('issues',[]):
        result['normal_space']='world'
        result['issues']=[issue for issue in result['issues'] if issue!=legacy_world_issue]
        notes.add('normal: legacy extraction explicitly marked Unreal world space; transform to MDL internal space')
    def rewrite(node):
        if not isinstance(node, dict): return node
        base = _rnm_base(node)
        if base is not None:
            notes.add('normal: use the main source normal; omit Unreal detail-normal blend')
            return rewrite(base)
        if node.get('op') == 'lerp':
            if _constant(node.get('b'), [0,0,1]):
                notes.add('normal: bypass lerp toward flat (0,0,1); source strength is 1')
                return rewrite(node['a'])
            if _constant(node.get('a'), [0,0,1]):
                notes.add('normal: bypass lerp from flat (0,0,1); source strength is 1')
                return rewrite(node['b'])
        return {k:rewrite(v) if isinstance(v,dict) else v for k,v in node.items()}
    if 'normal' in result.get('inputs', {}) and result.get('normal_space','tangent')=='tangent':
        result['inputs']['normal'] = rewrite(result['inputs']['normal'])
    return result, sorted(notes)


def foliage_normal(material):
    """OmniPBR's normal texture input requires one tangent-space RGB map."""
    if material.get('normal_space','tangent')!='tangent':
        raise Unsupported('World-space foliage normals require MDL')
    node = material.get('inputs', {}).get('normal', {'op':'constant','value':[0,0,1]})
    result = evaluate(node)
    if isinstance(result, Constant):
        if result.value != (0,0,1): raise Unsupported('OmniPBR requires a tangent normal map or a flat normal')
        return None
    if not isinstance(result, Sample) or result.channels[:3] != (0,1,2):
        raise Unsupported('OmniPBR normal must use an RGB texture')
    if result.scale[:3] not in ((2,-2,2), (2,2,2)) or result.bias[:3] not in ((-1,1,-1),(-1,-1,-1)):
        raise Unsupported('OmniPBR normal must be a decoded source normal map')
    if result.wrap_s != 'repeat' or result.wrap_t != 'repeat':
        raise Unsupported('Stock OmniPBR normal textures currently require repeat addressing')
    return result
