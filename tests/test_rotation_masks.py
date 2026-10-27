import math
import unittest
from test_core import constant
from ash_unreal_usd601_decals.graph import evaluate,Constant,Unsupported
from ash_unreal_usd601_decals.mdl import compile_mdl,compile_function
from ash_unreal_usd601_decals.material_policy import foliage_normal


class RotationMaskTests(unittest.TestCase):
    def test_fresnel_uses_material_normal_in_functions_and_materials(self):
        fresnel={'op':'fresnel','exponent':constant([5]),'base':constant([0.04])}
        normal={'op':'mask','input':{'op':'texture','texture':'normal','normal_map':True},'channels':[0,1,2]}
        textures={'normal':{'file':'normal.png'}}
        program,issues=compile_mdl({'inputs':{'base_color':fresnel,'normal':normal}},textures)
        self.assertFalse(issues)
        function=compile_function(fresnel,textures,'float',normal)
        for p in (program,function):
            self.assertIn('-state::direction()',p['source'])
            self.assertIn('state::texture_tangent_u(0)',p['source'])
            self.assertTrue(any(v.get('file')=='normal.png' for v in p['parameters'].values()))

    def test_fresnel_normal_cycle_is_reported(self):
        node={'op':'fresnel','exponent':constant([5]),'base':constant([0.04])}
        _,issues=compile_mdl({'inputs':{'normal':node,'base_color':node}}, {})
        self.assertIn('cycle',issues[0])

    def test_period_scaling_and_live_rotation_parameter(self):
        for op,expected in [('sin',1),('cos',0)]:
            node={'op':op,'input':constant([0.25]),'frequency':2*math.pi}
            self.assertAlmostEqual(evaluate(node).value[0],expected,places=6)
            node['input']['parameter']='Rotation'
            program,issues=compile_mdl({'inputs':{'roughness':node}}, {})
            self.assertFalse(issues)
            self.assertIn('math::'+op,program['source'])
            self.assertTrue(any(p['label']=='Rotation' for p in program['parameters'].values()))

    def test_curtain_reassembles_same_normal_without_baking(self):
        tex={'op':'texture','texture':'normal','normal_map':True,'uv':{'op':'uv','scale':[15,15]}}
        node={'op':'append','a':{'op':'multiply','a':{'op':'mask','input':tex,'channels':[0,1]},'b':constant([1])},
              'b':{'op':'mask','input':tex,'channels':[2]}}
        normal=foliage_normal({'inputs':{'normal':node}})
        self.assertEqual(normal.texture,'normal');self.assertEqual(normal.channels,(0,1,2))
        self.assertEqual(normal.uv.scale,(15,15));self.assertEqual(normal.scale,(2,-2,2,1))

    def test_append_does_not_mix_different_textures_or_conflicting_channels(self):
        a={'op':'texture','texture':'a','channels':[0]}
        b={'op':'texture','texture':'b','channels':[1]}
        with self.assertRaises(Unsupported):evaluate({'op':'append','a':a,'b':b})
        b={'op':'multiply','a':a,'b':constant([2])}
        with self.assertRaises(Unsupported):evaluate({'op':'append','a':a,'b':b})
        self.assertEqual(evaluate({'op':'append','a':constant([0,0]),'b':constant([1])}),Constant((0,0,1)))

    def test_weightmaps_raw_separate_uv_and_shared_bounded_softness(self):
        node={'op':'texture','texture':'weights','usage':'landscape_weight','uv':{'op':'uv','channel':1},'color_space':'raw','wrap_s':'clamp','wrap_t':'clamp'}
        with self.assertRaises(Unsupported):evaluate(node)
        program,issues=compile_mdl({'inputs':{'base_color':node,'roughness':{'op':'mask','input':node,'channels':[1]}}},
                                  {'weights':{'file':'textures/weight.png'}})
        self.assertFalse(issues)
        self.assertEqual(program['uv_channels'],[1])
        self.assertEqual(program['parameters']['landscape_mask_softness']['value'],0)
        self.assertIn('math::clamp(landscape_mask_softness,0.0,2.0)',program['source'])
        self.assertIn('tex::texel_float4',program['source'])
        node['color_space']='sRGB'
        _,issues=compile_mdl({'inputs':{'base_color':node}},{'weights':{'file':'x.png'}})
        self.assertIn('raw',issues[0])
