import copy
import json
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'UnrealUsdBridge/Resources/Python'))
from ash_unreal_usd601_decals.repeated_meshes import prepare, IDENTITY
from ash_unreal_usd601_decals.usd_writer import convert
from test_core import fixture_directory
import test_usd
try:
    from pxr import Usd, UsdGeom, UsdShade, Gf
except ImportError:
    Usd = None


class RepeatedPlanningTests(unittest.TestCase):
    def test_distinct_material_paint_and_decal_partitions_are_prototypes(self):
        base = {'source': 'tree0', 'name': 'Pine_Tree', 'mesh': 'mesh', 'materials': ['bark', 'leaves'], 'matrix': list(IDENTITY)}
        copies = [dict(base, source='tree'+str(i)) for i in range(5)]
        copies[2]['materials'] = ['different', 'leaves']
        copies[3]['colors'] = [[1, 0, 0, 1]]
        copies[4]['decal_sections'] = [{'faces': [0], 'material': 'decal'}]
        data = {'instances': copies, 'meshes': {'mesh': {'source': '/Game/SM_Pine_Tree.SM_Pine_Tree'}}}
        remaining, groups, audit = prepare(data, {'mesh': {}}, lambda _: True)
        self.assertFalse(remaining)
        self.assertEqual(groups[0]['decal_proto_indices'], [0, 0, 1, 2, 3])
        self.assertEqual(audit['instances'], 5)
        self.assertEqual(audit['prototypes'], 4)
        self.assertEqual(len(data['instances']), 5)

    def test_hidden_groups_and_ineligible_components(self):
        instances = [dict(source=str(i), name='Tree', mesh='mesh', materials=['mat'], matrix=IDENTITY,
                          visible=i < 2) for i in range(4)]
        instances += [dict(instances[0], source='skeletal', mesh_kind='skeletal_rest_pose'),
                      dict(instances[0], source='landscape', mesh='terrain'),
                      dict(instances[0], source='shear', matrix=[0]*16)]
        data = {'instances': instances, 'meshes': {'mesh': {}, 'terrain': {}}}
        remaining, groups, audit = prepare(data, {'mesh': {}, 'terrain': {'unified_landscape': True}}, lambda x: x != [0]*16)
        self.assertEqual(len(groups), 2)
        self.assertEqual([g['visible'] for g in groups], [True, False])
        self.assertEqual({i['source'] for i in remaining}, {'skeletal', 'landscape', 'shear'})
        self.assertEqual(audit['excluded_placements'], {'skeletal_rest_pose': 1, 'landscape': 1, 'non_srt_transform': 1})


