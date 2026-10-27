"""Generate editable MDL programs for graphs beyond USD Preview Surface.

The program keeps source texture lookups and graph arithmetic. No pixel outputs
are computed here. Only the required diffuse/GGX/cutout PBR lobes are generated.
"""
import hashlib
import json
import math
import re
from .graph import Unsupported, INPUTS
from .emission import uses_emission
from . import unreal_noise


def f(value):
    value=float(value)
    if not math.isfinite(value): raise Unsupported('Non-finite MDL literal')
    result=format(value,'.9g')
    return result if '.' in result or 'e' in result.lower() else result+'.0'


def name(value):
    return 'p_'+re.sub('[^A-Za-z0-9_]','_',value)[:45]+'_'+hashlib.sha1(value.encode()).hexdigest()[:8]


def parameter_display_name(value):
    # Correct the source label only; stable Unreal parameter identifiers stay intact.
    def corrected(match):
        original=match.group()
        return 'DESATURATION' if original.isupper() else 'desaturation' if original.islower() else 'Desaturation'
    return re.sub(r'(?i)(?<![a-z])deaturation(?![a-z])',corrected,value)


def decal_annotations(parameter):
    # Keep projected-decal controls out of the main material texture inputs.
    return ', anno::in_group("Decals"), anno::ui_order(1000)' if parameter.get('projection_id') or parameter.get('shared_projection_texture') else ''


def parameter_default(p):
    kind=p['type']
    if kind=='texture_2d':return 'texture_2d()'
    if kind=='bool':return 'true' if p['value'] else 'false'
    if kind=='float':return f(p['value'])
    return kind+'('+', '.join(map(f,p['value']))+')'


def control_annotations(p):
    result=decal_annotations(p)
    if p.get('uv_control'):result+=', anno::in_group("UV Coordinates")'
    if p.get('hidden_control'):result+=', anno::hidden()'
    if p.get('leaf_color_control'):result+=', anno::in_group("Leaf Base Color")'
    return result


def clean_helpers(source):
    # Distinct overload names let us remove genuinely unused helpers, including
    # landscape filtering from foliage functions, without suppressing warnings.
    for helper in ('landscape_weight','landscape_bilinear','rotate_delta','to4_2','to4_3'):
        if len(re.findall(r'\b'+helper+r'\s*\(',source))>1:continue
        match=re.search(r'^float[234]\s+'+helper+r'\s*\(',source,re.M)
        if not match:continue
        start=source.index('{',match.start());depth=1;end=start+1
        while depth:
            depth+=(source[end]=='{')-(source[end]=='}');end+=1
        source=source[:match.start()]+source[end:].lstrip('\r\n')
    return source


