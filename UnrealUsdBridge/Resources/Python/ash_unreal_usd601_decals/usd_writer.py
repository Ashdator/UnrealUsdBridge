"""Author portable USD geometry, material networks and foliage PointInstancers."""
import hashlib
import json
import re
import math
import shutil
from pathlib import Path

from .graph import Constant, Sample, INPUTS, Unsupported, compile_material
from .mdl import compile_mdl
from .naming import asset_name, names, material_name
from .material_policy import main_normals
from . import omnipbr
from . import decals
from .mdl_sharing import canonical_program
from . import world_decals
from . import decal_maps
from . import emission
from . import material_metadata
from . import shared_base
from . import water_policy
from . import basic_surface
from . import leaf_controls
from . import repeated_meshes
from .mesh_json import load_mesh
from .manifest_io import update_texture_paths


def identifier(source):
    name=re.sub(r"[^A-Za-z0-9_]","_",source.rsplit("/",1)[-1])[:64]
    return "a_"+name+"_"+hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]


def display_name(prim,name):
    if hasattr(prim, "SetDisplayName"): prim.SetDisplayName(name)
    prim.SetCustomDataByKey("unreal:displayName",name)


def contained_file(root, relative):
    path = (root / relative).resolve()
    if root.resolve() not in path.parents or not path.is_file():
        raise ValueError(f"Missing asset or path outside conversion folder: {relative}")
    return path


