"""One decal-free MDL evaluator and parameter authority per Unreal base material."""
import hashlib,json,re
from .graph import INPUTS
from .material_policy import main_normals
from .mdl import Compiler,clean_helpers
from .emission import uses_emission

BASE_CONTROL='unreal:baseControl'
BASE_MATERIAL='unreal:baseMaterial'


def evaluator(base,textures):
    base,_=main_normals(base)
    compiler=Compiler(textures)
    compiler.expose_uv=not base.get('leaf_surface')
    compiler.surface_normal=base.get('inputs',{}).get('normal',{'op':'constant','value':[0,0,1]})
    compiler.surface_normal_space=base.get('normal_space','tangent')
    values={}
    for field,(_,width,default) in INPUTS.items():
        node=base.get('inputs',{}).get(field,{'op':'constant','value':list(default)})
        values[field]=compiler.compile(node)
    if base.get('leaf_surface'):values['base_color']=compiler.leaf_color(values['base_color'])
    if uses_emission(base):
        compiler.parameters['unreal_emissive_strength']={'type':'float','value':1.,'label':'Emissive strength','emission_control':True}
        values['emissive']=compiler.variable(compiler.four(values['emissive'])+' * float4(math::max(unreal_emissive_strength,0.0))',3)
    parameters={};rename={};declarations=[]
    for index,(key,param) in enumerate(compiler.parameters.items()):
        normalized='base_'+str(index);rename[key]=normalized
        parameters[normalized]=dict(param,identity='base:'+key)
        kind=param['type'];default='texture_2d()' if kind=='texture_2d' else 'false' if kind=='bool' else kind+'(0.0)'
        declarations.append(f'    uniform {kind} {normalized} = {default}')
    header=Compiler({}).material({'inputs':{}},prune=False)['source'].split('export material UnrealMaterial(',1)[0]
    header+=compiler.extra_helpers()
    fields='\n'.join('    float4 '+field+';' for field in INPUTS)
    arguments=', '.join(field+':'+compiler.four(values[field]) for field in INPUTS)
    body=('let {\n'+'\n'.join(compiler.lines)+'\n} in ') if compiler.lines else ''
    source=header+'export struct BridgeSurfaceData {\n'+fields+'\n};\n\nexport BridgeSurfaceData EvaluateBase(\n'+',\n'.join(declarations)+'\n) = '+body+'BridgeSurfaceData('+arguments+');\n'
    if rename:
        pattern=re.compile(r'\b(?:'+'|'.join(re.escape(k) for k in sorted(rename,key=len,reverse=True))+r')\b')
        source=pattern.sub(lambda m:rename[m.group()],source)
    source=clean_helpers(source.replace('to4(', 'to4_3('))
    module='BaseSurface_'+hashlib.sha256(source.encode()).hexdigest()[:20]
    return {'source':source,'module':module,'parameters':parameters,'uv_channels':sorted(compiler.uv_channels)}


def resolve(base,textures,layers=(),coordinate_slots=None,program=None):
    from .decals import compose,response_channels
    program=program or evaluator(base,textures);base,_=main_normals(base)
    proxy=dict(base);inputs={}
    for field in INPUTS:
        if field=='emissive' and not uses_emission(base):continue
        inputs[field]={'op':'shared_base','field':field,'module':program['module'],
                       'parameters':program['parameters'],'uv_channels':program['uv_channels']}
    proxy['inputs']=inputs
    updated=[]
    for decal,definition,frame in layers:
        frame=dict(frame,fixed_transform=True)
        if coordinate_slots is not None:frame['coordinate_slot']=coordinate_slots[decal['source']]
        updated.append((decal,definition,frame))
    material=compose(proxy,updated,response_channels(base.get('decal_response',1)))
    material['shared_base_shader']=True
    return material,program


def material(data,mat):
    base_key=mat.get('decal_base_key')
    if base_key is None:base_key=next((k for k in data.get('_shared_base_keys',()) if data['materials'][k] is mat),None)
    if base_key is None:return None
    layers=[data['_decal_layers'][source] for source in mat.get('decal_layers',[])]
    cached=data.get('_base_programs',{}).get(base_key)
    resolved,program=resolve(data['materials'][base_key],data['textures'],layers,mat.get('decal_coordinate_slots'),cached)
    data.setdefault('_base_programs',{})[base_key]=program
    resolved.update(name=mat.get('name',base_key),decal_base_key=base_key)
    return resolved

