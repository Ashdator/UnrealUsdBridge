"""Local world projectors sharing clean base evaluators and shader definitions."""
from . import decal_regions

MAX_SHARED_DECALS=8


def prepare(data,root):
    audits,issues=decal_regions.prepare(data,root,max_prop_layers=MAX_SHARED_DECALS)
    # Keep source decal calculations frozen, but store placement as hidden
    # uniform values. Different boxes can reuse one MDL source definition.
    for _,_,frame in data.get('_decal_layers',{}).values():
        frame.update(fixed_transform=True,parameterized_transform=True,cull_texture_samples=True)
    used=set();receivers={}
    for instance in data['instances']+data.get('instancers',[]):
        for key in decal_regions.material_keys(instance):
            # Preserve empty/unresolved slots for the writer's audited fallback,
            # but do not treat them as authored materials or decal receivers.
            if key not in data['materials']:continue
            used.add(key);receivers.setdefault(key,[]).append(instance['source'])
        if instance.get('decal_sections'):
            merged={}
            for region in instance['decal_sections']:
                signature=(region['section'],region['slot'],region['material'])
                if signature not in merged:merged[signature]=dict(region,faces=[])
                merged[signature]['faces'].extend(region['faces'])
            instance['decal_sections']=list(merged.values())
    bases=set();groups=[]
    for key in sorted(used):
        mat=data['materials'][key]
        if not mat.get('decal_layers'):continue
        base=mat['decal_base_key'];bases.add(base)
        groups.append({'base':base,'material':key,'decals':mat['decal_layers'],
                       'receivers':receivers[key],'over_budget':len(mat['decal_layers'])>MAX_SHARED_DECALS})
    data['_shared_base_keys']=bases
    data['_author_material_keys']=used|bases
    data['world_decal_groups']=groups
    data['world_decal_slot_budget']=MAX_SHARED_DECALS
    return audits,issues