def convert(manifest_path, *, allow_partial=False, preview_fallback=False, include_decals=True, hide_unsupported_sky=False, export_cameras=True, export_lights=True, shared_world_decals=True, progress=lambda _:None):
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, UsdLux, Vt

    root = Path(manifest_path).resolve().parent
    data = json.loads(Path(manifest_path).read_text(encoding="utf-8-sig"))
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported bridge manifest version")
    # Preserve the compact extraction before adding material variants. It is
    # enough to reproduce conversion and avoids a huge expanded JSON snapshot.
    source_manifest=root/'source-manifest.json'
    if not source_manifest.exists(): shutil.copyfile(manifest_path,source_manifest)
    report = {"status":"checking", "map":data.get("map"), "material_baking":False,
              "issues":list(data.get("issues", [])), "notes":list(data.get("notes", [])),
              "materials":{}, "counts":{}}
    report['export_cameras']=bool(export_cameras); report['export_lights']=bool(export_lights)
    report['source_cameras']=len(data.get('cameras',[])); report['source_lights']=len(data.get('lights',[]))
    if not export_cameras:
        data['cameras']=[];report['notes'].append('Camera export disabled by user.')
    if not export_lights:
        data['lights']=[];report['notes'].append('Light export disabled by user.')
    source_decals=len(data.get('decals',[]))
    report['excluded_water_materials']=[]
    for key,source_material in data['materials'].items():
        if water_policy.excluded(source_material):
            report['excluded_water_materials'].append({'key':key,'source':source_material.get('source',''),'name':source_material.get('name',key)})
            source_material.update(excluded_water=True,inputs={},issues=[],decal_response=0,translucent=True)
        else:
            fallback=basic_surface.recover(source_material,data['textures'])
            if fallback is not None:
                data['materials'][key]=fallback
            else:emission.prepare(source_material)
    leaf_controls.mark(data)
    report['include_decals']=include_decals
    report['export_skeletal_meshes']=bool(data.get('export_skeletal_meshes',False))
    report['hide_unsupported_sky']=hide_unsupported_sky;report['hidden_unsupported_sky']=[]
    if not include_decals:
        data['decals']=[]
        report['notes'].append(f'Decals disabled by user: {source_decals} source projectors omitted; base materials and original geometry retained.')
    progress('Preparing decal receivers' if include_decals else 'Decals disabled; preparing base materials')
    report['decal_map_precomputation'] = decal_maps.prepare(data, root, progress) if include_decals and shared_world_decals else []
    report['decal_maps_baked'] = any(item['status'] == 'precomputed' for item in report['decal_map_precomputation'])
    report['receiver_material_baking'] = False
    report['material_baking'] = report['decal_maps_baked']
    report['material_baking_scope'] = 'fixed_decal_maps_only' if report['decal_maps_baked'] else 'none'
    if report['decal_maps_baked']:
        report['notes'].append('Fixed UV-only decal calculations were precomputed into reusable 16-bit maps. Receiver materials and decal intensity remain editable; simple source normal/texture maps are preserved. Context-dependent decal graphs remain translated and are reported.')
    report['decals'], decal_issues = (world_decals.prepare if shared_world_decals else decals.prepare)(data,root)
    report['decal_mode']='shared_base_local_world_projection' if shared_world_decals else 'material_blends'
    report['world_decal_groups']=data.get('world_decal_groups',[])
    report['world_decal_slot_budget']=data.get('world_decal_slot_budget')
    report['decal_receiver_exclusions']=data.get('decal_receiver_exclusions',[])
    report['ground_decal_regions']=data.get('ground_decal_regions',[])
    report['performance_decal_regions']=data.get('performance_decal_regions',[])
    report['decal_sampling_policy']='Projected texture lookups guarded by projector footprint and intensity; bounded area-based receiver partitions' if shared_world_decals else 'Original material blends'
    report['vegetation_decals_excluded']=True
    if include_decals:
        report['notes'].append('Vegetation is excluded from projected decals, including individually placed plants and foliage instances. Source geometry, base layers and Receives Decals settings remain unchanged. See decal_receiver_exclusions for classifications.')
    report['issues'].extend(decal_issues)

    def save_report():
        (root / "conversion-report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")

    # Keep only the requested surface channels, even for older manifests.
    for mat in data["materials"].values():
        mat["inputs"]={k:v for k,v in mat.get("inputs",{}).items() if k in INPUTS}
    # Instancing does not imply a foliage material: rocks and props can also be
    # painted by Unreal's foliage tool. Use the extracted shading-model flag.
    referenced=set()
    def collect(node):
        if isinstance(node,dict):
            if node.get("op")=="texture": referenced.add(node["texture"])
            for child in node.values(): collect(child)
        elif isinstance(node,list):
            for child in node: collect(child)
    for mat in data["materials"].values():
        collect(mat.get("inputs",{})); collect(mat.get('decal_world_normal',{}))
    for _,definition,_ in data.get('_decal_layers',{}).values(): collect(definition.get('inputs',{}))
    data["textures"]={key:value for key,value in data["textures"].items() if key in referenced}
    authored_keys=data.get('_author_material_keys',set(data['materials']))
    authored_materials={key:mat for key,mat in data['materials'].items() if key in authored_keys}
    material_names=names({key:material_name(mat,data["textures"]) for key,mat in authored_materials.items()})
    mesh_names=names({key:asset_name(ref.get("source",key)) for key,ref in data["meshes"].items()})
    texture_names=names({key:asset_name(ref["source"]) if ref.get("source") else Path(ref["file"]).stem for key,ref in data["textures"].items()})
    # Extraction runs have unique folders; preserve original images byte for byte.
    for key,ref in data["textures"].items():
        original=(root/ref["file"]).resolve()
        if root.resolve() not in original.parents:
            raise ValueError(f'Texture path outside conversion folder: {ref["file"]}')
        relative="textures/"+texture_names[key]+original.suffix
        target=root/relative
        if not original.is_file():
            if not target.is_file():raise ValueError(f'Missing texture: {ref["file"]}')
            progress(f'Reusing previously renamed texture: {target.name}')
        elif target != original:
            if target.exists():raise FileExistsError(str(target))
            original.rename(target)
        ref["file"]=relative
    # Preserve all source texture records (including unused source maps).
    # Stream replacement instead of parsing the enormous placement arrays twice.
    progress('Updating texture paths without reloading placement arrays')
    from .manifest_io import texture_span
    start,end=texture_span(source_manifest)
    with source_manifest.open('rb') as source:
        source.seek(start);source_textures=json.loads(source.read(end-start))
    for key,ref in data['textures'].items():
        if key in source_textures:source_textures[key]['file']=ref['file']
    update_texture_paths(source_manifest,manifest_path,source_textures,span=(start,end))
    del source_textures
    report.update(target_isaac="6.0.1",meters_per_unit=1.0,extension_version="0.6.6",host="Unreal Editor",
                  visibility_filter=data.get('visibility_filter',{'exclude_hidden':False}),
                  extractor_version=data.get('extractor_version'),
                  extractor_patch=data.get('extractor_patch'),
                  extension_patch="2026-10-14-repeated-static-point-instancers",
                  geometry_policy="Original high-resolution mesh description where available, otherwise original LOD0. No Nanite render fallback or triangle reduction.",
                  material_profile="OmniPBR foliage; USD Preview Surface simple objects; MDL complex graphs and decal receivers. No AO or subsurface.",
                  normal_policy="Source main normal maps, strength 1; bypass flatten/detail blends; preserve layer masks and UVs")
    report['emissive_policy']='Unreal Emissive Color, HDR values, textures, source UVs and supported calculations retained; no emitter-material baking. Unlit surfaces emit without a reflective lobe.'
    report['specular_policy']='0.5.15 behavior restored: the bridge does not author or route a custom Specular workflow. Standard USD Preview Surface controls remain available in Kit, and MDL uses the fixed legacy dielectric lobe.'
    if preview_fallback:
        report["notes"].append("The legacy preview_fallback argument is ignored. Each material now has one surface context.")
    compiled = {}
    mdl_compiled = {}
    omni_compiled = {}
    prepared = {}
    for key, mat in authored_materials.items():
        progress(f"Translating material {len(compiled)+1}/{len(authored_materials)}")
        if mat.get('excluded_water'):
            prepared[key]=mat;compiled[key]=({},[]);mdl_compiled[key]=None;omni_compiled[key]=None
            report['materials'][key]={'name':material_names[key],'source':mat.get('source',''),
                'backend':'ExcludedWater','issues':[],'preview_limitations':[],
                'backend_reason':'Water conversion excluded by user; visible magenta placeholder retains geometry for manual replacement.'}
            continue
        try:shared_material=shared_base.material(data,mat)
        except Unsupported:
            # Preserve partial-preview diagnostics for an unsupported receiver
            # rather than letting creation of its shared evaluator abort the run.
            shared_material=None
        material, normal_notes = main_normals(shared_material if shared_material is not None else decals.resolve(data,mat))
        material.pop('foliage_instance',None)
        prepared[key] = mat if mat.get('decal_layers') else material
        inputs, preview_issues = compile_material(material)
        if material.get('normal_space','tangent')=='world':
            preview_issues.append('World-space normals require MDL')
        mdl = None; omni = None
        if material.get('decal_layers') or material.get('unlit') or material.get('shared_base_shader'):
            mdl, issues = compile_mdl(material,data['textures'])
            backend = 'MDL'
        elif material.get('foliage'):
            omni, issues = omnipbr.compile_omnipbr(material,data['textures'])
            backend = 'OmniPBR'
            if issues:
                mdl, issues = compile_mdl(material,data['textures'])
                omni=None;backend='MDL'
        elif not preview_issues:
            issues = []; backend = 'UsdPreviewSurface'
        else:
            mdl, issues = compile_mdl(material,data['textures'])
            backend = 'MDL'
        if mdl is not None and not issues:mdl=canonical_program(mdl)
        omni_compiled[key] = omni
        mdl_compiled[key]=mdl
        programs = ([mdl] if mdl else []) + (list(omni['functions'].values()) if omni else [])
        for program in programs:
            for parameter in program["parameters"].values():
                if parameter["type"]=="texture_2d":
                    try: contained_file(root,parameter["file"])
                    except ValueError as exc: issues.append(str(exc))
        samples = list(inputs.values()) if backend=='UsdPreviewSurface' else ([omni['normal']] if omni and omni['normal'] else [])
        for value in samples:
            if isinstance(value, Sample):
                try:
                    contained_file(root,data["textures"][value.texture]["file"])
                except (ValueError,KeyError) as exc:
                    issues.append(str(exc))
        compiled[key] = (inputs,issues)
        report["materials"][key] = {"source":mat.get("source",""),"issues":issues,"preview_limitations":preview_issues,
                                    "name":material_names[key],"backend":backend if not issues else 'Unsupported',
                                    "normal_changes":normal_notes,
                                    "emissive":emission.uses_emission(material),
                                    "unlit":bool(material.get('unlit')),
                                    "basic_surface_fallback":material.get('basic_surface_fallback'),
                                    "leaf_surface":bool(material.get('leaf_surface')),
                                    "mdl_uv_controls":[p['label'] for p in mdl['parameters'].values() if p.get('uv_control')] if mdl else [],
                                    "decal_layers":material.get('decal_layers',[]),
                                    "backend_reason":"Projected decal blend with independent coordinates" if material.get('decal_layers') else "Unreal Unlit emission without reflected-light scattering" if material.get('unlit') else "Unreal foliage shading model" if material.get('foliage') else "Complete PBR graph fits USD Preview Surface" if backend=='UsdPreviewSurface' else "Complex graph retained without baking"}
    mesh_data = {}
    report["geometry"] = {}
    for index, (key, ref) in enumerate(data["meshes"].items(), 1):
        progress(f"Validating geometry {index}/{len(data['meshes'])}: {ref.get('source',key)}")
        mesh = load_mesh(contained_file(root,ref["file"]))
        indices, points = mesh["indices"], mesh["points"]
        if len(indices)%3 or any(i<0 or i>=len(points) for i in indices):
            raise ValueError(f"Invalid mesh topology: {key}")
        if len(mesh["normals"]) != len(points) or any(len(channel)!=len(points) for channel in mesh["uvs"]):
            raise ValueError(f"Invalid mesh normals or UV count: {key}")
        mode=mesh.get("geometry_source", "landscape" if mesh.get("unified_landscape") else "legacy_unspecified")
        if (mode.startswith("original_") or mode == 'spline_deformed_original') and mesh.get("source_triangles") != len(indices)//3:
            raise ValueError(f"Original mesh triangle count changed during extraction: {key}")
        report["geometry"][key]={"source":mesh.get("source",key),"geometry_source":mode,
                                 "vertices":len(points),"triangles":len(indices)//3,
                                 "source_triangles":mesh.get("source_triangles"),
                                 "render_lod0_triangles":mesh.get("render_lod0_triangles"),"repaired_uv_coordinates":mesh.get("repaired_uv_coordinates",0)}
        if mesh.get('spline_component'):
            report['geometry'][key].update(spline_component=mesh['spline_component'],
                                          source_mesh=mesh.get('source_mesh'),
                                          spline_reversed_winding=mesh.get('spline_reversed_winding',False))
        mesh_data[key]={'source':mesh.get('source',key),'sections':mesh['sections'],
                        'point_count':len(points),'uv_count':len(mesh['uvs']),
                        'unified_landscape':mesh.get('unified_landscape',False)}
    if mesh_data: del mesh,points,indices
    mesh_names=names({key:asset_name(mesh.get("source",key)) for key,mesh in mesh_data.items()})
    for instance in data["instances"] + data.get("instancers",[]):
        mesh = mesh_data[instance["mesh"]]
        for section in mesh["sections"]:
            slot = section["slot"]
            if slot >= len(instance["materials"]) or instance["materials"][slot] not in compiled:
                report["issues"].append(f"{instance['source']}: missing material in slot {slot}")
                continue
            mat_key=instance['materials'][slot]
            for value in (compiled[mat_key][0].values() if report['materials'][mat_key]['backend']=='UsdPreviewSurface' else []):
                if isinstance(value,Sample) and value.uv.channel >= mesh['uv_count']:
                    report["issues"].append(f"{instance['source']}: material requests absent UV channel {value.uv.channel}")
            mdl=mdl_compiled[instance["materials"][slot]]
            if mdl and any(channel>=mesh['uv_count'] for channel in mdl["uv_channels"]):
                report["issues"].append(f"{instance['source']}: MDL material requests an absent UV channel")
            omni=omni_compiled[mat_key]
            if omni and any(channel>=mesh['uv_count'] for channel in omni['uv_channels']):
                report['issues'].append(f"{instance['source']}: OmniPBR material requests an absent UV channel")
        for mat_key in decals.material_keys(instance):
            if mat_key not in compiled:continue
            program=mdl_compiled[mat_key]
            if program and any(channel>=mesh['uv_count'] for channel in program['uv_channels']):
                report['issues'].append(f"{instance['source']}: decal material requests an absent UV channel")
    issue_count = len(report["issues"]) + sum(len(item[1]) for item in compiled.values())
    report["issue_count"] = issue_count
    if issue_count and not allow_partial:
        report["status"]="blocked"; save_report()
        raise ValueError(f"{issue_count} unsupported features. See conversion-report.json. Enable partial preview to inspect supported content.")

    stage_path=root/"Scene.usdc"
    if stage_path.exists():
        raise FileExistsError("Scene.usdc already exists; choose a fresh conversion folder")
    geometry_path=root/"Geometry.usdc"
    geometry=Usd.Stage.CreateNew(str(geometry_path))
    UsdGeom.SetStageUpAxis(geometry,UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(geometry,1.0)
    UsdGeom.Scope.Define(geometry,"/Meshes")
    for index,key in enumerate(mesh_data):
        mesh=load_mesh(contained_file(root,data['meshes'][key]['file']))
        progress(f"Writing geometry {index+1}/{len(mesh_data)}")
        target=UsdGeom.Mesh.Define(geometry,f"/Meshes/{mesh_names[key]}")
        points=[Gf.Vec3f(p[0]*0.01,-p[1]*0.01,p[2]*0.01) for p in mesh["points"]]
        display_name(target.GetPrim(),mesh_names[key])
        target.GetPrim().SetCustomDataByKey("unreal:source",data["meshes"][key].get("source",mesh.get("source","")))
        if mesh.get("geometry_source"):
            target.GetPrim().SetCustomDataByKey("unreal:geometrySource",mesh["geometry_source"])
        if mesh.get('spline_component'):
            target.GetPrim().SetCustomDataByKey('unreal:splineComponent',mesh['spline_component'])
            target.GetPrim().SetCustomDataByKey('unreal:splineSourceMesh',mesh.get('source_mesh',''))
        target.CreatePointsAttr(points)
        # Unreal's extracted triangles are clockwise relative to its vertex
        # normals. Reflecting Y converts that to USD's right-handed winding.
        # Reversing indices as well would put the front faces opposite normals.
        indices=mesh["indices"]
        target.CreateFaceVertexIndicesAttr(indices)
        target.CreateFaceVertexCountsAttr([3]*(len(indices)//3))
        target.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
        target.CreateOrientationAttr(UsdGeom.Tokens.rightHanded)
        target.CreateNormalsAttr([Gf.Vec3f(p[0],-p[1],p[2]) for p in mesh["normals"]])
        target.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
        target.CreateExtentAttr(UsdGeom.PointBased.ComputeExtent(points))
        for channel,uv in enumerate(mesh["uvs"]):
            name="st" if channel==0 else f"st{channel}"
            UsdGeom.PrimvarsAPI(target).CreatePrimvar(name,Sdf.ValueTypeNames.TexCoord2fArray,UsdGeom.Tokens.vertex).Set([Gf.Vec2f(p[0],1-p[1]) for p in uv])
        if mesh.get("colors"):
            UsdGeom.PrimvarsAPI(target).CreatePrimvar("unreal_vertex_color",Sdf.ValueTypeNames.Float4Array,UsdGeom.Tokens.vertex).Set([Gf.Vec4f(*p) for p in mesh["colors"]])
        binding=UsdShade.MaterialBindingAPI.Apply(target.GetPrim())
        if mesh.get('unified_landscape'):
            if len(mesh['sections'])!=1 or mesh['sections'][0]['slot']!=0 or mesh['sections'][0]['first_face']!=0 or mesh['sections'][0]['face_count']!=len(indices)//3:
                raise ValueError('Unified landscape requires one material covering the entire mesh')
            target.GetPrim().SetCustomDataByKey('unreal:landscapeComponentCount',len(mesh.get('landscape_components',[])))
            continue
        for section_index,section in enumerate(mesh["sections"]):
            start,count=section["first_face"],section["face_count"]
            if start<0 or start+count>len(indices)//3:
                raise ValueError("Mesh section is outside face range")
            binding.CreateMaterialBindSubset(f"section_{section_index}",list(range(start,start+count)))
        binding.SetMaterialBindSubsetsFamilyType(UsdGeom.Tokens.nonOverlapping)
    geometry.GetRootLayer().Save()
    if mesh_data: del mesh,points,indices
    # Object definitions live in the default root editing layer. Binary storage
    # keeps data compact without putting editable objects behind a sublayer.
    stage=Usd.Stage.CreateNew(str(stage_path))
    UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage,1.0)
    world=UsdGeom.Xform.Define(stage,"/World")
    stage.SetDefaultPrim(world.GetPrim())
    UsdGeom.Scope.Define(stage,"/World/Looks")
    materials={}
    projection_inputs={}
    control_names=names({k:v['label'] for k,v in data.get('decal_controls',{}).items()})
    for key,frame in data.get('decal_controls',{}).items():
        control=UsdShade.NodeGraph.Define(stage,'/World/Decals/'+control_names[key])
        display_name(control.GetPrim(),frame['label'])
        control.GetPrim().SetCustomDataByKey('unreal:source',key)
        control.GetPrim().SetCustomDataByKey('unreal:decalNote','Decal intensity only. Projection, textures and source parameters are fixed from Unreal. Keep this extension enabled for shared intensity edits; save afterward.')
        inp=control.CreateInput('amount',Sdf.ValueTypeNames.Float)
        inp.Set(1.0);inp.GetAttr().SetDisplayName('Decal intensity')
        projection_inputs[key,'amount']=inp

    def shader_input(shader,name,type_name,value):
        return shader.CreateInput(name,type_name).Set(value)

    def make_material(key,mat,inputs,issues):
        material=UsdShade.Material.Define(stage,f"/World/Looks/{material_names.get(key,key)}")
        display_name(material.GetPrim(),mat.get("name",key))
        material.GetPrim().SetCustomDataByKey("unreal:source",mat.get("source",""))
        material.GetPrim().SetCustomDataByKey('unreal:materialBackend',report['materials'].get(key,{}).get('backend','Unsupported'))
        notes=report['materials'].get(key,{}).get('normal_changes',[])
        if notes: material.GetPrim().SetCustomDataByKey('unreal:normalChanges','\n'.join(notes))
        # Exactly one surface backend. Never author an incomplete Universal fallback.
        if not issues and (mdl_compiled.get(key) or omni_compiled.get(key)):
            return material
        shader=UsdShade.Shader.Define(stage,material.GetPath().AppendChild("Surface"))
        shader.CreateIdAttr("UsdPreviewSurface")
        material.CreateSurfaceOutput().ConnectToSource(shader.CreateOutput("surface",Sdf.ValueTypeNames.Token))
        if mat.get('excluded_water'):
            shader_input(shader,'diffuseColor',Sdf.ValueTypeNames.Color3f,Gf.Vec3f(1,0,1))
            shader_input(shader,'opacity',Sdf.ValueTypeNames.Float,1.0)
            material.GetPrim().SetCustomDataByKey('unreal:excludedWater',True)
            return material
        if issues:
            shader_input(shader,"diffuseColor",Sdf.ValueTypeNames.Color3f,Gf.Vec3f(1,0,1))
            material.GetPrim().SetCustomDataByKey("unreal:translationIssues","\n".join(issues))
            return material
        if mat.get("opacity_threshold") is not None:
            shader_input(shader,"opacityThreshold",Sdf.ValueTypeNames.Float,float(mat["opacity_threshold"]))
        if mat.get('unlit'):
            shader_input(shader,'useSpecularWorkflow',Sdf.ValueTypeNames.Int,1)
            shader_input(shader,'specularColor',Sdf.ValueTypeNames.Color3f,Gf.Vec3f(0))
        for name,value in inputs.items():
            if name in ("opacity","metallic") and name not in mat.get("inputs",{}): continue
            usd_name,width,_=INPUTS[name]
            type_name = Sdf.ValueTypeNames.Normal3f if name=="normal" else Sdf.ValueTypeNames.Color3f if width==3 else Sdf.ValueTypeNames.Float
            dest=shader.CreateInput(usd_name,type_name)
            if isinstance(value,Constant):
                interface=material.CreateInput(usd_name,type_name)
                interface.Set(Gf.Vec3f(*value.value) if width==3 else value.value[0])
                if name=='emissive':
                    interface.GetAttr().SetDisplayName('Emissive color (linear HDR)')
                    interface.GetAttr().SetDisplayGroup('Emission')
                dest.ConnectToSource(interface)
                if name=='base_color' and mat.get('leaf_surface'):
                    leaf_controls.author_preview(material,shader,interface,value.value)
                continue
            texture=UsdShade.Shader.Define(stage,material.GetPath().AppendChild(name+"_texture"))
            texture.CreateIdAttr("UsdUVTexture")
            file_input=material.CreateInput(name+"_texture",Sdf.ValueTypeNames.Asset)
            file_input.Set(Sdf.AssetPath("./"+data["textures"][value.texture]["file"]))
            texture.CreateInput("file",Sdf.ValueTypeNames.Asset).ConnectToSource(file_input)
            file_input.GetAttr().SetColorSpace(value.color_space)
            texture.GetInput('file').GetAttr().SetColorSpace(value.color_space)
            shader_input(texture,"sourceColorSpace",Sdf.ValueTypeNames.Token,value.color_space)
            shader_input(texture,"wrapS",Sdf.ValueTypeNames.Token,value.wrap_s)
            shader_input(texture,"wrapT",Sdf.ValueTypeNames.Token,value.wrap_t)
            shader_input(texture,"scale",Sdf.ValueTypeNames.Float4,Gf.Vec4f(*value.scale))
            shader_input(texture,"bias",Sdf.ValueTypeNames.Float4,Gf.Vec4f(*value.bias))
            if name=='base_color' and mat.get('leaf_surface'):
                leaf_controls.author_preview(material,shader,texture.GetInput('scale'),value)
            if name=='emissive':
                # USD Preview Surface has no portable scalar multiply node.
                # Expose its exact affine RGB gain/offset through UsdUVTexture.
                for field, vector in (('scale',value.scale),('bias',value.bias)):
                    interface=material.CreateInput('emissive_'+field,Sdf.ValueTypeNames.Float4)
                    interface.Set(Gf.Vec4f(*vector))
                    interface.GetAttr().SetDisplayName('Emissive RGB gain' if field=='scale' else 'Emissive RGB offset')
                    interface.GetAttr().SetDisplayGroup('Emission')
                    texture.GetInput(field).ConnectToSource(interface)
                file_input.GetAttr().SetDisplayGroup('Emission')
            reader=UsdShade.Shader.Define(stage,material.GetPath().AppendChild(name+"_uv"))
            reader.CreateIdAttr("UsdPrimvarReader_float2")
            shader_input(reader,"varname",Sdf.ValueTypeNames.String,"st" if value.uv.channel==0 else f"st{value.uv.channel}")
            transform=UsdShade.Shader.Define(stage,material.GetPath().AppendChild(name+"_tiling"))
            transform.CreateIdAttr("UsdTransform2d")
            transform.CreateInput("in",Sdf.ValueTypeNames.Float2).ConnectToSource(reader.CreateOutput("result",Sdf.ValueTypeNames.Float2))
            # Conjugate the Unreal UV transform by the V-flip: F * T * F.
            scale,offset=value.uv.scale,value.uv.offset
            for field,vector in (("scale",scale),("translation",(offset[0],1-scale[1]-offset[1]))):
                interface=material.CreateInput(name+"_uv_"+field,Sdf.ValueTypeNames.Float2)
                interface.Set(Gf.Vec2f(*vector))
                if mat.get('leaf_surface'):interface.GetAttr().SetHidden(True)
                if name=='emissive': interface.GetAttr().SetDisplayGroup('Emission')
                transform_input=transform.CreateInput(field,Sdf.ValueTypeNames.Float2)
                transform_input.ConnectToSource(interface)
                if mat.get('leaf_surface'):transform_input.GetAttr().SetHidden(True)
            texture.CreateInput("st",Sdf.ValueTypeNames.Float2).ConnectToSource(transform.CreateOutput("result",Sdf.ValueTypeNames.Float2))
            output_name="rgb" if width==3 else "rgba"[value.channels[0]]
            output_type=Sdf.ValueTypeNames.Float3 if width==3 else Sdf.ValueTypeNames.Float
            dest.ConnectToSource(texture.CreateOutput(output_name,output_type))
        return material

    (root/"materials").mkdir(exist_ok=True)
    for base_key,program in data.get('_base_programs',{}).items():
        (root/'materials'/(program['module']+'.mdl')).write_text(program['source'],encoding='utf-8')
    report['base_shader_modules']={key:'materials/'+p['module']+'.mdl' for key,p in data.get('_base_programs',{}).items()}
    shared_programs={}
    for key,(inputs,issues) in compiled.items():
        progress(f"Writing material {len(materials)+1}/{len(compiled)}")
        material=make_material(key,prepared[key],inputs,issues)
        materials[key]=material
        if omni_compiled[key] is not None and not issues:
            omnipbr.author(stage,material,omni_compiled[key],prepared[key],data['textures'],root,material_names[key])
        mdl=mdl_compiled[key]
        if mdl is not None and not issues:
            signature=hashlib.sha256(mdl['source'].encode('utf-8')).hexdigest()
            relative=shared_programs.get(signature)
            if relative is None:
                relative=f'materials/Shared_{signature[:20]}.mdl'
                (root/relative).write_text(mdl['source'],encoding='utf-8')
                shared_programs[signature]=relative
            report['materials'][key]['mdl_definition']=relative
            shader=UsdShade.Shader.Define(stage,material.GetPath().AppendChild("MDL"))
            shader.CreateImplementationSourceAttr(UsdShade.Tokens.sourceAsset)
            shader.SetSourceAsset(Sdf.AssetPath("./"+relative),"mdl")
            shader.SetSourceAssetSubIdentifier("UnrealMaterial","mdl")
            output=shader.CreateOutput("out",Sdf.ValueTypeNames.Token)
            for context in ("surface","displacement","volume"):
                material.CreateOutput("mdl:"+context,Sdf.ValueTypeNames.Token).ConnectToSource(output)
            for param,p in mdl["parameters"].items():
                if p["type"]=="texture_2d":
                    attr=shader.CreateInput(param,Sdf.ValueTypeNames.Asset)
                    attr.Set(Sdf.AssetPath("./"+p["file"]))
                    attr.GetAttr().SetColorSpace(p["color_space"])
                elif p["type"]=="float":
                    attr=shader.CreateInput(param,Sdf.ValueTypeNames.Float)
                    attr.Set(float(p["value"]))
                elif p["type"]=="bool":
                    attr=shader.CreateInput(param,Sdf.ValueTypeNames.Bool)
                    attr.Set(bool(p["value"]))
                elif p["type"]=="float2":
                    attr=shader.CreateInput(param,Sdf.ValueTypeNames.Float2)
                    attr.Set(Gf.Vec2f(*p["value"]))
                elif p["type"]=="float3":
                    attr=shader.CreateInput(param,Sdf.ValueTypeNames.Color3f if p.get('leaf_color_control') else Sdf.ValueTypeNames.Float3)
                    attr.Set(Gf.Vec3f(*p["value"]))
                else:
                    attr=shader.CreateInput(param,Sdf.ValueTypeNames.Float4)
                    attr.Set(Gf.Vec4f(*p["value"]))
                attr.GetAttr().SetDisplayName(p["label"])
                attr.GetAttr().SetCustomDataByKey(material_metadata.IDENTITY,p['identity'])
                if p.get('emission_control'): attr.GetAttr().SetDisplayGroup('Emission')
                if p.get('uv_control'): attr.GetAttr().SetDisplayGroup('UV Coordinates')
                if p.get('leaf_color_control'):attr.GetAttr().SetDisplayGroup('Leaf Base Color')
                if p.get('hidden_control'):attr.GetAttr().SetHidden(True)
                if p.get('projection_id') or p.get('shared_projection_texture'):
                    attr.GetAttr().SetDisplayGroup('Decals')
                    attr.GetAttr().SetCustomDataByKey('uiorder',1000)
                if p.get('shared_projection_texture') or (p.get('projection_id') and p['projection_field']!='amount'):
                    attr.GetAttr().SetHidden(True)
                elif p.get('projection_id'):
                    shared=projection_inputs[p['projection_id'],p['projection_field']]
                    attr.GetAttr().SetCustomDataByKey('unreal:decalControl',str(shared.GetAttr().GetPath()))
                    attr.GetAttr().SetCustomDataByKey(material_metadata.DECAL_SOURCE,p['projection_id'])
    # One authoritative base input, stored as an ordinary renderer-visible MDL
    # value; regional copies are synchronized only when that input changes.
    for key,mat in authored_materials.items():
        if not mat.get('decal_layers') or key not in materials:continue
        base_key=mat['decal_base_key']
        master=materials.get(base_key)
        if not master:continue
        materials[key].GetPrim().SetCustomDataByKey(shared_base.BASE_MATERIAL,str(master.GetPath()))
        master_shader=stage.GetPrimAtPath(master.GetPath().AppendChild('MDL'))
        child=stage.GetPrimAtPath(materials[key].GetPath().AppendChild('MDL'))
        if not master_shader or not child:continue
        sources={a.GetCustomDataByKey(material_metadata.IDENTITY):a for a in master_shader.GetAttributes() if a.GetCustomDataByKey(material_metadata.IDENTITY)}
        for attr in child.GetAttributes():
            identity=attr.GetCustomDataByKey(material_metadata.IDENTITY)
            if identity and identity.startswith('base:') and identity in sources:
                attr.SetCustomDataByKey(shared_base.BASE_CONTROL,str(sources[identity].GetPath()))
                attr.SetHidden(True)
    missing=None

    def matrix(values):
        if len(values)!=16:
            raise ValueError("Expected a 4x4 transform matrix")
        signs=(1,-1,1,1)
        return Gf.Matrix4d(*[values[4*i+j]*signs[i]*signs[j]*(0.01 if i==3 and j<3 else 1.0) for i in range(4) for j in range(4)])

    def component_position(node):
        if isinstance(node,dict):
            return node.get('op')=='local_position' and node.get('origin')=='component' or any(component_position(v) for v in node.values())
        return isinstance(node,list) and any(component_position(v) for v in node)

    def place_mesh(path,instance):
        nonlocal missing
        prim=stage.DefinePrim(path,"Mesh")
        prim.GetReferences().AddReference("./Geometry.usdc",f"/Meshes/{mesh_names[instance['mesh']]}")
        prim.SetCustomDataByKey("unreal:source",instance["source"])
        double_sided=False
        if instance.get("colors"):
            if len(instance["colors"])!=mesh_data[instance["mesh"]]['point_count']:
                raise ValueError("Component vertex-color count does not match its mesh")
            UsdGeom.PrimvarsAPI(prim).CreatePrimvar("unreal_vertex_color",Sdf.ValueTypeNames.Float4Array,UsdGeom.Tokens.vertex).Set([Gf.Vec4f(*p) for p in instance["colors"]])
        if instance.get("object_position") and "transforms" not in instance:
            UsdGeom.PrimvarsAPI(prim).CreatePrimvar("unreal_object_position",Sdf.ValueTypeNames.Float3,UsdGeom.Tokens.constant).Set(Gf.Vec3f(*instance["object_position"]))
        for i,section in enumerate(mesh_data[instance["mesh"]]["sections"]):
            slot=section["slot"]
            key=instance["materials"][slot] if slot<len(instance["materials"]) else ""
            subset=prim if mesh_data[instance['mesh']].get('unified_landscape') else stage.GetPrimAtPath(path+f"/section_{i}")
            if key not in materials and missing is None:
                fallback="BridgeMissingMaterial"
                while fallback in material_names.values(): fallback+="_"
                missing=make_material(fallback,{"name":"Missing material"},{},["Missing material assignment"])
            UsdShade.MaterialBindingAPI.Apply(subset).Bind(materials.get(key,missing))
            double_sided=double_sided or data["materials"].get(key,{}).get("two_sided",False)
        if instance.get('decal_sections'):
            # Replace inherited full-section bindings with a complete partition.
            binding=UsdShade.MaterialBindingAPI.Apply(prim)
            binding.UnbindAllBindings()
            for i,_ in enumerate(mesh_data[instance['mesh']]['sections']):
                old=stage.GetPrimAtPath(path+f'/section_{i}')
                if old:old.SetActive(False)
            for i,region in enumerate(instance['decal_sections']):
                subset=binding.CreateMaterialBindSubset(f'decal_region_{i}',region['faces'])
                key=region['material']
                UsdShade.MaterialBindingAPI.Apply(subset.GetPrim()).Bind(materials.get(key,missing))
            binding.SetMaterialBindSubsetsFamilyType(UsdGeom.Tokens.partition)
        if shared_world_decals:
            report.setdefault('projected_coordinate_bytes',0)
        UsdGeom.Mesh(prim).CreateDoubleSidedAttr(double_sided)
        return prim

    def representable(values):
        original=matrix(values)
        transform=Gf.Transform(original)
        scale=Gf.Matrix4d(1);scale.SetScale(transform.GetScale())
        rotation=Gf.Matrix4d(1);rotation.SetRotate(transform.GetRotation())
        translation=Gf.Matrix4d(1);translation.SetTranslate(transform.GetTranslation())
        reconstructed=scale*rotation*translation
        return all(abs(original[i][j]-reconstructed[i][j]) <= 1e-6*max(1.0,abs(original[i][j]))
                   for i in range(4) for j in range(4))

    progress('Grouping repeated static meshes')
    ordinary,repeated,report['repeated_static_instancing']=repeated_meshes.prepare(data,mesh_data,representable)
    all_instancers=data.get('instancers',[])+repeated
    report['notes'].append('Repeated static mesh components are automatically exported as PointInstancers under /World/Instances. Shared mesh data and per-prototype materials, decal face regions and vertex paint are retained. Original source names and component paths are stored by instance index. Skeletal meshes, landscape components, sky meshes, non-SRT transforms and single placements remain ordinary objects. Instancing changes the Stage hierarchy; it does not simplify geometry or reduce leaf opacity overdraw.')
    if repeated:UsdGeom.Scope.Define(stage,'/World/Instances')
    object_names=names({i["source"]:i["name"] for i in ordinary})
    for index,instance in enumerate(ordinary):
        if index%100==0: progress(f"Placing object {index+1}/{len(ordinary)}")
        path="/World/Objects/"+object_names[instance["source"]]
        prim=place_mesh(path,instance)
        display_name(prim,instance["name"])
        UsdGeom.Xformable(prim).AddTransformOp().Set(matrix(instance["matrix"]))
        if not instance.get("visible",True):
            UsdGeom.Imageable(prim).MakeInvisible()
        sky_name=instance['name'].casefold().replace('_','')
        if hide_unsupported_sky and any(label in sky_name for label in ('skysphere','skydome')) and any(compiled.get(key,({},[]))[1] for key in instance['materials']):
            UsdGeom.Imageable(prim).MakeInvisible()
            report['hidden_unsupported_sky'].append(instance['source'])
            prim.SetCustomDataByKey('unreal:visibilityNote','Unsupported Unreal sky hidden by conversion option to avoid blocking environment lighting. Geometry retained; assign a supported sky material before making visible.')
    foliage_names=names({i["source"]:mesh_names[i["mesh"]]+"_"+i["name"] for i in all_instancers})
    instance_count=0;repeated_count=0
    for instance in all_instancers:
        is_repeated=instance.get('instance_source')=='bridge_repeated_static'
        progress(('Writing repeated meshes: ' if is_repeated else 'Writing foliage: ')+instance['name'])
        path=('/World/Instances/' if is_repeated else '/World/Foliage/')+foliage_names[instance["source"]]
        instancer=UsdGeom.PointInstancer.Define(stage,path)
        display_name(instancer.GetPrim(),instance["name"])
        instancer.GetPrim().SetCustomDataByKey("unreal:source",instance["source"])
        UsdGeom.Xformable(instancer).AddTransformOp().Set(matrix(instance["matrix"]))
        if not instance.get("visible",True):
            UsdGeom.Imageable(instancer).MakeInvisible()
        prototypes=instance.get('prototypes',instance.get('decal_prototypes',[{'materials':instance['materials']}]))
        targets=[]
        for index,prototype in enumerate(prototypes):
            proto=path+'/Prototypes/'+mesh_names[instance['mesh']]+('' if len(prototypes)==1 else f'_{index}')
            placement=dict(instance,**prototype)
            place_mesh(proto,placement);targets.append(Sdf.Path(proto))
        instancer.CreatePrototypesRel().SetTargets(targets)
        positions,orientations,scales=[],[],[]
        for flat in instance["transforms"]:
            transform=Gf.Transform(matrix(flat))
            rotation=transform.GetRotation().GetQuat()
            positions.append(Gf.Vec3f(transform.GetTranslation()))
            orientations.append(Gf.Quath(rotation.GetReal(),Gf.Vec3h(rotation.GetImaginary())))
            scales.append(Gf.Vec3f(transform.GetScale()))
        count=len(positions)
        if is_repeated:repeated_count+=count
        else:instance_count+=count
        instancer.CreateProtoIndicesAttr(instance.get('decal_proto_indices',[0]*count))
        instancer.CreatePositionsAttr(positions)
        instancer.CreateOrientationsAttr(orientations)
        instancer.CreateScalesAttr(scales)
        instancer.CreateIdsAttr(Vt.Int64Array(range(count)))
        if is_repeated:
            instancer.GetPrim().SetCustomDataByKey('unreal:instanceSources',Vt.StringArray(instance['source_components']))
            instancer.GetPrim().SetCustomDataByKey('unreal:instanceNames',Vt.StringArray(instance['source_names']))
        if not is_repeated and any(component_position(data['materials'].get(key,{})) for key in instance['materials']):
            # Relative instance transforms preserve the component-origin frame
            # even after moving the component in USD. Ordinary static objects
            # already use their component as MDL object space (identity defaults).
            relative=[matrix(flat) for flat in instance['transforms']]
            for column in range(3):
                UsdGeom.PrimvarsAPI(instancer).CreatePrimvar('unreal_instance_to_component_'+str(column),Sdf.ValueTypeNames.Float4Array,UsdGeom.Tokens.vertex).Set([Gf.Vec4f(m.GetColumn(column)) for m in relative])
        if "object_positions" in instance:
            if len(instance["object_positions"])!=count:
                raise ValueError("Foliage object positions must match the instance count")
            UsdGeom.PrimvarsAPI(instancer).CreatePrimvar("unreal_object_position",Sdf.ValueTypeNames.Float3Array,UsdGeom.Tokens.vertex).Set([Gf.Vec3f(*p) for p in instance["object_positions"]])
        if "random_values" in instance:
            if len(instance["random_values"])!=count:
                raise ValueError("Foliage random values must match the instance count")
            UsdGeom.PrimvarsAPI(instancer).CreatePrimvar("unreal_instance_random",Sdf.ValueTypeNames.FloatArray,UsdGeom.Tokens.vertex).Set(instance["random_values"])
    forward=Gf.Matrix4d(1)
    forward.SetRotate(Gf.Rotation(Gf.Vec3d(0,1,0),-90))
    for light in data.get("lights",[]):
        path="/World/Lights/"+identifier(light["source"])
        kind=light["kind"]
        if kind=="distant":
            target=UsdLux.DistantLight.Define(stage,path)
        elif kind=="rect":
            target=UsdLux.RectLight.Define(stage,path)
            target.CreateWidthAttr(light["width"]*0.01); target.CreateHeightAttr(light["height"]*0.01)
        else:
            target=UsdLux.SphereLight.Define(stage,path)
            target.CreateRadiusAttr(light["radius"]*0.01)
            if kind=="spot": UsdLux.ShapingAPI.Apply(target.GetPrim()).CreateShapingConeAngleAttr(light["angle"])
        target.CreateIntensityAttr(light["intensity"])
        target.CreateColorAttr(Gf.Vec3f(*light["color"]))
        UsdGeom.Xformable(target).AddTransformOp().Set(forward*matrix(light["matrix"]))
        if not light.get("visible",True): UsdGeom.Imageable(target).MakeInvisible()
    for camera in data.get("cameras",[]):
        target=UsdGeom.Camera.Define(stage,"/World/Cameras/"+identifier(camera["source"]))
        focal=0.5  # USD camera optical attributes are tenths of a stage unit (50 mm).
        aperture=2*focal*math.tan(math.radians(camera["fov"])/2)
        target.CreateProjectionAttr(UsdGeom.Tokens.orthographic if camera.get("orthographic") else UsdGeom.Tokens.perspective)
        if camera.get("orthographic"): aperture=camera["ortho_width"]*0.1
        target.CreateFocalLengthAttr(focal); target.CreateHorizontalApertureAttr(aperture)
        target.CreateVerticalApertureAttr(aperture/max(camera["aspect"],0.01))
        target.CreateClippingRangeAttr(Gf.Vec2f(0.01,10000))
        UsdGeom.Xformable(target).AddTransformOp().Set(forward*matrix(camera["matrix"]))
    if data.get("lights"):
        report["notes"].append("Light transforms, colors and intensity values are transferred. Unreal exposure, sky atmosphere and renderer-specific photometric behavior require adjustment in Isaac Sim.")
    stage.GetRootLayer().Save()
    for audit in report['decals']:
        supported=[]; blocked=[]
        for instance in data['instances']+data.get('instancers',[]):
            if instance['source'] not in audit['receivers']: continue
            affected=[key for key in decals.material_keys(instance) if audit['source'] in data['materials'].get(key,{}).get('decal_layers',[])]
            if any(not compiled[key][1] for key in affected): supported.append(instance['source'])
            if any(compiled[key][1] for key in affected): blocked.append(instance['source'])
        audit['supported_receivers']=supported; audit['blocked_receivers']=blocked
        if blocked: audit['status']='partial' if supported else 'blocked_receivers'
    report["status"]="partial" if issue_count else "converted"
    report["scene"]=str(stage_path)
    report["counts"]={"unique_meshes":len(mesh_data),"materials":len(materials),"translated_materials":sum(not issues and report['materials'][key]['backend']!='ExcludedWater' for key,(_,issues) in compiled.items()),"textures":len(data['textures']),"mesh_placements":len(data["instances"]),"point_instancers":len(all_instancers),"foliage_instances":instance_count,"lights":len(data.get('lights',[])),"cameras":len(data.get('cameras',[]))}
    report['counts'].update(individual_mesh_prims=len(ordinary),repeated_mesh_instances=repeated_count,
                            repeated_mesh_prototypes=report['repeated_static_instancing']['prototypes'])
    report['counts']['excluded_water_materials']=sum(m['backend']=='ExcludedWater' for m in report['materials'].values())
    report['counts']['attempted_materials']=len(materials)-report['counts']['excluded_water_materials']
    report['counts']['skeletal_mesh_placements']=sum(i.get('mesh_kind')=='skeletal_rest_pose' for i in data['instances'])
    report['counts']['decals']=len(report['decals'])
    report['counts']['source_decals']=source_decals
    report['counts']['vegetation_components_excluded_from_decals']=len(report['decal_receiver_exclusions'])
    report['counts']['projected_decals']=sum(d['status'] in ('projected','partial') for d in report['decals'])
    report['counts']['decal_material_variants']=sum(bool(m.get('decal_layers')) for m in authored_materials.values())
    report['counts']['max_decals_per_material']=max((len(m.get('decal_layers',[])) for m in authored_materials.values()),default=0)
    report['counts']['shared_world_material_groups']=len(data.get('world_decal_groups',[]))
    report['counts']['shared_mdl_definitions']=len(shared_programs)
    report['counts']['shared_base_materials']=len(data.get('_shared_base_keys',()))
    report['counts']['shared_base_shader_modules']=len(set(report['base_shader_modules'].values()))
    report['counts']['decal_material_regions']=sum(len(i.get('decal_sections',[])) for i in data['instances'])
    report['counts']['foliage_prototypes']=sum(len(i.get('decal_prototypes',[None])) for i in data.get('instancers',[]))
    if data.get('world_decal_groups'):
        budget = data['world_decal_slot_budget']
        report['notes'].append('A decal-free shared base evaluator supplies bounded local world-projected receiver shaders. Original mesh arrays and UVs remain intact. Ordinary props use only intersecting decals; heavily covered sections use coarse nearby face groups. Equal recipes share materials, and hidden placement uniforms permit MDL source sharing. No receiving-object bake, additional decal UV data or overlay geometry is generated. Shared base and decal controls require this extension while editing; saved values render independently. Genuine overlapping stacks are preserved, and Unreal DBuffer alpha blending remains approximate.')
    if report['counts']['max_decals_per_material']>8:
        report['notes'].append('At least one local face region intersects more than eight projectors. Required stacks remain intact rather than dropping decals; these regions can still be expensive.')
    report["notes"].append("Geometry and transforms are meters. unreal_object_position remains in original Unreal centimeters for material graph evaluation; UVs remain dimensionless.")
    if report['hidden_unsupported_sky']:
        report['notes'].append('Unsupported sky sphere/dome meshes were made invisible by the selected option, retaining their geometry and names. Supply an Isaac dome/environment light. These unsupported opaque sky placeholders can otherwise block environment lighting.')
    report['counts']['backends']={backend:sum(m['backend']==backend for m in report['materials'].values()) for backend in ('UsdPreviewSurface','OmniPBR','MDL','Unsupported','ExcludedWater')}
    if report['excluded_water_materials']:
        report['notes'].append('Identified water surfaces are excluded from shader conversion and decal receiving. Their geometry remains with a visible magenta placeholder for assigning a water material manually. Water-only maps are not used by generated shaders; exclusions are separate from unsupported static materials.')
    report["notes"].append("Unaffected foliage uses stock OmniPBR; decal receivers use MDL. No wind, subsurface or collision deformation is generated.")
    if data.get('decal_controls'):
        report['notes'].append('Live shared decal edits under /World/Decals require extension ash.unreal_usd601_decals enabled. Edits copy into local shader values on the next app update; save the stage afterward. Saved shader values render without the extension.')
    save_report()
    return stage_path,report