class Compiler:
    def __init__(self,textures):
        self.textures=textures; self.lines=[]; self.cache={}; self.parameters={}; self.uv_channels=set();self.modules=set()
        self.projector_slots={}
        self.surface_normal={'op':'constant','value':[0,0,1]}; self.reading_surface_normal=False
        self.needs_unreal_noise=False
        self.two_sided_sign=None
        self.expose_uv=True

    def leaf_color(self,value):
        self.parameters['leaf_tint']={'type':'float3','value':[1,1,1],'label':'Leaf color tint','leaf_color_control':True}
        self.parameters['leaf_brightness']={'type':'float','value':1.,'label':'Leaf brightness','leaf_color_control':True}
        self.parameters['leaf_darkening']={'type':'float','value':0.,'label':'Leaf darkening','leaf_color_control':True}
        gain=self.variable('to4(math::max(leaf_tint,float3(0.0))*math::max(leaf_brightness,0.0)*(1.0-math::clamp(leaf_darkening,0.0,1.0)))',3)
        return self.variable(self.four(value)+' * ('+gain[0]+' + float4(0.0,0.0,0.0,1.0))',3)

    def extra_helpers(self):
        return unreal_noise.HELPERS if self.needs_unreal_noise else ''

    def variable(self,expression,width):
        result='v'+str(len(self.lines))
        self.lines.append(f'    float4 {result} = {expression};')
        return result,width

    def v4(self,parts):
        parts=list(parts)
        if len(parts)==1: return f'float4({parts[0]})'
        return 'float4('+', '.join(parts+['0.0']*(4-len(parts)))+')'

    def parts(self,result):
        return [f'{result[0]}.{c}' for c in 'xyzw'[:result[1]]]

    def four(self,result):
        # A masked scalar is stored in x, with unused components padded with
        # zero. Replicate it when it participates in vector arithmetic.
        return f'float4({result[0]}.x)' if result[1]==1 else result[0]

    def vector(self,result,width=3):
        parts=self.parts(result)
        if len(parts)==1: parts*=width
        if len(parts)<width: raise Unsupported('Insufficient vector components')
        return f'float{width}('+', '.join(parts[:width])+')'

    def pixel_normal(self,depth):
        if self.reading_surface_normal:raise Unsupported('Pixel normal dependency cycle')
        self.reading_surface_normal=True
        try:normal=self.vector(self.compile(self.surface_normal,depth+1))
        finally:self.reading_surface_normal=False
        if getattr(self,'surface_normal_space','tangent')=='world':
            return f'math::normalize(state::transform_normal(state::coordinate_world,state::coordinate_internal,{normal} * float3(1.0,-1.0,1.0)))'
        return f'math::normalize(state::texture_tangent_u(0)*{normal}.x - state::texture_tangent_v(0)*{normal}.y + state::normal()*{normal}.z)'

    def projector(self,frame,need_axes=False):
        indexed='coordinate_slot' in frame
        slot=self.projector_slots.setdefault(frame['id'],len(self.projector_slots))
        prefix='decal_slot_'+str(frame['coordinate_slot']) if indexed else 'decal_'+str(slot)
        for field in ('center','half_size','axis_x','axis_y','axis_z'):
            if indexed and (field=='center' or not need_axes):continue
            if frame.get('fixed_transform') and not frame.get('parameterized_transform') and not indexed:
                cache_key='fixed-projector:'+prefix+'_'+field
                if cache_key not in self.cache:
                    self.lines.append('    float3 '+prefix+'_'+field+' = float3('+', '.join(map(f,frame[field]))+');')
                    self.cache[cache_key]=True
            else:
                self.parameters[prefix+'_'+field]={'type':'float3','value':frame[field],
                    'label':frame['label']+' '+field, 'projection_id':frame['id'],'projection_field':field,
                    'identity':'decal:'+frame['id']+':'+field}
        self.parameters[prefix+'_amount']={'type':'float','value':1.0,
            'label':frame['label']+' intensity', 'minimum':0.0,'maximum':1.0,
            'projection_id':frame['id'],'projection_field':'amount','identity':'decal:'+frame['id']+':amount'}
        return prefix

    def projector_position(self,frame):
        # One coordinate evaluation per projector, independent of the base UVs.
        key='projector-position:'+frame['id']
        if key not in self.cache:
            if 'coordinate_slot' in frame:
                self.projector(frame)
                self.cache[key]=self.variable('to4(scene::data_lookup_float3("bridge_decalUVW'+str(frame['coordinate_slot'])+'",float3(2.0)))',3)
                return self.cache[key]
            p=self.projector(frame)
            world='state::transform_point(state::coordinate_internal,state::coordinate_world,state::position()) * state::meters_per_scene_unit()'
            delta=f'({world} - {p}_center)'
            components=[f'math::dot({delta},{p}_axis_{axis}) / math::max({p}_half_size.{axis},0.000001)' for axis in 'xyz']
            self.cache[key]=self.variable('float4('+', '.join(components)+',0.0)',3)
        return self.cache[key]

    def compile(self,node,depth=0):
        if depth>128: raise Unsupported('Material graph depth exceeded')
        key=json.dumps(node,sort_keys=True,separators=(',',':'))
        if key in self.cache: return self.cache[key]
        def child(field): return self.compile(node[field],depth+1)
        op=node.get('op')
        if op=='unsupported' and node.get('reason','').startswith('MaterialExpressionNoise at ') and node.get('noise_settings'):
            # Older diagnostic manifests contain the complete Noise inputs.
            # Reuse them without requiring another Unreal extraction.
            op='unreal_noise'
        if op=='unsupported' and node.get('reason','').startswith('MaterialExpressionTwoSidedSign at '):
            op='two_sided_sign'
        if op=='shared_base':
            module=node['module'];self.modules.add(module);self.uv_channels.update(node['uv_channels'])
            cache_key='shared-base:'+module
            if cache_key not in self.cache:
                self.parameters.update(node['parameters'])
                args=', '.join(node['parameters'])
                self.lines.append('    '+module+'::BridgeSurfaceData bridge_base = '+module+'::EvaluateBase('+args+');')
                self.cache[cache_key]=True
            result=self.variable('bridge_base.'+node['field'],INPUTS[node['field']][1])
        elif op=='decal_tint':
            frame=node['projection']
            if frame.get('fixed_transform'):
                result=(self.v4(map(f,frame['tint'])),4)
            else:
                key=self.projector(frame)+'_tint'
                self.parameters[key]={'type':'float4','value':frame['tint'],
                    'label':frame['label']+' tint','projection_id':frame['id'],'projection_field':'tint'}
                result=(key,4)
        elif op in ('decal_uv','decal_mask'):
            p=self.projector(node['projection']); local=self.projector_position(node['projection'])[0]
            if op=='decal_uv':
                scale=node.get('scale',[1,1])
                result=self.variable(f'float4(({local}.z*0.5+0.5)*{f(scale[0])},({local}.y*0.5+0.5)*{f(scale[1])},0.0,0.0)',2)
            else:
                inside=' && '.join(f'math::abs({local}.{axis})<=1.0' for axis in 'xyz')
                fade=f'math::clamp(4.0-4.0*math::abs({local}.x),0.0,1.0)'
                result=self.variable(f'float4(({inside}) ? {fade}*math::clamp({p}_amount,0.0,1.0) : 0.0)',1)
        elif op=='surface_world_normal':
            n=self.vector(child('input'))
            result=self.variable(f'to4(math::normalize(state::texture_tangent_u(0)*{n}.x - state::texture_tangent_v(0)*{n}.y + state::normal()*{n}.z))',3)
        elif op=='decal_world_normal':
            p=self.projector(node['projection'],need_axes=True); n=self.vector(child('input'))
            # UE decal tangent basis: X maps to +Z, Y to +Y, Z to -X.
            normal=f'({p}_axis_z*{n}.x/math::max({p}_half_size.z,0.000001) + {p}_axis_y*{n}.y/math::max({p}_half_size.y,0.000001) - {p}_axis_x*{n}.z/math::max({p}_half_size.x,0.000001))'
            result=self.variable(f'to4(math::normalize(state::transform_normal(state::coordinate_world,state::coordinate_internal,{normal})))',3)
        elif op=='constant':
            values=node['value'] if isinstance(node['value'],list) else [node['value']]
            if not 1<=len(values)<=4: raise Unsupported('Invalid constant width')
            if node.get('parameter'):
                param=name(node['parameter'])
                scalar=len(values)==1
                self.parameters[param]={'type':'float' if scalar else 'float4','value':values[0] if scalar else values+[0]*(4-len(values)),'label':parameter_display_name(node.get('parameter_label',node['parameter']))}
                if not self.expose_uv:
                    from .leaf_controls import uv_parameter
                    if uv_parameter(self.parameters[param]['label']):self.parameters[param]['hidden_control']=True
                if node.get('projection_id'):
                    self.parameters[param].update(projection_id=node['projection_id'],projection_field=node['projection_field'],label=node['projection_label'])
                result=(f'float4({param})' if scalar else param,len(values))
            else: result=(self.v4(map(f,values)),len(values))
        elif op=='uv':
            channel=int(node.get('channel',0)); self.uv_channels.add(channel)
            if channel<0: raise Unsupported('Negative UV channel')
            scale=node.get('scale',[1,1])
            if not self.expose_uv:
                result=self.variable(f'float4(state::texture_coordinate({channel}).x * {f(scale[0])}, (1.0 - state::texture_coordinate({channel}).y) * {f(scale[1])}, 0.0, 0.0)',2)
                self.cache[key]=result
                return result
            # Expose each distinct source UV transform once. Identical UV nodes
            # share controls across texture channels; projected decals use
            # decal_uv and never receive these base-material controls.
            prefix='uv_'+str(channel)+'_'+hashlib.sha1(json.dumps([channel,scale]).encode()).hexdigest()[:8]
            for field,vector in (('tiling',scale),('offset',[0,0])):
                self.parameters[prefix+'_'+field]={'type':'float2','value':vector,
                    'label':f'UV {channel} '+field.title(),'uv_control':True}
            result=self.variable(f'float4(state::texture_coordinate({channel}).x * {prefix}_tiling.x + {prefix}_offset.x, (1.0 - state::texture_coordinate({channel}).y) * {prefix}_tiling.y + {prefix}_offset.y, 0.0, 0.0)',2)
        elif op=='texture':
            if node.get('sampling_issue'):raise Unsupported(node['sampling_issue'])
            texture=node['texture']
            if texture not in self.textures: raise Unsupported('Missing texture '+texture)
            cubemap=node.get('texture_dimension')=='cube_longlat'
            if cubemap:
                if node.get('normal_map'):raise Unsupported('Cubemap normal decoding requires a world-space normal backend')
                direction=child('direction')
                if direction[1]!=3:raise Unsupported('Cubemap direction must have three components')
                d=self.variable(f'to4(math::normalize({self.vector(direction)}))',3)
                # UE swaps Y/Z when constructing cube faces from its panorama.
                # Original panorama lookup is atan2(X,-Y), acos(Z). Preserve
                # its half-texel convention and MDL texture V orientation.
                resolution=self.textures[texture].get('resolution')
                if not resolution or min(resolution)<=0:raise Unsupported('Cubemap panorama resolution is missing')
                u=f'(1.0 + math::atan2({d[0]}.x,-{d[0]}.y)/math::PI)*0.5 + {f(0.5/resolution[0])}'
                v=f'math::acos(math::clamp({d[0]}.z,-1.0,1.0))/math::PI + {f(0.5/resolution[1])}'
                uv=self.variable(f'float4({u},1.0-({v}),0.0,0.0)',2)
            else:
                uv=self.compile(node.get('uv',{'op':'uv'}),depth+1)
            identity='fixed-projected-texture' if node.get('shared_projection_texture') else node.get('projection_id','')
            param='tex_'+hashlib.sha1((texture+node.get('color_space','raw')+identity).encode()).hexdigest()[:16]
            self.parameters[param]={'type':'texture_2d','file':self.textures[texture]['file'],'color_space':node.get('color_space','raw'),'label':self.textures[texture].get('source',texture).rsplit('/',1)[-1]}
            if node.get('shared_projection_texture'):
                self.parameters[param]['shared_projection_texture']=True
            elif node.get('projection_id'):
                self.parameters[param].update(projection_id=node['projection_id'],projection_field=node['projection_field'])
            wrap={'repeat':'wrap_repeat','clamp':'wrap_clamp','mirror':'wrap_mirrored_repeat'}
            ws,wt=('wrap_repeat','wrap_clamp') if cubemap else (wrap[node.get('wrap_s','repeat')],wrap[node.get('wrap_t','repeat')])
            lookup=f'tex::lookup_float4({param}, float2({uv[0]}.x, 1.0-{uv[0]}.y), tex::{ws}, tex::{wt})'
            if node.get('projection_guard'):
                # The footprint is independent of texture alpha. Put the lookup
                # inside the branch, so RTX can skip it outside the box or when
                # uniform intensity is zero. Base textures remain unconditional.
                guard=self.compile({'op':'decal_mask','projection':node['projection_guard']},depth+1)
                neutral='float4(0.5,0.5,1.0,1.0)' if node.get('normal_map') else 'float4(0.0)'
                lookup=f'({guard[0]}.x > 0.0) ? {lookup} : {neutral}'
            result=self.variable(lookup,4)
            if node.get('usage')=='landscape_weight':
                if node.get('color_space','raw')!='raw':raise Unsupported('Landscape weights must be raw data')
                self.parameters['landscape_mask_softness']={'type':'float','value':0.0,'label':'Landscape Mask Softness (texels)','minimum':0.0,'maximum':2.0}
                result=self.variable(f'landscape_weight({param}, float2({uv[0]}.x, 1.0-{uv[0]}.y), math::clamp(landscape_mask_softness,0.0,2.0))',4)
            if node.get('normal_map'):
                sy=-2 if node.get('flip_green') else 2
                by=1 if node.get('flip_green') else -1
                result=self.variable(f'{result[0]} * float4(2.0,{f(sy)},2.0,1.0) + float4(-1.0,{f(by)},-1.0,0.0)',4)
        elif op=='mask':
            a=child('input'); channels=node['channels']
            if not channels or any(i<0 or i>=a[1] for i in channels): raise Unsupported('Invalid component mask')
            result=self.variable(self.v4(f'{a[0]}.{"xyzw"[i]}' for i in channels),len(channels))
        elif op in ('add','subtract','multiply','divide','power','dot','append','fmod','distance','cross'):
            a,b=child('a'),child('b')
            width=max(a[1],b[1]) if min(a[1],b[1])==1 else min(a[1],b[1])
            if op=='append':
                parts=self.parts(a)+self.parts(b)
                if len(parts)>4: raise Unsupported('Append exceeds float4')
                result=self.variable(self.v4(parts),len(parts))
            elif op=='dot':
                width=min(a[1],b[1])
                result=self.variable(f'float4(math::dot({self.vector(a,width)}, {self.vector(b,width)}))',1)
            elif op=='distance':
                if a[1]!=b[1] and min(a[1],b[1])!=1:raise Unsupported('Distance requires matching vector widths or a scalar')
                delta=self.variable(f'{self.four(a)} - {self.four(b)}',width)
                expression=f'math::abs({delta[0]}.x)' if width==1 else f'math::length({self.vector(delta,width)})'
                result=self.variable('float4('+expression+')',1)
            elif op=='cross':
                if a[1]!=3 or b[1]!=3:raise Unsupported('Cross Product requires two float3 inputs')
                result=self.variable(f'to4(math::cross({self.vector(a)}, {self.vector(b)}))',3)
            elif op=='power':
                result=self.variable(f'math::pow(math::max({self.four(a)},float4(0.0)),{self.four(b)})',width)
            elif op=='fmod':
                # Do not evaluate 0/0 in unused float4 padding lanes.
                if a[1]!=b[1] and min(a[1],b[1])!=1:
                    raise Unsupported('Signed remainder requires matching vector widths or a scalar')
                result=self.variable(self.v4(f'math::fmod({a[0]}.{"x" if a[1]==1 else c}, {b[0]}.{"x" if b[1]==1 else c})' for c in 'xyzw'[:width]),width)
            else:
                symbol={'add':'+','subtract':'-','multiply':'*','divide':'/'}[op]
                result=self.variable(f'{self.four(a)} {symbol} {self.four(b)}',width)
        elif op in ('sin','cos'):
            a=child('input')
            result=self.variable(f'math::{op}({a[0]} * {f(node.get("frequency",1))})',a[1])
        elif op=='fresnel':
            exponent,base=child('exponent'),child('base')
            if self.reading_surface_normal:raise Unsupported('Fresnel normal dependency cycle')
            self.reading_surface_normal=True
            try:normal=self.vector(self.compile(self.surface_normal,depth+1))
            finally:self.reading_surface_normal=False
            world=f'math::normalize(state::texture_tangent_u(0)*{normal}.x - state::texture_tangent_v(0)*{normal}.y + state::normal()*{normal}.z)'
            # Match UE's default PixelNormalWS/CameraVector expression. The
            # original graph's normal is subject to the requested main-normal policy.
            facing=f'math::max(math::dot({world}, -state::direction()),0.0)'
            power=f'math::pow(math::max(math::abs(1.0-{facing}),0.0001),{exponent[0]}.x)'
            result=self.variable(f'float4({power}*(1.0-{base[0]}.x)+{base[0]}.x)',1)
        elif op=='decal_contribution':
            value=child('value');alpha=child('alpha')
            # Add emission independently; disabled decals must contribute zero
            # even if unused texture arithmetic evaluates to an invalid value.
            result=self.variable(f'({alpha[0]}.x > 0.0) ? {self.four(value)} * {self.four(alpha)} : float4(0.0)',max(value[1],alpha[1]))
        elif op=='decal_blend':
            # Flat ordered layers avoid nesting a whole material graph for
            # every decal on a large receiver (e.g. a landscape).
            result=child('base')
            for layer in node['layers']:
                value=self.compile(layer['value'],depth+1)
                alpha=self.compile(layer['alpha'],depth+1)
                # Guard independent layer values, never the accumulated base.
                # Repeating the previous blend in both sides of a conditional
                # makes its dependent branch tree grow with every new layer.
                # Zero weights also sanitize unused decal arithmetic (e.g. NaN).
                positive=f'({alpha[0]}.x > 0.0)'
                weight=self.variable(f'{positive} ? {self.four(alpha)} : float4(0.0)',alpha[1])
                safe_value=self.variable(f'{positive} ? {self.four(value)} : float4(0.0)',value[1])
                result=self.variable(f'math::lerp({self.four(result)}, {self.four(safe_value)}, {self.four(weight)})',max(result[1],value[1]))
            if node.get('normalize'):
                # Composite vector contributions first. Repeated normalization
                # makes each layer depend nonlinearly on the whole prior chain.
                result=self.variable(f'to4(math::normalize({self.vector(result,3)}))',3)
        elif op=='lerp':
            a,b,t=child('a'),child('b'),child('alpha')
            result=self.variable(f'math::lerp({self.four(a)}, {self.four(b)}, {self.four(t)})',max(a[1],b[1]))
        elif op=='one_minus':
            a=child('input'); result=self.variable(f'float4(1.0)-{a[0]}',a[1])
        elif op=='clamp':
            a,lo,hi=child('input'),child('min'),child('max')
            result=self.variable(f'math::clamp({self.four(a)}, {self.four(lo)}, {self.four(hi)})',a[1])
        elif op=='normalize':
            a=child('input')
            if a[1]==1: result=self.variable(f'float4(math::sign({a[0]}.x))',1)
            else:
                normalized=f'math::normalize({self.vector(a,a[1])})'
                result=self.variable(f'to4_{a[1]}({normalized})' if a[1]<4 else normalized,a[1])
        elif op=='abs':
            a=child('input'); result=self.variable(f'math::abs({a[0]})',a[1])
        elif op=='frac':
            a=child('input'); result=self.variable(f'{a[0]}-math::floor({a[0]})',a[1])
        elif op in ('ceil','floor'):
            a=child('input');result=self.variable(f'math::{op}({a[0]})',a[1])
        elif op=='desaturate':
            a,t=child('input'),child('fraction')
            weights='float3('+','.join(map(f,node['weights']))+')'
            result=self.variable(f'math::lerp({self.four(a)},float4(math::dot({self.vector(a)}, {weights})),{self.four(t)})',3)
        elif op=='vertex_color': result=self.variable('scene::data_lookup_float4("unreal_vertex_color",float4(1.0))',4)
        elif op=='object_position': result=self.variable('to4(scene::data_lookup_float3("unreal_object_position",float3(0.0)))',3)
        elif op=='per_instance_random': result=self.variable('float4(scene::data_lookup_float("unreal_instance_random",0.0))',1)
        elif op=='world_position': result=self.variable('to4(state::transform_point(state::coordinate_internal,state::coordinate_world,state::position()) * float3(1.0,-1.0,1.0) * (100.0*state::meters_per_scene_unit()))',3)
        elif op=='local_position':
            origin=node.get('origin')
            if origin=='component':
                # PointInstancer object space is relative to each instance;
                # UE Component origin is shared by the entire component.
                local='state::transform_point(state::coordinate_internal,state::coordinate_object,state::position()) * state::meters_per_scene_unit()'
                local_value=self.variable('to4('+local+')',3)[0]
                point=f'float4({local_value}.x,{local_value}.y,{local_value}.z,1.0)'
                defaults=('float4(1.0,0.0,0.0,0.0)','float4(0.0,1.0,0.0,0.0)','float4(0.0,0.0,1.0,0.0)')
                parts=[f'math::dot({point},scene::data_lookup_float4("unreal_instance_to_component_{i}",{defaults[i]}))' for i in range(3)]
                result=self.variable('to4(float3('+', '.join(parts)+') * float3(100.0,-100.0,100.0))',3)
            elif origin in ('instance','instance_pre_skinning'):
                # Exported meshes are static/rest pose; pre-skinned positions
                # equal object coordinates for this exported geometry.
                result=self.variable('to4(state::transform_point(state::coordinate_internal,state::coordinate_object,state::position()) * float3(1.0,-1.0,1.0) * (100.0*state::meters_per_scene_unit()))',3)
            else:raise Unsupported('Local Position requires an explicitly captured origin')
        elif op=='vertex_interpolator':
            from .vertex_interpolation import affine
            if not affine(node.get('input'))[0]:
                raise Unsupported('Nonlinear VertexInterpolator requires preserved vertex-stage evaluation')
            result=child('input')
        elif op=='camera_vector':
            result=self.variable('to4(state::transform_vector(state::coordinate_internal,state::coordinate_world,-state::direction()) * float3(1.0,-1.0,1.0))',3)
        elif op=='pixel_normal':
            result=self.variable(f'to4(state::transform_normal(state::coordinate_internal,state::coordinate_world,{self.pixel_normal(depth)}) * float3(1.0,-1.0,1.0))',3)
        elif op=='vertex_normal':
            # The incoming interpolated mesh normal, before this material's
            # normal-map perturbation; this must not call pixel_normal().
            result=self.variable('to4(math::normalize(state::transform_normal(state::coordinate_internal,state::coordinate_world,state::normal())) * float3(1.0,-1.0,1.0))',3)
        elif op=='two_sided_sign':
            if self.two_sided_sign is None:
                raise Unsupported('TwoSidedSign requires separate MDL front/back surfaces')
            result=(f'float4({f(self.two_sided_sign)})',1)
        elif op=='transform_vector':
            value=child('input');source=node['from'];target=node['to']
            if source not in ('tangent','object','world') or target not in ('tangent','object','world'):
                raise Unsupported('Vector Transform requires tangent, local or world space')
            if value[1]<3:raise Unsupported('Vector Transform input requires at least three components')
            vector=self.vector(value)
            if source==target:
                result=self.variable(f'to4({vector})',3)
            else:
                if source=='tangent':
                    internal=f'(state::texture_tangent_u(0)*{vector}.x - state::texture_tangent_v(0)*{vector}.y + state::normal()*{vector}.z)'
                else:
                    internal=f'state::transform_vector(state::coordinate_{source},state::coordinate_internal,{vector} * float3(1.0,-1.0,1.0))'
                internal=self.vector(self.variable(f'to4({internal})',3))
                if target=='tangent':
                    transformed=f'float3(math::dot({internal},state::texture_tangent_u(0)),-math::dot({internal},state::texture_tangent_v(0)),math::dot({internal},state::normal()))'
                else:
                    transformed=f'(state::transform_vector(state::coordinate_internal,state::coordinate_{target},{internal}) * float3(1.0,-1.0,1.0))'
                result=self.variable(f'to4({transformed})',3)
        elif op=='reflection_vector':
            if 'normal' in node:
                n=self.vector(child('normal'))
                n=f'state::transform_normal(state::coordinate_world,state::coordinate_internal,{n} * float3(1.0,-1.0,1.0))'
                if node.get('normalize_custom'):n=f'math::normalize({n})'
            else:n=self.pixel_normal(depth)
            nvar=self.variable(f'to4({n})',3)
            n=self.vector(nvar)
            reflected=f'(state::direction() - 2.0 * math::dot(state::direction(),{n}) * {n})'
            result=self.variable(f'to4(state::transform_vector(state::coordinate_internal,state::coordinate_world,{reflected}) * float3(1.0,-1.0,1.0))',3)
        elif op=='rotate_about_axis':
            axis,angle,pivot,position=child('axis'),child('angle'),child('pivot'),child('position')
            period=float(node.get('period',1))
            if period==0: raise Unsupported('Rotation period cannot be zero')
            result=self.variable(f'to4(rotate_delta({self.vector(axis)}, {angle[0]}.x * {f(2*math.pi/period)}, {self.vector(pivot)}, {self.vector(position)}))',3)
        elif op=='if':
            a,b,gt,eq,lt=child('a'),child('b'),child('greater'),child('equal'),child('less')
            result=self.variable(f'math::abs({a[0]}.x-{b[0]}.x) <= {f(node.get("threshold",1e-5))} ? {eq[0]} : ({a[0]}.x>{b[0]}.x ? {gt[0]} : {lt[0]})',max(gt[1],eq[1],lt[1]))
        elif op=='unreal_noise':
            settings=unreal_noise.configuration(node)
            position=child('position')
            if position[1]!=3:raise Unsupported('Unreal Voronoi position must have three components')
            filter_width=self.compile(node.get('filter_width',{'op':'constant','value':[0]}),depth+1)
            if filter_width[1]!=1:raise Unsupported('Unreal Voronoi filter width must be scalar')
            self.needs_unreal_noise=True
            args=[self.vector(position),filter_width[0]+'.x',f(settings['scale']),str(settings['quality']),
                  str(settings['levels']),f(settings['level_scale']),f(settings['output_min']),f(settings['output_max']),
                  'true' if settings.get('turbulence') else 'false','true' if settings.get('tiling') else 'false',f(settings['repeat_size'])]
            result=self.variable('float4(bridge_unreal_noise('+', '.join(args)+'))',1)
        elif op=='unsupported': raise Unsupported(node.get('reason','Unsupported expression'))
        else: raise Unsupported('No MDL translation for '+str(op))
        self.cache[key]=result
        return result

    def material(self,material,prune=True):
        self.expose_uv=not material.get('leaf_surface')
        if self.two_sided_sign is None:self.two_sided_sign=1.0
        self.surface_normal=material.get('inputs',{}).get('normal',{'op':'constant','value':[0,0,1]})
        self.surface_normal_space=material.get('normal_space','tangent')
        values={}
        for field,(_,width,default) in INPUTS.items():
            if field=='emissive' and not uses_emission(material): continue
            node=material.get('inputs',{}).get(field,{'op':'constant','value':list(default)})
            values[field]=self.compile(node)
        if material.get('leaf_surface') and not material.get('shared_base_shader'):
            values['base_color']=self.leaf_color(values['base_color'])
        normal=self.vector(values['normal'])
        if material.get('decal_world_normal'):
            self.lines.append(f'    float3 world_normal = {self.vector(self.compile(material["decal_world_normal"]))};')
        elif self.surface_normal_space=='world':
            self.lines.append(f'    float3 world_normal = math::normalize(state::transform_normal(state::coordinate_world,state::coordinate_internal,{normal} * float3(1.0,-1.0,1.0)));')
        else:
            self.lines.append(f'    float3 tangent_normal = {normal};')
            self.lines.append('    float3 world_normal = math::normalize(state::texture_tangent_u(0)*tangent_normal.x - state::texture_tangent_v(0)*tangent_normal.y + state::normal()*tangent_normal.z);')
        def rgb(field):
            v=self.vector(values[field]); return f'color({v}.x,{v}.y,{v}.z)'
        def scalar(field): return values[field][0]+'.x'
        # Evaluate the combined decal normal once in the material geometry.
        # Reusing its whole expression as each BSDF layer normal causes the
        # renderer to compile it into multiple distribution-function paths.
        projected_normal=bool(material.get('decal_world_normal'))
        layer_normal='state::normal()' if projected_normal else 'world_normal'
        geometry_normal='world_normal' if projected_normal else 'state::normal()'
        # Expand the non-coated OmniPBRBase scattering lobes used
        # by this bridge. Avoid importing its unrelated coat/rounded-edge paths.
        scattering_start=len(self.lines)
        self.lines.extend([
            f'    color base_color = {rgb("base_color")};',
            f'    float rough = math::clamp({scalar("roughness")}*{scalar("roughness")},0.0,1.0);',
            f'    bsdf diffuse = df::weighted_layer(weight:1.0,layer:df::diffuse_reflection_bsdf(tint:base_color,roughness:0.0),base:bsdf(),normal:{layer_normal});',
            '    bsdf glossy = df::microfacet_ggx_smith_bsdf(roughness_u:rough,roughness_v:rough,tint:color(1.0),mode:df::scatter_reflect);',
            '    bsdf dielectric = df::custom_curve_layer(normal_reflectivity:0.08,grazing_reflectivity:1.0,exponent:5.0,weight:0.5,layer:glossy,base:diffuse,normal:'+layer_normal+');',
            f'    bsdf scattering = df::weighted_layer(weight:{scalar("metallic")},layer:df::tint(base_color,glossy),base:dielectric,normal:{layer_normal});',
        ])
        if material.get('unlit'):
            # An Unreal Unlit emitter has no reflected-light BSDF.
            self.lines[scattering_start:]=['    bsdf scattering = bsdf();']
        emission=''
        if 'emissive' in values:
            gain='unreal_emissive_strength'
            if material.get('shared_base_shader'):
                emission=f',emission:material_emission(df::diffuse_edf(),intensity:math::max({rgb("emissive")},color(0.0)))'
            else:
                self.parameters[gain]={'type':'float','value':1.0,'label':'Emissive strength','emission_control':True}
                emission=f',emission:material_emission(df::diffuse_edf(),intensity:math::max({rgb("emissive")},color(0.0))*math::max({gain},0.0))'
        opacity=scalar('opacity') if 'opacity' in material.get('inputs',{}) else '1.0'
        threshold=float(material.get('opacity_threshold',0))
        cutout=f'({opacity}>={f(threshold)} ? 1.0 : 0.0)' if threshold else opacity
        self.lines.append(f'    material pbr = material(surface:material_surface(scattering:scattering{emission}),geometry:material_geometry(normal:{geometry_normal},cutout_opacity:{cutout}));')
        declarations=[]
        for key,p in self.parameters.items():
            default=parameter_default(p)
            bounds=f', anno::hard_range({f(p["minimum"])},{f(p["maximum"])})' if 'minimum' in p else ''
            bounds+=', anno::hidden()' if p.get('shared_projection_texture') or (p.get('projection_id') and p.get('projection_field')!='amount') else ''
            bounds+=control_annotations(p)
            if p.get('emission_control'): bounds+=', anno::in_group("Emission")'
            declarations.append(f'    uniform {p["type"]} {key} = {default} [[anno::display_name({json.dumps(p["label"],ensure_ascii=True)}){bounds}]]')
        surface='pbr'
        if material.get('two_sided'):
            surface='material(thin_walled:true,surface:pbr.surface,backface:pbr.surface,ior:pbr.ior,geometry:pbr.geometry)'
        if material.get('foliage') or material.get('foliage_instance'):
            # Varying input: an MDL texture/noise graph can drive this later.
            # Expose meters; MDL geometry consumes renderer scene units.
            declarations.append('    float3 geometry_displacement = float3(0.0) [[anno::display_name("Displacement (meters)")]]')
            self.parameters['geometry_displacement']={'type':'float3','value':[0,0,0],'label':'Displacement (meters)'}
            surface='material(thin_walled:true,surface:pbr.surface,backface:pbr.surface,ior:pbr.ior,geometry:material_geometry(displacement:geometry_displacement*state::scene_units_per_meter(),cutout_opacity:pbr.geometry.cutout_opacity,normal:pbr.geometry.normal))'
        source='''mdl 1.7;
import ::df::*;
import ::math::*;
import ::state::*;
import ::tex::*;
import ::scene::*;
import ::anno::*;

float4 to4_3(float3 v) { return float4(v.x,v.y,v.z,0.0); }
float4 to4_2(float2 v) { return float4(v.x,v.y,0.0,0.0); }

// Sample painted data at texel centers with linear interpolation. Do not use
// color corrections or re-bake masks. All layers share the same filter.
float4 landscape_bilinear(uniform texture_2d t, float2 uv) {
    int2 size = int2(math::max(tex::width(t),1),math::max(tex::height(t),1));
    float2 p = math::clamp(uv,float2(0.0),float2(1.0))*float2(size)-float2(0.5);
    int2 lo = int2(math::floor(p));
    float2 a = p-float2(lo);
    float4 c00 = tex::texel_float4(t,math::clamp(lo,int2(0),size-int2(1)));
    float4 c10 = tex::texel_float4(t,math::clamp(lo+int2(1,0),int2(0),size-int2(1)));
    float4 c01 = tex::texel_float4(t,math::clamp(lo+int2(0,1),int2(0),size-int2(1)));
    float4 c11 = tex::texel_float4(t,math::clamp(lo+int2(1,1),int2(0),size-int2(1)));
    return math::lerp(math::lerp(c00,c10,a.x),math::lerp(c01,c11,a.x),a.y);
}

float4 landscape_weight(uniform texture_2d t, float2 uv, uniform float softness) {
    float4 center = landscape_bilinear(t,uv);
    float2 step = float2(softness)/float2(math::max(tex::width(t),1),math::max(tex::height(t),1));
    return softness<=0.0 ? center : (4.0*center +
        2.0*(landscape_bilinear(t,uv+float2(step.x,0.0)) + landscape_bilinear(t,uv-float2(step.x,0.0)) +
             landscape_bilinear(t,uv+float2(0.0,step.y)) + landscape_bilinear(t,uv-float2(0.0,step.y))) +
        landscape_bilinear(t,uv+step) + landscape_bilinear(t,uv-step) +
        landscape_bilinear(t,uv+float2(step.x,-step.y)) + landscape_bilinear(t,uv+float2(-step.x,step.y)))/16.0;
}

float3 rotate_delta(float3 axis, float angle, float3 pivot, float3 position) {
    float3 v = position-pivot;
    float c = math::cos(angle);
    float s = math::sin(angle);
    return v*c + math::cross(axis,v)*s + axis*math::dot(axis,v)*(1.0-c) - v;
}

export material UnrealMaterial(
'''+',\n'.join(declarations)+'\n) = let {\n'+'\n'.join(self.lines)+'\n} in '+surface+';\n'
        source=source.replace('to4(', 'to4_3(')
        source=source.replace('export material UnrealMaterial(',self.extra_helpers()+'\nexport material UnrealMaterial(')
        if self.modules:
            source=source.replace('import ::anno::*;','import ::anno::*;\n'+'\n'.join('import .::'+module+'::*;' for module in sorted(self.modules)))
        if prune:source=clean_helpers(source)
        return {'source':source,'parameters':self.parameters,'uv_channels':sorted(self.uv_channels)}


