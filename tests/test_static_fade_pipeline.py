"""Verify resolved native foliage snapshots keep real cutout wiring in USD.

These are USD pipeline checks, not a substitute for the native commandlet
fixtures, which also exercise Unreal branch selection and function arguments.
"""
import json,unittest
import test_usd
from test_core import fixture_directory
from ash_unreal_usd601_decals.graph import evaluate,Sample
from ash_unreal_usd601_decals.usd_writer import convert
from pxr import Usd,UsdShade

class StaticFadePipelineTests(unittest.TestCase):
    def test_resolved_fade_preserves_alpha_cutout_in_both_shader_backends(self):
        for foliage in (False,True):
            with self.subTest(foliage=foliage),fixture_directory() as root:
                path=test_usd.UsdIntegrationTests().fixture(root)
                data=json.loads(path.read_text())
                mat=data['materials']['mat'];mat.update(name='SnapshotLeaves',foliage=foliage,two_sided=True,opacity_threshold=.4)
                mat['inputs']['opacity']={'op':'multiply','a':{'op':'mask','input':{'op':'texture','texture':'tex'},'channels':[3]},'b':{'op':'constant','value':[1]}}
                opacity=evaluate(mat['inputs']['opacity'])
                self.assertIsInstance(opacity,Sample);self.assertEqual(opacity.channels,(3,))
                self.assertEqual(opacity.scale[3],1.)
                path.write_text(json.dumps(data))
                scene,report=convert(path)
                self.assertFalse(report['materials']['mat']['issues'])
                self.assertEqual(report['materials']['mat']['backend'],'OmniPBR' if foliage else 'UsdPreviewSurface')
                stage=Usd.Stage.Open(str(scene));base='/World/Looks/SnapshotLeaves/'
                shader=UsdShade.Shader(stage.GetPrimAtPath(base+('OmniPBR' if foliage else 'Surface')))
                source=shader.GetInput('opacity_constant' if foliage else 'opacity').GetConnectedSource()
                self.assertTrue(source)
                if foliage:
                    self.assertEqual(str(source[0].GetPath()),base+'opacity_graph')
                    self.assertTrue(shader.GetInput('enable_opacity').Get())
                else:
                    self.assertEqual(source[1],'a')
                self.assertAlmostEqual(shader.GetInput('opacity_threshold' if foliage else 'opacityThreshold').Get(),.4,places=6)
                self.assertEqual(report['counts']['foliage_instances'],2)
