"""Assign projections to actual surface regions and local foliage prototypes."""
import hashlib
import itertools
import json
import re
from collections import defaultdict
from .vegetation import exclusion_reason
MAX_BUNDLE_LAYERS = 8


def spatial_regions(points, triangles, face_masks, first_face, budget=MAX_BUNDLE_LAYERS, *, weights=None, waste_ratio=3):
    """Coarse spatial unions, without changing any triangle or dropping overlaps.

    A projector clips itself in world space. A nearby superset is safe, while
    grouping distant receivers together needlessly samples unrelated textures.
    Split a region only when its union is too large or mostly wasted work.
    """
    if not len(triangles):return []
    if not face_masks:
        return [([], list(range(first_face, first_face+len(triangles))))]
    masks=np.stack(face_masks,axis=0)
    centers=points[triangles].mean(axis=1)
    result=[]

    def visit(faces,depth=0):
        block=masks[:,faces]
        active=np.flatnonzero(block.any(axis=1)).tolist()
        if weights is None:
            average=float(block.sum())/max(len(faces),1)
        else:
            area=weights[faces]
            average=float((block.sum(axis=0)*area).sum())/max(float(area.sum()),1e-20)
        waste=len(active)>max(2,average*waste_ratio)
        identical=not len(active) or bool(np.all(block[active]==block[active,:1]))
        if identical or (len(active)<=budget and (not waste or len(faces)<=64)) or depth>=18:
            result.append((active,(faces+first_face).tolist()));return
        if len(faces)<=64:
            # A large triangle can genuinely intersect more than the target.
            # Preserve its full recipe; report the excess instead of clipping.
            groups=defaultdict(list)
            for face in faces:
                signature=tuple(np.flatnonzero(masks[:,face]).tolist())
                groups[signature].append(int(face)+first_face)
            result.extend((list(signature),ids) for signature,ids in groups.items());return
        extent=np.ptp(centers[faces],axis=0)
        axis=int(np.argmax(extent))
        ordered=faces[np.argsort(centers[faces,axis],kind='stable')]
        middle=len(ordered)//2
        visit(ordered[:middle],depth+1);visit(ordered[middle:],depth+1)

    visit(np.arange(len(triangles)))
    return result


def performance_regions(points, triangles, face_masks, first_face, budget, transform):
    """Accept at most four recipes when area-weighted projector work drops 40%.

    This estimates work from intersected triangle area, not camera-specific FPS.
    Small sections and genuine overlap stacks keep their original assignment.
    """
    if len(triangles)<128 or not 3<=len(face_masks)<=budget:return None
    world=points @ transform[:3,:3]+transform[3,:3]
    vertices=world[triangles]
    weights=np.linalg.norm(np.cross(vertices[:,1]-vertices[:,0],vertices[:,2]-vertices[:,0]),axis=1)
    total=float(weights.sum())
    # Source positions are Unreal centimeters. Ignore sections below four
    # square meters: the extra assignments rarely pay off on small props.
    if total<80000:return None
    coverage=float((np.stack(face_masks).sum(axis=0)*weights).sum())/total
    if coverage>len(face_masks)*0.55:return None
    candidate=spatial_regions(world,triangles,face_masks,first_face,budget,
                              weights=weights,waste_ratio=2)
    merged=defaultdict(list)
    for active,faces in candidate:merged[tuple(active)].extend(faces)
    if not 1<len(merged)<=4:return None
    after=sum(len(active)*float(weights[np.asarray(faces)-first_face].sum()) for active,faces in merged.items())
    before=len(face_masks)*total
    if after>before*0.60:return None
    return [(list(active),faces) for active,faces in merged.items()],1-after/before


def ground_asset(mesh):
    # Asset leaves, not project folders or material names, identify terrain props.
    if mesh.get('terrain') or mesh.get('landscape'):return True
    for field in ('source','name'):
        leaf=str(mesh.get(field,'')).rsplit('/',1)[-1].split('.',1)[0]
        leaf=re.sub(r'([a-z])([A-Z])',r'\1_\2',leaf)
        if set(re.findall(r'[a-z]+',leaf.lower())) & {'ground','terrain','landscape'}:return True
    return False
try:
    import numpy as np
except ModuleNotFoundError:
    # Isaac's standalone Python does not automatically activate Kit's bundled
    # scientific packages. Reuse the matching installation; no pip install.
    import sys
    from pathlib import Path
    from pxr import Usd
    archive=next(Path(Usd.__file__).resolve().parents[3].glob('omni.kit.pip_archive*/pip_prebundle'))
    sys.path.insert(0,str(archive))
    import numpy as np