def compile_mdl(material,textures):
    issues=list(material.get('issues',[]))
    if issues: return None,issues
    try:
        if material.get('two_sided') and contains_two_sided_sign(material.get('inputs',{})):
            if contains_two_sided_sign(material.get('inputs',{}).get('opacity',{})) or contains_two_sided_sign(material.get('decal_world_normal',{})):
                raise Unsupported('TwoSidedSign in shared cutout/projected geometry requires separate geometry handling')
            front=Compiler(textures);front.two_sided_sign=1.0
            back=Compiler(textures);back.two_sided_sign=-1.0
            a,b=front.material(material),back.material(material)
            if a['parameters']!=b['parameters']:
                raise Unsupported('Front/back MDL parameter layouts differ')
            marker='export material UnrealMaterial('
            header,body=a['source'].split(marker,1)
            back_header,back_body=b['source'].split(marker,1)
            if header!=back_header:raise Unsupported('Front/back MDL helper layouts differ')
            declarations=body.split(') = let {',1)[0]
            args=', '.join(a['parameters'])
            source=header+'material BridgeFront('+body+'\nmaterial BridgeBack('+back_body+'\n'
            source+=marker+declarations+') = let {\n    material front = BridgeFront('+args+');\n    material back = BridgeBack('+args+');\n} in material(thin_walled:true,surface:front.surface,backface:back.surface,ior:front.ior,volume:front.volume,geometry:front.geometry);\n'
            return dict(a,source=source,two_sided_sign_surfaces=True),[]
        return Compiler(textures).material(material),[]
    except (Unsupported,KeyError,ValueError) as exc:
        return None,[str(exc)]


