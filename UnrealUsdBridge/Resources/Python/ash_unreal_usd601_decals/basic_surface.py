"""Recover unsupported static surfaces using their connected source maps only.

This is a reported approximation, used only after full translation fails.
Sky, camera-depth, water, landscape layers and decals retain their policies.
"""
import copy
from .graph import Constant, UV, Unsupported, evaluate
from .mdl import compile_mdl
from .material_policy import main_normals
from .water_policy import excluded

CHANNELS=('base_color','normal','roughness','opacity')
RECOVERABLE=('VertexInterpolator','vertex-stage','Explicit texture mip',
             'Pixel Depth Offset','DitherTemporalAA','DeriveTangentBasis',
             'MF_Triplanar','Vector Transform requires','Unsupported Unreal shading model')


def _textures(node,channel):
    """Follow surface-value branches, never UVs or blend/selection masks."""
    if not isinstance(node,dict):return []
    op=node.get('op')
    if op=='texture':
        if node.get('texture_dimension') or node.get('usage')=='landscape_weight':return []
        # Screen-space noise is a rendering effect, not a surface texture.
        if 'ScreenPosition' in str(node.get('uv',{})):return []
        if channel=='normal' and not node.get('normal_map'):return []
        selected=list(node.get('channels',[0,1,2,3]))
        return [(node,selected)]
    if op=='mask':
        if channel=='normal':return _textures(node.get('input'),channel)
        result=[]
        for texture,selected in _textures(node.get('input'),channel):
            indices=node.get('channels',[])
            if indices and all(i<len(selected) for i in indices):
                result.append((texture,[selected[i] for i in indices]))
        return result
    fields=('a','b') if op=='lerp' else ('a','b','greater','equal','less') if op=='if' and channel=='opacity' else ('greater','equal','less') if op=='if' else tuple(node)
    result=[]
    for key in fields:
        if key not in ('uv','alpha','direction','projection','diagnostic_inputs'):
            result.extend(_textures(node.get(key),channel))
    return result


def recover(material,textures):
    if excluded(material) or material.get('unlit') or material.get('decal_channels') is not None:
        return None
    source=material.get('inputs',{})
    if 'landscape_weight' in str(source):return None
    probe,_=main_normals(material)
    _,issues=compile_mdl(probe,textures)
    if not issues or not all(any(marker in issue for marker in RECOVERABLE) for issue in issues):return None
    # Preserve source layer blends if a rendering effect alone blocked them.
    layered=any(len({(t['texture'],tuple(c)) for t,c in _textures(source.get(channel),channel)})>1 for channel in CHANNELS)
    if layered:
        candidate=copy.deepcopy(probe)
        candidate['inputs']={k:v for k,v in candidate.get('inputs',{}).items() if k in CHANNELS}
        candidate['issues']=[];candidate.pop('pixel_depth_offset',None)
        _,remaining=compile_mdl(candidate,textures)
        if not remaining and candidate['inputs'].get('base_color'):
            candidate['basic_surface_fallback']={'original_issues':issues,
                'notes':['Retained source layers, blend masks and UVs; omitted unsupported rendering effects.'],
                'policy':'Source base color, normal, roughness and opacity graphs; rendering effects omitted.'}
            return candidate
    inputs={};notes=[]
    for channel in CHANNELS:
        node=source.get(channel)
        if node is None:continue
        candidates={}
        for texture,channels in _textures(node,channel):
            channels=channels[:3] if channel in ('base_color','normal') else channels[:1]
            if len(channels)!=(3 if channel in ('base_color','normal') else 1):continue
            candidates[(texture['texture'],tuple(channels))]=(texture,channels)
        if len(candidates)>1:
            # Multiple surface maps need their layer blend; never guess by name.
            return None
        if not candidates:
            try:value=evaluate(node)
            except (Unsupported,KeyError,ValueError):value=None
            if isinstance(value,Constant):inputs[channel]=copy.deepcopy(node)
            elif channel in ('normal','roughness'):
                notes.append(channel+': no recoverable source map; use standard flat normal/roughness default')
            else:return None
            continue
        texture,channels=next(iter(candidates.values()))
        if texture['texture'] not in textures:return None
        sample=copy.deepcopy(texture)
        sample.pop('sampling_issue',None)
        try:uv=evaluate(sample.get('uv',{'op':'uv'}))
        except (Unsupported,KeyError,ValueError):uv=None
        if not isinstance(uv,UV):
            sample['uv']={'op':'uv','channel':int(sample.pop('source_uv_channel',0))}
            notes.append(channel+': complex source projection replaced by mesh UVs')
        sample['channels']=channels
        if channel=='normal':sample['color_space']='raw'
        inputs[channel]=sample
        notes.append(channel+': original connected texture '+textures[texture['texture']].get('source',texture['texture'])+' channels '+str(channels))
    if not inputs.get('base_color'):return None
    result=copy.deepcopy(material)
    result.update(inputs=inputs,issues=[],normal_space='tangent',unlit=False,
                  basic_surface_fallback={'original_issues':issues,'notes':notes,
                    'policy':'Source base color, tangent normal, roughness and opacity only; rendering effects omitted.'})
    result.pop('pixel_depth_offset',None)
    return result