def box_hits(bounds, matrices, inverse):
    corners=np.array(list(itertools.product(*bounds)),dtype=np.float64)
    transform=matrices @ inverse
    points=np.einsum('vj,njk->nvk',corners,transform[:,:3,:3])+transform[:,None,3,:3]
    return np.all(points.min(axis=1)<=1+1e-7,axis=1)&np.all(points.max(axis=1)>=-1-1e-7,axis=1)


def triangle_hits(points,triangles,transform):
    local=points @ transform[:3,:3]+transform[3,:3]
    vertices=local[triangles]
    broad=np.all(vertices.min(axis=1)<=1+1e-7,axis=1)&np.all(vertices.max(axis=1)>=-1-1e-7,axis=1)
    indices=np.flatnonzero(broad)
    if not len(indices):return broad
    v=vertices[indices]
    edges=np.stack((v[:,1]-v[:,0],v[:,2]-v[:,1],v[:,0]-v[:,2]),axis=1)
    normal=np.cross(edges[:,0],edges[:,1])
    inside=np.abs(np.einsum('ni,ni->n',normal,v[:,0]))<=np.abs(normal).sum(axis=1)+1e-7
    for edge in range(3):
        for axis in np.eye(3):
            cross=np.cross(edges[:,edge],axis)
            projection=np.einsum('nvi,ni->nv',v,cross)
            radius=np.abs(cross).sum(axis=1)+1e-7
            inside&=(projection.min(axis=1)<=radius)&(projection.max(axis=1)>=-radius)
    broad[indices]=inside
    return broad