def contains_two_sided_sign(node):
    if isinstance(node,dict):
        if node.get('op')=='two_sided_sign' or node.get('op')=='unsupported' and node.get('reason','').startswith('MaterialExpressionTwoSidedSign at '):return True
        return any(contains_two_sided_sign(value) for value in node.values())
    return isinstance(node,list) and any(contains_two_sided_sign(value) for value in node)


def compile_function(node, textures, output_type, surface_normal=None, *, expose_uv=True, leaf_color=False):
    """Live MDL color/scalar function feeding a stock OmniPBR input.

    This preserves graph math and packed channel selection without baking maps
    or replacing OmniPBR with a generated material definition.
    """
    compiler = Compiler(textures)
    compiler.expose_uv=expose_uv
    if surface_normal is not None:compiler.surface_normal=surface_normal
    value = compiler.compile(node)
    if leaf_color:value=compiler.leaf_color(value)
    # MDL forbids an empty let block. Literal emission colors can reach this
    # helper directly, so bind the result even when the graph has no statements.
    value = compiler.variable(value[0],value[1])
    declarations = []
    for key, p in compiler.parameters.items():
        default = parameter_default(p)
        declarations.append(f'    uniform {p["type"]} {key} = {default} [[anno::display_name({json.dumps(p["label"],ensure_ascii=True)}){control_annotations(p)}]]')
    # Share the validated math helpers with the complete-graph backend.
    header = Compiler({}).material({'inputs':{}},prune=False)['source'].split('export material UnrealMaterial(', 1)[0]
    header += compiler.extra_helpers()
    if output_type == 'color':
        v = compiler.vector(value)
        expression = f'color({v}.x,{v}.y,{v}.z)'
    else:
        expression = value[0]+'.x'
    source = header + f'export {output_type} Evaluate(\n' + ',\n'.join(declarations) + '\n) = let {\n' + '\n'.join(compiler.lines) + '\n} in ' + expression + ';\n'
    return {'source':clean_helpers(source.replace('to4(', 'to4_3(')),'parameters':compiler.parameters,'uv_channels':sorted(compiler.uv_channels)}
