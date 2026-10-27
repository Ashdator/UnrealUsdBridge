import copy,json,unittest
from test_core import fixture_directory,placed_mesh
import test_usd
from ash_unreal_usd601_decals.usd_writer import convert
from pxr import Usd,UsdGeom,UsdShade


class SplineUsdTests(unittest.TestCase):
    def fixture(self,root):
        path=test_usd.UsdIntegrationTests().fixture(root)
        data=json.loads(path.read_text());data['instancers']=[]
        mesh=json.loads((root/'meshes/m.json').read_text())
        mesh.update(geometry_source='spline_deformed_original',source_triangles=1,
                    source_mesh='/Game/Rope.Rope',spline_component='/Game/Actor.SplineA',
                    spline_reversed_winding=False)
        mesh['points']=[[0,0,0],[100,0,20],[0,100,10]]
        mesh['uvs'].append([[.1,.2],[.3,.4],[.5,.6]])
        (root/'meshes/m.json').write_text(json.dumps(mesh))
        data['meshes']['mesh'].update(source='/Game/Rope.Rope',spline_component=mesh['spline_component'])
        data['instances'][0]['mesh_kind']='spline_deformed'
        path.write_text(json.dumps(data))
        return path,data,mesh

    def test_deformed_shape_units_uvs_binding_and_metadata(self):
        with fixture_directory() as root:
            path,data,mesh=self.fixture(root)
            scene,report=convert(path)
            stage=Usd.Stage.Open(str(scene));prim=placed_mesh(stage,'Actor');geometry=UsdGeom.Mesh(prim)
            self.assertAlmostEqual(geometry.GetPointsAttr().Get()[1][2],.2)
            self.assertAlmostEqual(geometry.GetPointsAttr().Get()[2][1],-1)
            self.assertEqual(UsdGeom.GetStageMetersPerUnit(stage),1)
            self.assertEqual(prim.GetCustomDataByKey('unreal:splineComponent'),'/Game/Actor.SplineA')
            self.assertEqual(prim.GetCustomDataByKey('unreal:splineSourceMesh'),'/Game/Rope.Rope')
            self.assertEqual(report['geometry']['mesh']['spline_component'],'/Game/Actor.SplineA')
            uv=UsdGeom.PrimvarsAPI(prim).GetPrimvar('st1').Get()
            self.assertAlmostEqual(uv[0][0],.1);self.assertAlmostEqual(uv[0][1],.8)
            subsets=UsdShade.MaterialBindingAPI(prim).GetMaterialBindSubsets()
            self.assertTrue(UsdShade.MaterialBindingAPI(subsets[0]).ComputeBoundMaterial()[0])

    def test_different_curves_do_not_become_one_shared_mesh(self):
        with fixture_directory() as root:
            path,data,mesh=self.fixture(root)
            other=copy.deepcopy(mesh);other['points'][1][2]=80;other['spline_component']='/Game/Actor.SplineB'
            (root/'meshes/other.json').write_text(json.dumps(other))
            data['meshes']['other']=dict(file='meshes/other.json',source='/Game/Rope.Rope')
            instance=copy.deepcopy(data['instances'][0]);instance.update(name='OtherCurve',source='/Game/OtherActor',mesh='other')
            data['instances'].append(instance);path.write_text(json.dumps(data))
            scene,report=convert(path);stage=Usd.Stage.Open(str(scene))
            self.assertFalse(any(p.IsA(UsdGeom.PointInstancer) for p in stage.Traverse()))
            self.assertAlmostEqual(UsdGeom.Mesh(placed_mesh(stage,'Actor')).GetPointsAttr().Get()[1][2],.2)
            self.assertAlmostEqual(UsdGeom.Mesh(placed_mesh(stage,'OtherCurve')).GetPointsAttr().Get()[1][2],.8)

    def test_spline_topology_must_retain_original_triangle_count(self):
        with fixture_directory() as root:
            path,data,mesh=self.fixture(root);mesh['source_triangles']=2
            (root/'meshes/m.json').write_text(json.dumps(mesh))
            with self.assertRaisesRegex(ValueError,'Original mesh triangle count changed'):convert(path)

    def test_mirrored_spline_keeps_extracted_triangle_order(self):
        with fixture_directory() as root:
            path,data,mesh=self.fixture(root)
            mesh['spline_reversed_winding']=True;mesh['indices']=list(reversed(mesh['indices']))
            (root/'meshes/m.json').write_text(json.dumps(mesh))
            scene,report=convert(path);stage=Usd.Stage.Open(str(scene))
            self.assertEqual(list(UsdGeom.Mesh(placed_mesh(stage,'Actor')).GetFaceVertexIndicesAttr().Get()),mesh['indices'])
            self.assertTrue(report['geometry']['mesh']['spline_reversed_winding'])