def prepare(data,root,*,max_prop_layers=None):
    from .decals import projection,compose,response_channels
    from .mdl import compile_mdl
    definitions={k:v for k,v in data['materials'].items() if v.get('domain')=='decal'}
    audits=[];valid=[];issues=[]
    data['decal_controls']={};data['_decal_layers']={}
    for decal in sorted(data.get('decals',[]),key=lambda d:(d.get('sort_order',0),d['source'])):
        audit={'source':decal['source'],'name':decal.get('name','Decal'),'material':decal.get('material',''),
               'sort_order':decal.get('sort_order',0),'receivers':[],'issues':[],'status':'no_receivers'}
        audits.append(audit)
        if not decal.get('visible',True):audit['status']='hidden';continue
        try:
            definition=definitions[decal['material']];frame=projection(decal)
            probe=compose({'inputs':{}},[(decal,definition,frame)],('base_color','normal','roughness','metallic'))
            probe['issues']=definition.get('issues',[])
            _,problems=compile_mdl(probe,data['textures'])
            if problems:raise ValueError('; '.join(problems))
            inverse=np.linalg.inv(np.array(decal['matrix'],dtype=np.float64).reshape(4,4))
        except (KeyError,ValueError,np.linalg.LinAlgError) as exc:
            audit.update(status='unsupported',issues=[str(exc)])
            issues.append(f"{decal['source']}: decal unsupported: {exc}");continue
        valid.append((decal,definition,frame,inverse,audit))
        data['decal_controls'][decal['source']]=frame
        data['_decal_layers'][decal['source']]=(decal,definition,frame)
    variants={}
    whole_section_keys=set()
    def variant(base_key,selected,source):
        if not selected:return base_key
        base=data['materials'][base_key]
        signature=(base_key,tuple(valid[i][0]['source'] for i in selected))
        if signature not in variants:
            digest=hashlib.sha1(repr(signature).encode()).hexdigest()[:12]
            key=base_key+'_decals_'+digest
            # Recipes avoid retaining hundreds of copied expression trees.
            mat=dict(base)
            mat.update(decal_base_key=base_key,decal_layers=list(signature[1]),
                       name=base.get('name','Material')+'_Decals_'+digest[:6])
            data['materials'][key]=mat;variants[signature]=key
        for i in selected:
            audit=valid[i][4]
            if source not in audit['receivers']:audit['receivers'].append(source)
            audit['status']='projected'
        return variants[signature]
    groups=defaultdict(list)
    data['decal_receiver_exclusions']=[]
    data['ground_decal_regions']=[]
    data['performance_decal_regions']=[]
    for instance in data['instances']+data.get('instancers',[]):
        reason=exclusion_reason(data,instance)
        if reason:
            data['decal_receiver_exclusions'].append({
                'source':instance['source'],'name':instance.get('name',''),
                'mesh':instance['mesh'],'reason':reason,
                'source_receives_decals':instance.get('receives_decals',True),
            })
        elif valid and instance.get('receives_decals',True) and instance.get('visible',True):
            groups[instance['mesh']].append(instance)
    for mesh_key,instances in groups.items():
        mesh=json.loads((root/data['meshes'][mesh_key]['file']).read_text(encoding='utf-8-sig'))
        points=np.asarray(mesh['points'],dtype=np.float64)
        triangles=np.asarray(mesh['indices'],dtype=np.int64).reshape(-1,3)
        bounds=list(zip(points.min(axis=0),points.max(axis=0)))
        sections=mesh['sections'];landscape=bool(mesh.get('unified_landscape'))
        ground=ground_asset(data['meshes'][mesh_key]) or ground_asset(mesh);del mesh
        for instance in instances:
            component=np.asarray(instance['matrix'],dtype=np.float64).reshape(4,4)
            instanced='transforms' in instance
            matrices=np.asarray(instance['transforms'],dtype=np.float64).reshape(-1,4,4) @ component if instanced else component[None,:,:]
            if not len(matrices):continue
            hits=np.stack([box_hits(bounds,matrices,item[3]) for item in valid],axis=1)
            original=list(instance['materials'])
            prototypes=[];prototype_index={};indices=[]
            for placement,matrix in enumerate(matrices):
                materials=list(original);regions=[];needs_regions=False
                for section_index,section in enumerate(sections):
                    slot=section['slot'];start=section['first_face'];count=section['face_count']
                    base_key=original[slot] if slot<len(original) else None
                    base=data['materials'].get(base_key,{})
                    channels=response_channels(base.get('decal_response',1))
                    eligible=base and not base.get('translucent') and not base.get('issues') and base.get('domain')!='decal'
                    candidates=[i for i in np.flatnonzero(hits[placement]) if eligible and (set(valid[i][1].get('decal_channels',valid[i][1]['inputs'])) & (set(channels) | ({'emissive'} if channels else set())))]
                    face_masks=[];selected=[]
                    for i in candidates:
                        mask=triangle_hits(points,triangles[start:start+count],matrix @ valid[i][3])
                        if np.any(mask):selected.append(i);face_masks.append(mask)
                    ground_overload=ground and len(selected)>MAX_BUNDLE_LAYERS and not instanced
                    if ground_overload:
                        data['ground_decal_regions'].append({'source':instance['source'],'mesh':mesh_key,
                            'section':section_index,'decals':len(selected),'reason':'ground mesh with more than eight applicable decals'})
                    prop_overload=max_prop_layers is not None and len(selected)>max_prop_layers and not instanced
                    optimized=None
                    if max_prop_layers is not None and not (instanced or landscape or ground_overload or prop_overload):
                        optimized=performance_regions(points,triangles[start:start+count],face_masks,start,max_prop_layers,matrix)
                    if instanced or not (landscape or ground_overload or prop_overload or optimized):
                        if base_key is not None:
                            materials[slot]=variant(base_key,selected,instance['source'])
                            whole_section_keys.add(materials[slot])
                        # Every original section belongs in the complete face
                        # partition if any section later needs local regions.
                        if not instanced:
                            regions.append({'section':section_index,'slot':slot,
                                'material':materials[slot] if base_key is not None else '',
                                'faces':list(range(start,start+count))})
                        continue
                    if optimized:
                        face_groups,saving=optimized
                        data['performance_decal_regions'].append({'source':instance['source'],'section':section_index,
                            'decals':len(selected),'regions':len(face_groups),'estimated_area_work_reduction':saving})
                    else:
                        face_groups=spatial_regions(points,triangles[start:start+count],face_masks,start,
                                                    max_prop_layers or MAX_BUNDLE_LAYERS)
                    for local,faces in face_groups:
                        active=[selected[i] for i in local]
                        key=variant(base_key,active,instance['source']) if base_key is not None else ''
                        regions.append({'section':section_index,'slot':slot,'material':key,'faces':faces})
                        if len(face_groups)==1 and base_key is not None:materials[slot]=key
                    needs_regions|=len(face_groups)>1
                if instanced:
                    signature=tuple(materials)
                    if signature not in prototype_index:
                        prototype_index[signature]=len(prototypes);prototypes.append({'materials':materials})
                    indices.append(prototype_index[signature])
                else:
                    instance['materials']=materials
                    if needs_regions:instance['decal_sections']=regions
            if instanced and any(p['materials']!=original for p in prototypes):
                instance['decal_prototypes']=prototypes;instance['decal_proto_indices']=indices
                instance['materials']=prototypes[0]['materials']
    # Equal recipes already share a variant. Do not pad a material with decals
    # from distant receivers merely to reduce its Material prim count.
    for key in definitions:del data['materials'][key]
    return audits,issues

def resolve(data,material):
    if not material.get('decal_layers'):return material
    from .decals import compose,response_channels
    base=data['materials'][material['decal_base_key']]
    result=compose(base,[data['_decal_layers'][key] for key in material['decal_layers']],response_channels(base.get('decal_response',1)))
    result.update(name=material['name'],decal_base_key=material['decal_base_key'])
    return result


def material_keys(instance):
    keys=set(instance['materials'])
    keys.update(section['material'] for section in instance.get('decal_sections',[]))
    for prototype in instance.get('decal_prototypes',[]):keys.update(prototype['materials'])
    return keys
