"""Leaf color controls, with source UV transforms fixed at export values."""
import re
from .vegetation import exclusion_reason,plant_asset_name

PREVIEW_KEY='unreal:leafColorTarget'


def mark(data):
    plant_keys=set()
    for instance in data.get('instances',[])+data.get('instancers',[]):
        if exclusion_reason(data,instance):plant_keys.update(instance.get('materials',[]))
    for key,material in data['materials'].items():
        name=material.get('name','') or material.get('source','').rsplit('/',1)[-1].split('.')[0]
        name=re.sub(r'([a-z])([A-Z])',r'\1_\2',name)
        words=set(re.findall('[a-z]+',name.lower()))
        bark=bool(words & {'bark','trunk','wood','stem','stems'})
        # Some source assets use Leafes/Leafs. Treat these as leaf labels,
        # preserving the actual Unreal asset name and material identity.
        leaf=bool(words & {'leaf','leaves','leafes','leafs','needles','frond','fronds','branches'})
        masked='opacity' in material.get('inputs',{})
        plant=key in plant_keys or plant_asset_name(name) or bool(words & {'bb','billboard'}) or bool(re.search(r'billboard(?:_|$)',name.lower()))
        material['leaf_surface']=not bark and not material.get('excluded_water') and bool(
            material.get('foliage') or leaf or plant and (masked or material.get('two_sided')))


def uv_parameter(label):
    text=str(label).lower()
    return bool(re.search(r'til(?:e|ing)|\buv.*(?:scale|offset|rotation)',text))


def author_preview(material,surface,base_input,value):
    """Use ordinary UVTexture values so the saved result stays portable."""
    from pxr import Gf,Sdf,UsdShade
    for name,kind,default,label in (
        ('leaf_tint',Sdf.ValueTypeNames.Color3f,Gf.Vec3f(1),'Leaf color tint'),
        ('leaf_brightness',Sdf.ValueTypeNames.Float,1.,'Leaf brightness'),
        ('leaf_darkening',Sdf.ValueTypeNames.Float,0.,'Leaf darkening')):
        attr=material.CreateInput(name,kind).GetAttr();attr.Set(default)
        attr.SetDisplayName(label);attr.SetDisplayGroup('Leaf Base Color')
        attr.SetDocumentation('Tint multiplies the source color. Brightness: 1 preserves, below 1 darkens, above 1 brightens. Darkening: 0 preserves, 1 makes black. Keep this extension enabled while editing; save afterward.')
        attr.SetCustomDataByKey(PREVIEW_KEY,str(base_input.GetAttr().GetPath()))
    target=base_input.GetAttr()
    if isinstance(value,tuple):
        target.SetCustomDataByKey('unreal:leafOriginalColor',Gf.Vec3f(*value))
    else:
        target.SetCustomDataByKey('unreal:leafOriginalScale',Gf.Vec4f(*value.scale))
        target.SetCustomDataByKey('unreal:leafOriginalBias',Gf.Vec4f(*value.bias))


def update_preview(stage,path):
    from pxr import Gf
    target=stage.GetAttributeAtPath(path)
    if not target:return
    prim=target.GetPrim()
    material=prim if prim.GetTypeName()=='Material' else prim.GetParent()
    tint=material.GetAttribute('inputs:leaf_tint').Get()
    brightness=material.GetAttribute('inputs:leaf_brightness').Get()
    darkening=material.GetAttribute('inputs:leaf_darkening').Get()
    if tint is None or brightness is None or darkening is None:return
    gain=[max(float(c),0)*max(float(brightness),0)*(1-min(max(float(darkening),0),1)) for c in tint]
    original=target.GetCustomDataByKey('unreal:leafOriginalColor')
    if original is not None:
        value=Gf.Vec3f(*[original[i]*gain[i] for i in range(3)])
        if target.Get()!=value:target.Set(value)
        return
    for field,key in (('scale','unreal:leafOriginalScale'),('bias','unreal:leafOriginalBias')):
        original=target.GetCustomDataByKey(key)
        if original is None:continue
        attr=prim.GetAttribute('inputs:'+field)
        value=Gf.Vec4f(*[original[i]*gain[i] for i in range(3)],original[3])
        if attr.Get()!=value:attr.Set(value)
