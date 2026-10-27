"""Find shared decal controls from a selected material's existing shader links."""
from pxr import Sdf, Usd, UsdShade
from .decal_controls import SOURCE_KEY


def label(prim):
    return prim.GetDisplayName() or prim.GetName()


def material_ancestor(prim):
    if str(prim.GetPath()).startswith('/World/Decals/'):return None
    while prim and not prim.IsPseudoRoot():
        if prim.IsA(UsdShade.Material):return prim
        prim=prim.GetParent()
    return None


def material_decals(material):
    """Use 0.5.5 shader metadata, including controls deleted by the user."""
    stage=material.GetStage();found={}
    for prim in Usd.PrimRange(material):
        for attr in prim.GetAttributes():
            source=attr.GetCustomDataByKey(SOURCE_KEY)
            if not source or not str(source).endswith('.inputs:amount'):continue
            try:path=Sdf.Path(str(source)).GetPrimPath()
            except Exception:continue
            control=stage.GetPrimAtPath(path)
            valid=bool(control and control.HasAttribute('inputs:amount'))
            display=(label(control) if valid else
                     attr.GetDisplayName().removesuffix(' intensity') or path.name)
            row=found.setdefault(str(path),{'path':str(path),'label':display,
                                           'available':valid,'parameters':[]})
            row['parameters'].append(str(attr.GetPath()))
    return [found[k] for k in sorted(found)]


def selection_links(stage,paths):
    if not stage:return None
    materials={}
    for path in paths:
        prim=stage.GetPrimAtPath(path)
        if not prim:continue
        if prim.GetPath().HasPrefix('/World/Decals'):continue
        material=material_ancestor(prim)
        if material:
            key=str(material.GetPath())
            decals=material_decals(material)
            base=material.GetCustomDataByKey('unreal:baseMaterial')
            if decals or base:materials[key]={'path':key,'label':label(material),'decals':decals,'base_material':base}
    if materials:return {'mode':'materials','materials':[materials[k] for k in sorted(materials)]}
    return None