@unittest.skipIf(Usd is None, 'Requires USD Python')
class RepeatedUsdTests(unittest.TestCase):
    def test_renderable_geometry_bindings_positions_and_component_frame(self):
        with fixture_directory() as root:
            manifest = test_usd.UsdIntegrationTests().fixture(root)
            data = json.loads(manifest.read_text())
            data['instancers'] = []
            data['materials']['mat']['inputs']['base_color'] = {'op': 'local_position', 'origin': 'component'}
            data['materials']['other'] = dict(copy.deepcopy(data['materials']['mat']), name='Other')
            first = data['instances'][0]
            placements = []
            for i in range(4):
                obj = copy.deepcopy(first)
                obj.update(source='/Game/Pine'+str(i), name='Pine_Tree'+str(i), object_position=[10*i,20*i,30*i])
                obj['matrix'] = [0,2,0,0,-3,0,0,0,0,0,4,0,100*i,200*i,300*i,1]
                if i==1:obj['matrix'][1]=-2  # Mirrored instance, same geometry/material.
                if i == 2: obj['materials'] = ['other']
                if i == 3: obj['colors'] = [[1,0,0,1]]*3
                placements.append(obj)
            data['instances'] = placements
            manifest.write_text(json.dumps(data))
            scene, report = convert(manifest)
            stage = Usd.Stage.Open(str(scene))
            pi = next(UsdGeom.PointInstancer(p) for p in stage.Traverse() if p.IsA(UsdGeom.PointInstancer))
            self.assertEqual(report['counts']['repeated_mesh_instances'], 4)
            self.assertEqual(report['counts']['individual_mesh_prims'], 0)
            self.assertEqual(report['counts']['foliage_instances'], 0)
            self.assertEqual(len(pi.GetPrototypesRel().GetTargets()), 3)
            self.assertEqual(list(pi.GetProtoIndicesAttr().Get()), [0,0,1,2])
            self.assertEqual(list(pi.GetPrim().GetCustomDataByKey('unreal:instanceSources')), [p['source'] for p in placements])
            self.assertFalse(pi.GetPrim().GetAttribute('primvars:unreal_instance_to_component_0'))
            positions = UsdGeom.PrimvarsAPI(pi).GetPrimvar('unreal_object_position')
            self.assertEqual(positions.GetInterpolation(), 'vertex')
            self.assertEqual(tuple(positions.Get()[2]), (20,40,60))
            matrices = pi.ComputeInstanceTransformsAtTime(Usd.TimeCode.Default(), Usd.TimeCode.Default())
            for transform, obj in zip(matrices, placements):
                flat=obj['matrix']; signs=(1,-1,1,1)
                expected=Gf.Matrix4d(*[flat[4*i+j]*signs[i]*signs[j]*(.01 if i==3 and j<3 else 1) for i in range(4) for j in range(4)])
                self.assertLess((transform.Transform(Gf.Vec3d(.2,.3,.4))-expected.Transform(Gf.Vec3d(.2,.3,.4))).GetLength(), .003)
            for index, target in enumerate(pi.GetPrototypesRel().GetTargets()):
                mesh=UsdGeom.Mesh(stage.GetPrimAtPath(target))
                self.assertTrue(mesh)
                self.assertEqual(len(mesh.GetPointsAttr().Get()),3)
                self.assertEqual(UsdGeom.Imageable(mesh).ComputeVisibility(),'inherited')
                self.assertFalse(mesh.GetPrim().GetAttribute('primvars:unreal_object_position'))
                subset=UsdShade.MaterialBindingAPI(mesh).GetMaterialBindSubsets()[0]
                material,_=UsdShade.MaterialBindingAPI(subset).ComputeBoundMaterial()
                self.assertEqual(material.GetPath().name, 'Other' if index==1 else 'Paint')
            colored=stage.GetPrimAtPath(pi.GetPrototypesRel().GetTargets()[2])
            self.assertEqual(len(UsdGeom.PrimvarsAPI(colored).GetPrimvar('unreal_vertex_color').Get()),3)

    def test_decal_sections_survive_and_hidden_srt_exceptions_stay_individual(self):
        with fixture_directory() as root:
            manifest=test_usd.UsdIntegrationTests().fixture(root)
            data=json.loads(manifest.read_text());data['instancers']=[]
            a=data['instances'][0]
            a['decal_sections']=[{'faces':[0],'material':'mat','section':0,'slot':0}]
            b=copy.deepcopy(a);b.update(source='B',name='B')
            hidden=copy.deepcopy(a);hidden.update(source='hidden',name='Hidden',visible=False)
            shear=copy.deepcopy(a);shear.update(source='shear',name='Shear');shear['matrix'][1]=.5
            data['instances']=[a,b,hidden,shear]
            manifest.write_text(json.dumps(data));scene,report=convert(manifest)
            stage=Usd.Stage.Open(str(scene))
            self.assertEqual(report['counts']['repeated_mesh_instances'],2)
            self.assertEqual(report['counts']['individual_mesh_prims'],2)
            self.assertEqual(report['repeated_static_instancing']['excluded_placements']['non_srt_transform'],1)
            pi=next(UsdGeom.PointInstancer(p) for p in stage.Traverse() if p.IsA(UsdGeom.PointInstancer))
            prototype=stage.GetPrimAtPath(pi.GetPrototypesRel().GetTargets()[0])
            self.assertFalse(stage.GetPrimAtPath(prototype.GetPath().AppendChild('section_0')).IsActive())
            region=stage.GetPrimAtPath(prototype.GetPath().AppendChild('decal_region_0'))
            self.assertEqual(list(UsdGeom.Subset(region).GetIndicesAttr().Get()),[0])
            self.assertTrue(UsdShade.MaterialBindingAPI(region).ComputeBoundMaterial()[0])
            self.assertEqual(UsdGeom.Imageable(stage.GetPrimAtPath('/World/Objects/Hidden')).ComputeVisibility(),'invisible')
