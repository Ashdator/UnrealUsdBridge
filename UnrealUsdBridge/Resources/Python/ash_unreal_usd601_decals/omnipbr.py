"""Stock OmniPBR foliage, with live functions for richer Unreal surface inputs."""
from .graph import Constant, INPUTS, Unsupported, evaluate
from .material_policy import foliage_normal
from .mdl import compile_function
from .emission import uses_emission


PORTS = {
    'base_color': ('diffuse_color_constant', 'color'),
    'roughness': ('reflection_roughness_constant', 'float'),
    'metallic': ('metallic_constant', 'float'),
    'opacity': ('opacity_constant', 'float'),
    'emissive': ('emissive_color', 'color'),
}


def compile_omnipbr(material, textures):
    if material.get('issues'): return None, list(material['issues'])
    try:
        normal = foliage_normal(material)
        result = {'normal':normal, 'functions':{}, 'constants':{}, 'uv_channels':set()}
        if normal: result['uv_channels'].add(normal.uv.channel)
        for channel, (port, kind) in PORTS.items():
            if channel=='emissive' and not uses_emission(material): continue
            default = INPUTS[channel][2]
            node = material.get('inputs',{}).get(channel, {'op':'constant','value':list(default)})
            try: value = evaluate(node)
            except Unsupported: value = None
            if isinstance(value, Constant) and not (material.get('leaf_surface') and channel=='base_color'):
                result['constants'][channel] = value.value
            else:
                function = compile_function(node, textures, kind,material.get('inputs',{}).get('normal'),
                    expose_uv=not material.get('leaf_surface'),leaf_color=bool(material.get('leaf_surface') and channel=='base_color'))
                result['functions'][channel] = function
                result['uv_channels'].update(function['uv_channels'])
        result['uv_channels'] = sorted(result['uv_channels'])
        return result, []
    except (Unsupported, KeyError, ValueError) as exc:
        return None, [str(exc)]


def parameters(shader, values):
    from pxr import Gf, Sdf
    for key, p in values.items():
        if p['type']=='texture_2d':
            attr=shader.CreateInput(key,Sdf.ValueTypeNames.Asset)
            attr.Set(Sdf.AssetPath('./'+p['file']))
            attr.GetAttr().SetColorSpace(p['color_space'])
        elif p['type']=='float':
            attr=shader.CreateInput(key,Sdf.ValueTypeNames.Float); attr.Set(float(p['value']))
        elif p['type']=='float3':
            attr=shader.CreateInput(key,Sdf.ValueTypeNames.Color3f if p.get('leaf_color_control') else Sdf.ValueTypeNames.Float3); attr.Set(Gf.Vec3f(*p['value']))
        elif p['type']=='float2':
            attr=shader.CreateInput(key,Sdf.ValueTypeNames.Float2); attr.Set(Gf.Vec2f(*p['value']))
        else:
            attr=shader.CreateInput(key,Sdf.ValueTypeNames.Float4); attr.Set(Gf.Vec4f(*p['value']))
        if p.get('uv_control'):attr.GetAttr().SetDisplayGroup('UV Coordinates')
        if p.get('leaf_color_control'):attr.GetAttr().SetDisplayGroup('Leaf Base Color')
        if p.get('hidden_control'):attr.GetAttr().SetHidden(True)
        attr.GetAttr().SetDisplayName(p['label'])


