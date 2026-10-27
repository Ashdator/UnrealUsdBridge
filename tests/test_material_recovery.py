import copy,unittest
from ash_unreal_usd601_decals.basic_surface import recover
from ash_unreal_usd601_decals.mdl import compile_mdl

class MaterialRecoveryTests(unittest.TestCase):
    def data(self):
        uv={'op':'uv','channel':1,'scale':[3,4]}
        a={'op':'texture','texture':'a','uv':uv,'channels':[0,1,2]}
        b={'op':'texture','texture':'b','uv':uv,'channels':[0,1,2]}
        return {'inputs':{'base_color':{'op':'lerp','a':a,'b':b,'alpha':{'op':'constant','value':[.3]}},'roughness':{'op':'constant','value':[.7]}},'issues':['Connected Pixel Depth Offset is unsupported unless the captured value is provably zero']},{'a':{'file':'textures/a.png'},'b':{'file':'textures/b.png'}}
    def test_layered_static_keeps_actual_blend_and_uvs(self):
        mat,textures=self.data();original=copy.deepcopy(mat);result=recover(mat,textures)
        self.assertIsNotNone(result);self.assertEqual(result['inputs'],mat['inputs']);self.assertEqual(mat,original)
        self.assertFalse(compile_mdl(result,textures)[1]);self.assertTrue(result['basic_surface_fallback'])
    def test_missing_layer_mask_remains_unsupported(self):
        mat,textures=self.data();mat['inputs']['base_color']['alpha']={'op':'unsupported','reason':'camera projection unavailable'}
        self.assertIsNone(recover(mat,textures))
    def test_sky_water_and_decals_remain_excluded(self):
        for marker in ({'unlit':True},{'water_surface':True},{'decal_channels':['base_color']}):
            mat,textures=self.data();mat.update(marker);self.assertIsNone(recover(mat,textures))
    def test_opaque_shading_model_recovery_uses_original_maps(self):
        mat,textures=self.data();mat['issues']=['Unsupported Unreal shading model'];result=recover(mat,textures)
        self.assertEqual(result['inputs']['base_color'],mat['inputs']['base_color']);self.assertFalse(compile_mdl(result,textures)[1])
