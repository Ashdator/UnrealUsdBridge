"""Share shader definitions across material instances with different controls."""
import json
import re
from .mdl import control_annotations


def canonical_program(program):
    parameters={};rename={};declarations=[]
    for index,(key,param) in enumerate(program['parameters'].items()):
        name='geometry_displacement' if key=='geometry_displacement' else f'input_{index}'
        rename[key]=name;parameters[name]=dict(param,identity=param.get('identity',key))
        kind=param['type']
        default='texture_2d()' if kind=='texture_2d' else 'false' if kind=='bool' else '0.0' if kind=='float' else kind+'(0.0)'
        label=param.get('projection_field',param['label']) if param.get('projection_id') else param['label']
        # Texture filenames are instance metadata, not shader behavior. Keep the
        # real label on the USD attribute while equal programs share MDL source.
        if kind=='texture_2d':label=f'Texture {index}'
        if label.startswith(('parameter_','texture_')):label='Decal '+('texture' if kind=='texture_2d' else 'parameter')
        qualifier='' if key=='geometry_displacement' else 'uniform '
        bounds=', anno::hard_range(0.0,1.0)' if param.get('projection_field')=='amount' else ''
        bounds+=', anno::hidden()' if param.get('shared_projection_texture') or (param.get('projection_id') and param.get('projection_field')!='amount') else ''
        bounds+=control_annotations(param)
        if param.get('emission_control'): bounds+=', anno::in_group("Emission")'
        declarations.append(f'    {qualifier}{kind} {name} = {default} [[anno::display_name({json.dumps(label,ensure_ascii=True)}){bounds}]]')
    header,rest=program['source'].split('export material UnrealMaterial(',1)
    _,body=rest.split(') = let {',1)
    if rename:
        pattern=re.compile(r'\b(?:'+'|'.join(re.escape(key) for key in sorted(rename,key=len,reverse=True))+r')\b')
        body=pattern.sub(lambda m:rename[m.group()],body)
    result=dict(program)
    result['source']=header+'export material UnrealMaterial(\n'+',\n'.join(declarations)+'\n) = let {'+body
    result['parameters']=parameters
    return result