def author(stage, material, compiled, source, textures, root, name):
    from pxr import Gf, Sdf, UsdShade
    shader = UsdShade.Shader.Define(stage, material.GetPath().AppendChild('OmniPBR'))
    shader.CreateImplementationSourceAttr(UsdShade.Tokens.sourceAsset)
    shader.SetSourceAsset(Sdf.AssetPath('OmniPBR.mdl'), 'mdl')
    shader.SetSourceAssetSubIdentifier('OmniPBR', 'mdl')
    material.CreateSurfaceOutput('mdl').ConnectToSource(shader.CreateOutput('out',Sdf.ValueTypeNames.Token))
    def setting(key, kind, value):
        shader.CreateInput(key,kind).Set(value)
    setting('ao_to_diffuse', Sdf.ValueTypeNames.Float, 0.0)
    setting('enable_ORM_texture', Sdf.ValueTypeNames.Bool, False)
    active_emission=uses_emission(source)
    setting('enable_emission', Sdf.ValueTypeNames.Bool, active_emission)
    if active_emission:
        setting('emissive_intensity', Sdf.ValueTypeNames.Float, 1.0)
    setting('reflection_roughness_texture_influence', Sdf.ValueTypeNames.Float, 0.0)
    setting('metallic_texture_influence', Sdf.ValueTypeNames.Float, 0.0)
    setting('enable_opacity', Sdf.ValueTypeNames.Bool, 'opacity' in source.get('inputs',{}))
    setting('enable_opacity_texture', Sdf.ValueTypeNames.Bool, False)
    setting('opacity_threshold', Sdf.ValueTypeNames.Float, float(source.get('opacity_threshold',0)))
    # Imported normal pixels stay unchanged and are decoded by stock OmniPBR.
    normal = compiled['normal']
    if normal:
        inp=shader.CreateInput('normalmap_texture',Sdf.ValueTypeNames.Asset)
        inp.Set(Sdf.AssetPath('./'+textures[normal.texture]['file']))
        inp.GetAttr().SetColorSpace('raw')
        setting('bump_factor',Sdf.ValueTypeNames.Float,1.0)
        setting('flip_tangent_u',Sdf.ValueTypeNames.Bool,False)
        setting('flip_tangent_v',Sdf.ValueTypeNames.Bool,normal.scale[1]<0)
        setting('uv_space_index',Sdf.ValueTypeNames.Int,normal.uv.channel)
        setting('texture_scale',Sdf.ValueTypeNames.Float2,Gf.Vec2f(*normal.uv.scale))
        offset=normal.uv.offset; scale=normal.uv.scale
        setting('texture_translate',Sdf.ValueTypeNames.Float2,Gf.Vec2f(offset[0],1-scale[1]-offset[1]))
    if source.get('leaf_surface'):
        for key,kind,default in (('texture_scale',Sdf.ValueTypeNames.Float2,Gf.Vec2f(1)),
            ('texture_translate',Sdf.ValueTypeNames.Float2,Gf.Vec2f(0)),('texture_rotate',Sdf.ValueTypeNames.Float,0.)):
            attr=shader.GetPrim().GetAttribute('inputs:'+key)
            if not attr:
                attr=shader.CreateInput(key,kind).GetAttr();attr.Set(default)
            attr.SetHidden(True)
    for channel, (port, kind) in PORTS.items():
        if channel=='emissive' and not active_emission: continue
        usd_type=Sdf.ValueTypeNames.Color3f if kind=='color' else Sdf.ValueTypeNames.Float
        dest=shader.CreateInput(port,usd_type)
        if channel in compiled['constants']:
            value=compiled['constants'][channel]
            dest.Set(Gf.Vec3f(*(value*3 if len(value)==1 else value[:3])) if kind=='color' else value[0])
            continue
        function=compiled['functions'][channel]
        # A per-material directory avoids collisions with a material whose
        # source name happens to end in "_base_color", "_roughness", etc.
        relative=f'materials/{name}/{channel}.mdl'
        (root/relative).parent.mkdir(parents=True,exist_ok=True)
        (root/relative).write_text(function['source'],encoding='utf-8',newline='\n')
        node=UsdShade.Shader.Define(stage,material.GetPath().AppendChild(channel+'_graph'))
        node.CreateImplementationSourceAttr(UsdShade.Tokens.sourceAsset)
        node.SetSourceAsset(Sdf.AssetPath('./'+relative),'mdl')
        node.SetSourceAssetSubIdentifier('Evaluate','mdl')
        parameters(node,function['parameters'])
        dest.ConnectToSource(node.CreateOutput('out',usd_type))
    material.GetPrim().SetCustomDataByKey('unreal:displacementNote','Stock OmniPBR: add an MDL displacement modifier for future wind; no displacement or physics deformation is generated.')
