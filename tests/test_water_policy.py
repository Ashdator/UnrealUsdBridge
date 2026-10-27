import json,unittest
from pxr import Usd,UsdShade
from test_core import fixture_directory
import test_usd
from ash_unreal_usd601_decals.water_policy import excluded
from ash_unreal_usd601_decals.usd_writer import convert


class WaterPolicyTests(unittest.TestCase):
    def test_only_water_surfaces_are_excluded(self):
        for material in ({'water_surface':True},
                         {'translucent':True,'name':'MI_Water_Inst2'},
                         {'translucent':True,'source':'/Game/Water/M_Lake.M_Lake'}):
            self.assertTrue(excluded(material))
        for material in ({'translucent':True,'name':'M_Glass'},
                         {'name':'M_Waterproof_Roof'},
                         {'name':'M_Water_Pipe','translucent':False},
                         {'name':'M_Water_Leak','domain':'decal','translucent':True}):
            self.assertFalse(excluded(material))

    def test_water_exclusion_is_reported_without_failure_or_material_translation(self):
        with fixture_directory() as root:
            manifest=test_usd.UsdIntegrationTests().fixture(root);data=json.loads(manifest.read_text())
            data['materials']['mat'].update(name='MI_Water_Inst',translucent=True,
                inputs={'base_color':{'op':'unsupported','reason':'SceneColor water graph'}},
                issues=['DepthFade water graph'])
            manifest.write_text(json.dumps(data));scene,report=convert(manifest)
            self.assertEqual(report['counts']['excluded_water_materials'],1)
            self.assertEqual(report['counts']['attempted_materials'],0)
            self.assertEqual(report['counts']['translated_materials'],0)
            self.assertEqual(report['materials']['mat']['backend'],'ExcludedWater')
            self.assertEqual(report['issue_count'],0)
            stage=Usd.Stage.Open(str(scene))
            shader=next(p for p in stage.Traverse() if p.IsA(UsdShade.Shader))
            self.assertEqual(shader.GetAttribute('inputs:opacity').Get(),1)
            self.assertEqual(tuple(shader.GetAttribute('inputs:diffuseColor').Get()),(1,0,1))
            self.assertFalse(list((root/'materials').glob('*.mdl')))
