import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'UnrealUsdBridge/Resources/Python'))
from ash_unreal_usd601_decals.usd_writer import convert
from ash_unreal_usd601_decals.decal_controls import DecalControls
from pxr import Usd,UsdGeom,UsdLux
from test_core import fixture_directory, placed_mesh
import test_decals

def with_lights_cameras(root):
    path,data=test_decals.DecalTests().data(root)
    data['lights']=[dict(source='/Game/Light',kind='rect',width=100,height=100,color=[1,1,1],intensity=10,matrix=test_decals.IDENTITY)]
    data['cameras']=[dict(source='/Game/Camera',fov=90,aspect=1.7,matrix=test_decals.IDENTITY)]
    path.write_text(json.dumps(data));return path

class SceneEditingTests(unittest.TestCase):
    def test_root_definitions_can_be_deleted_and_remain_deleted_after_reload(self):
        with fixture_directory() as root:
            manifest=with_lights_cameras(root)
            data=json.loads(manifest.read_text())
            # Keep one genuinely separate mesh to exercise ordinary-prim deletion.
            data['meshes']['actor_mesh']=dict(data['meshes']['mesh'])
            data['instances'][0]['mesh']='actor_mesh'
            manifest.write_text(json.dumps(data))
            scene,report=convert(manifest);self.assertEqual(scene.name,'Scene.usdc')
            self.assertFalse((root/'Scene.usda').exists());self.assertFalse((root/'SceneContent.usdc').exists())
            s=Usd.Stage.Open(str(scene));layer=s.GetRootLayer();self.assertEqual(list(layer.subLayerPaths),[])
            self.assertEqual(s.GetEditTarget().GetLayer(),layer)
            targets=['/World/Objects/Actor']+[str(p.GetPath()) for p in s.Traverse() if p.IsA(UsdGeom.Camera) or p.IsA(UsdLux.RectLight)]
            self.assertEqual(len(targets),3)
            for path in targets:
                self.assertIsNotNone(layer.GetPrimAtPath(path));self.assertTrue(s.RemovePrim(path));self.assertFalse(s.GetPrimAtPath(path))
            layer.Save();layer.Reload()
            self.assertTrue(all(not s.GetPrimAtPath(p) for p in targets))
            self.assertTrue(placed_mesh(s,'Raised'))
            self.assertTrue((root/'Geometry.usdc').exists())
            sync=DecalControls(s);s.GetAttributeAtPath('/World/Decals/TestDecal.inputs:amount').Set(.2)
            self.assertFalse(s.GetPrimAtPath('/World/Objects/Actor'));sync.close()

    def test_repeated_instancer_can_be_deleted_and_stays_deleted(self):
        with fixture_directory() as root:
            scene,_=convert(with_lights_cameras(root))
            stage=Usd.Stage.Open(str(scene))
            path=next(p.GetPath() for p in stage.Traverse()
                      if p.IsA(UsdGeom.PointInstancer) and p.GetPath().HasPrefix('/World/Instances'))
            self.assertIsNotNone(stage.GetRootLayer().GetPrimAtPath(path))
            self.assertTrue(stage.RemovePrim(path))
            stage.GetRootLayer().Save();stage.GetRootLayer().Reload()
            self.assertFalse(stage.GetPrimAtPath(path))

    def test_all_camera_light_option_combinations_preserve_other_content(self):
        for cameras,lights in ((True,True),(True,False),(False,True),(False,False)):
            with self.subTest(cameras=cameras,lights=lights),fixture_directory() as root:
                path=with_lights_cameras(root);scene,r=convert(path,export_cameras=cameras,export_lights=lights)
                s=Usd.Stage.Open(str(scene));self.assertEqual(r['counts']['cameras'],int(cameras));self.assertEqual(r['counts']['lights'],int(lights))
                self.assertEqual(sum(p.IsA(UsdGeom.Camera) for p in s.Traverse()),int(cameras))
                self.assertEqual(sum(p.IsA(UsdLux.RectLight) for p in s.Traverse()),int(lights))
                self.assertEqual(r['counts']['mesh_placements'],4);self.assertEqual(r['counts']['foliage_instances'],2)
                self.assertEqual(r['counts']['projected_decals'],1)
                self.assertEqual(r['source_cameras'],1);self.assertEqual(r['source_lights'],1)
                source=json.loads((root/'source-manifest.json').read_text());self.assertEqual(len(source['lights']),1);self.assertEqual(len(source['cameras']),1)

