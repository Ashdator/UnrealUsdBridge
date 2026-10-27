import json
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'UnrealUsdBridge/Resources/Python'))
from ash_unreal_usd601_decals.usd_writer import convert
from ash_unreal_usd601_decals.mdl import compile_function
from ash_unreal_usd601_decals.decal_regions import triangle_hits,ground_asset
import numpy as np
from pxr import Usd,UsdGeom,UsdShade
from test_core import fixture_directory, placed_mesh
import test_decals


class DecalMemoryTests(unittest.TestCase):
    def test_ground_asset_matching_uses_leaf_names_not_folders_or_substrings(self):
        self.assertTrue(ground_asset({'source':'/Game/Props/Diorama_Ground.Diorama_Ground'}))
        self.assertTrue(ground_asset({'name':'SM_TerrainGround_02'}))
        self.assertFalse(ground_asset({'source':'/Game/Ground/Tire.Tire'}))
        self.assertFalse(ground_asset({'name':'SM_BackgroundSign'}))

    def test_static_ground_many_decals_preserves_both_original_sections(self):
        with fixture_directory() as root:
            path,data=test_decals.DecalTests().data(root)
            mesh_path=root/data['meshes']['mesh']['file'];mesh=json.loads(mesh_path.read_text())
            points=[];uvs=[];indices=[]
            for i in range(10):
                points.extend([[400*i,0,0],[400*i+100,0,0],[400*i,100,0]])
                uvs.extend([[0,0],[1,0],[0,1]]);indices.extend([i*3,i*3+2,i*3+1])
            mesh.update(points=points,normals=[[0,0,1]]*len(points),indices=indices,uvs=[uvs],
                        sections=[{'slot':0,'first_face':0,'face_count':9},{'slot':1,'first_face':9,'face_count':1}])
            mesh_path.write_text(json.dumps(mesh))
            data['meshes']['mesh']['source']='/Game/Meshes/Diorama_Ground.Diorama_Ground'
            data['instances']=data['instances'][:1];data['instances'][0]['materials']=['mat','mat']
            data['instancers']=[];data['decals']=[]
            for i in range(9):
                d=test_decals.decal('Decal'+str(i),i);d['matrix'][12]=400*i;data['decals'].append(d)
            path.write_text(json.dumps(data));scene,report=convert(path)
            self.assertEqual(report['counts']['projected_decals'],9)
            self.assertLessEqual(report['counts']['max_decals_per_material'],8)
            self.assertEqual(len(report['ground_decal_regions']),1)
            self.assertEqual(report['ground_decal_regions'][0]['decals'],9)
            stage=Usd.Stage.Open(str(scene));prim=placed_mesh(stage,'Actor')
            faces=[]
            for child in prim.GetChildren():
                if not child.IsA(UsdGeom.Subset):continue
                material=UsdShade.MaterialBindingAPI(child).ComputeBoundMaterial()[0]
                self.assertTrue(material)
                face_indices=list(child.GetAttribute('indices').Get());faces.extend(face_indices)
                if 9 in face_indices:self.assertEqual(material.GetPrim().GetDisplayName(),'Paint')
            self.assertEqual(sorted(faces),list(range(10)))
            self.assertEqual(list(UsdGeom.Mesh(prim).GetFaceVertexIndicesAttr().Get()),indices)



    def test_distributed_86_decals_keep_one_mesh_and_local_materials(self):
        with fixture_directory() as root:
            path,data=test_decals.DecalTests().data(root)
            mesh_path=root/data['meshes']['mesh']['file']
            mesh=json.loads(mesh_path.read_text())
            points=[];uvs=[];indices=[]
            for i in range(86):
                points.extend([[400*i,0,0],[400*i+100,0,0],[400*i,100,0]])
                uvs.extend([[0,0],[1,0],[0,1]])
                indices.extend([i*3,i*3+2,i*3+1])
            mesh.update(points=points,normals=[[0,0,1]]*len(points),indices=indices,uvs=[uvs],
                        sections=[{'slot':0,'first_face':0,'face_count':86}],unified_landscape=True)
            mesh_path.write_text(json.dumps(mesh))
            data['instances']=data['instances'][:1];data['instancers']=[];data['decals']=[]
            for i in range(86):
                d=test_decals.decal('Decal'+str(i),i);d['matrix'][12]=400*i
                data['decals'].append(d)
            path.write_text(json.dumps(data));scene,report=convert(path)
            self.assertEqual(report['counts']['projected_decals'],86)
            self.assertLessEqual(report['counts']['max_decals_per_material'],8)
            self.assertEqual(report['counts']['decal_material_variants'],86)
            self.assertEqual(report['counts']['max_decals_per_material'],1)
            self.assertEqual(report['counts']['shared_base_materials'],1)
            self.assertEqual(report['counts']['unique_meshes'],1)
            stage=Usd.Stage.Open(str(scene));prim=placed_mesh(stage,'Actor')
            faces=[]
            for child in prim.GetChildren():
                if child.IsA(UsdGeom.Subset):
                    faces.extend(UsdGeom.Subset(child).GetIndicesAttr().Get())
                    material=UsdShade.MaterialBindingAPI(child).ComputeBoundMaterial()[0]
                    self.assertTrue(material)
                    controls={a.GetCustomDataByKey('unreal:decalControl') for p in Usd.PrimRange(material.GetPrim()) for a in p.GetAttributes()}
                    for face in UsdGeom.Subset(child).GetIndicesAttr().Get():
                        self.assertIn(f'/World/Decals/Decal{face}.inputs:amount',controls)
            self.assertEqual(sorted(faces),list(range(86)))
            self.assertEqual(list(UsdGeom.Mesh(prim).GetFaceVertexIndicesAttr().Get()),indices)
            compact=json.loads(path.read_text())
            self.assertEqual(len(compact['materials']),2)
            self.assertFalse(any(m.get('decal_layers') for m in compact['materials'].values()))
            self.assertEqual(compact,json.loads((root/'source-manifest.json').read_text()))
            for item in report['materials'].values():
                layers=item.get('decal_layers',[])
                self.assertEqual(layers,sorted(layers,key=lambda name:int(name[5:])))

    def test_foliage_uses_local_prototypes_preserving_instance_order(self):
        with fixture_directory() as root:
            path,data=test_decals.DecalTests().data(root)
            data['instances']=[]
            instance=data['instancers'][0]
            instance['matrix']=test_decals.IDENTITY[:]
            matrices=[]
            for x in (0,1000,3000):
                m=test_decals.IDENTITY[:];m[12]=x;matrices.append(m)
            instance['transforms']=matrices;instance['random_values']=[.1,.2,.3]
            other=test_decals.decal('Other');other['matrix'][12]=1000
            data['decals'].append(other)
            path.write_text(json.dumps(data));scene,report=convert(path)
            self.assertEqual(report['counts']['foliage_instances'],3)
            self.assertEqual(report['counts']['max_decals_per_material'],1)
            self.assertEqual(report['counts']['foliage_prototypes'],3)
            stage=Usd.Stage.Open(str(scene))
            p=next(p for p in stage.Traverse() if p.IsA(UsdGeom.PointInstancer))
            inst=UsdGeom.PointInstancer(p)
            self.assertEqual(list(inst.GetProtoIndicesAttr().Get()),[0,1,2])
            self.assertEqual([round(p[0]) for p in inst.GetPositionsAttr().Get()],[0,10,30])

    def test_diagonal_triangle_box_false_positive_is_rejected(self):
        points=np.array([[0,3,0],[3,0,0],[3,3,0]],dtype=float)
        hit=triangle_hits(points,np.array([[0,1,2]]),np.eye(4))
        self.assertFalse(hit[0])

    def test_foliage_function_omits_unused_landscape_helpers(self):
        program=compile_function({'op':'constant','value':[.5]}, {},'float')
        self.assertNotIn('landscape_weight(',program['source'])
        self.assertNotIn('landscape_bilinear(',program['source'])
        self.assertNotIn('rotate_delta(',program['source'])
        self.assertNotIn('float4 to4_',program['source'])
