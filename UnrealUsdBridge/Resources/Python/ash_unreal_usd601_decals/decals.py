"""Project Unreal decals into editable receiver materials without extra meshes."""
import copy
import hashlib
import itertools
import json
import math

from .graph import INPUTS
from .material_policy import main_normals
from .decal_regions import prepare,resolve,material_keys


def constant(value):
    return {'op': 'constant', 'value': value}


def projection(decal):
    """USD world meters; Unreal's decal local box spans [-1,1], X is depth."""
    m = decal['matrix']
    if len(m) != 16 or not all(math.isfinite(float(x)) for x in m):
        raise ValueError('Invalid decal projection transform')
    axes = [[m[4*i], -m[4*i+1], m[4*i+2]] for i in range(3)]
    lengths = [math.sqrt(sum(x*x for x in axis)) for axis in axes]
    if min(lengths) < 1e-6:
        raise ValueError('Decal projection has zero size')
    axes = [[x/size for x in axis] for axis, size in zip(axes, lengths)]
    if any(abs(sum(a*b for a,b in zip(axes[i],axes[j]))) > 1e-4
           for i,j in ((0,1),(0,2),(1,2))):
        raise ValueError('Sheared decal projection is unsupported')
    return {'id': decal['source'], 'label': decal.get('name', 'Decal'),
            'center': [m[12]*.01, -m[13]*.01, m[14]*.01],
            'half_size': [x*.01 for x in lengths],
            'axis_x': axes[0], 'axis_y': axes[1], 'axis_z': axes[2],
            'tint':decal.get('color',[1,1,1,1])}


def response_channels(value):
    # Unreal EMaterialDecalResponse; preserve the 0.5.15 channel set.
    return {0: (), 1: ('base_color','normal','roughness','metallic'),
            2: ('base_color',), 3: ('base_color','normal'),
            4: ('base_color','roughness','metallic'), 5: ('normal',),
            6: ('normal','roughness','metallic'),
            7: ('roughness','metallic')}.get(value, ())


def project_graph(node, frame):
    """Every Unreal decal UV channel reads the projector's Z,Y coordinates."""
    if isinstance(node,list): return [project_graph(x,frame) for x in node]
    if not isinstance(node,dict): return node
    if frame.get('fixed_transform') and node.get('op')=='constant' and node.get('parameter'):
        # Source decal graph values are fixed; only its final intensity is live.
        node={k:v for k,v in node.items() if k not in ('parameter','projection_id','projection_field','projection_label')}
    if node.get('op') == 'uv':
        return {'op':'decal_uv', 'projection':frame, 'scale':node.get('scale',[1,1])}
    if node.get('op') == 'texture' and 'uv' not in node:
        node = dict(node, uv={'op':'uv'})
    if node.get('op') == 'texture' or (node.get('op')=='constant' and node.get('parameter')):
        node=dict(node)
        if node.get('op')=='texture' and frame.get('cull_texture_samples'):
            node['projection_guard']=frame
        original=node.get('parameter')
        identity=(node['texture']+node.get('color_space','raw')) if node.get('op')=='texture' else original
        node['projection_id']=frame['id']
        node['projection_field']=('texture_' if node.get('op')=='texture' else 'parameter_')+hashlib.sha1(identity.encode()).hexdigest()[:12]
        node['projection_label']=original or 'Texture'
        if node.get('op')=='texture' and frame.get('fixed_transform'):
            # Placement UVs remain distinct, but identical source images need
            # only one texture handle in a shared receiving material.
            node['shared_projection_texture']=True
        if original:
            suffix=hashlib.sha1(frame['id'].encode()).hexdigest()[:8]
            node['parameter']=frame['label']+': '+original+' ['+suffix+']'
    if node.get('op') == 'vertex_color': return constant([1,1,1,1])
    if node.get('op') == 'decal_color': return {'op':'decal_tint','projection':frame}
    if node.get('op') == 'object_position':
        c=frame['center']; return constant([c[0]*100,-c[1]*100,c[2]*100])
    return {k:project_graph(v,frame) for k,v in node.items()}


def local_bounds(mesh):
    points=mesh['points']
    return [(min(p[i] for p in points),max(p[i] for p in points)) for i in range(3)]


def overlaps(instance, bounds, decal):
    from pxr import Gf
    inv=Gf.Matrix4d(*decal['matrix']).GetInverse()
    component=Gf.Matrix4d(*instance['matrix'])
    corners=[Gf.Vec3d(*p) for p in itertools.product(*bounds)]
    placements=instance.get('transforms', [None])
    for placement in placements:
        transform=component if placement is None else Gf.Matrix4d(*placement)*component
        points=[inv.Transform(transform.Transform(p)) for p in corners]
        if all(min(p[i] for p in points) <= 1 and max(p[i] for p in points) >= -1 for i in range(3)):
            return True
    return False


def compose(base, layers, channels):
    mat,_=main_normals(base)
    values=copy.deepcopy(mat.get('inputs',{}))
    # Blend normal maps in renderer world coordinates, never in receiver UV space.
    world_normal={'op':'surface_world_normal','input':values.get('normal',constant([0,0,1]))}
    blends={channel:[] for channel in ('base_color','roughness','metallic','normal')}
    for decal, definition, frame in layers:
        inputs=definition['inputs']
        alpha={'op':'multiply', 'a':{'op':'decal_mask','projection':frame},
               'b':project_graph(inputs.get('opacity',constant([1])),frame)}
        alpha={'op':'clamp','input':alpha,'min':constant([0]),'max':constant([1])}
        available=set(definition.get('decal_channels', inputs.keys())) & set(channels)
        if 'emissive' in definition.get('decal_channels', inputs.keys()) and 'emissive' in inputs:
            # Emission adds radiance; a non-emissive decal must never erase an
            # already glowing receiving material. Its shared amount masks it.
            values['emissive']={'op':'add','a':values.get('emissive',constant([0,0,0])),
                'b':{'op':'decal_contribution','value':project_graph(inputs['emissive'],frame),'alpha':alpha}}
        for channel in ('base_color','roughness','metallic'):
            if channel in available:
                blends[channel].append({'value':project_graph(inputs[channel],frame),'alpha':alpha})
        if 'normal' in available:
            blends['normal'].append({'value':{'op':'decal_world_normal','projection':frame,
                     'input':project_graph(inputs['normal'],frame)}, 'alpha':alpha})
    for channel in ('base_color','roughness','metallic'):
        if blends[channel]:
            values[channel]={'op':'decal_blend','base':values.get(channel,constant(list(INPUTS[channel][2]))),'layers':blends[channel]}
    if blends['normal']:
        # The MDL backend consumes this separately from tangent-space normals.
        mat['decal_world_normal']={'op':'decal_blend','base':world_normal,'layers':blends['normal'],'normalize':True}
    mat['inputs']=values
    mat['decal_layers']=[d['source'] for d,_,_ in layers]
    return mat
