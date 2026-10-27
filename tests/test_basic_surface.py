import copy,json,unittest
import test_usd
from test_core import fixture_directory
from ash_unreal_usd601_decals.basic_surface import recover
from ash_unreal_usd601_decals.graph import compile_material
from ash_unreal_usd601_decals.usd_writer import convert
from pxr import Usd,UsdShade


class BasicSurfaceTests(unittest.TestCase):
    def test_render_effect_does_not_block_basic_maps_or_opacity_alpha(self):
        sample={'op':'texture','texture':'image','color_space':'sRGB'}
        mat={'inputs':{'base_color':{'op':'mask','input':sample,'channels':[0,1,2]},
            'normal':{'op':'texture','texture':'normal','normal_map':True},
            'roughness':{'op':'mask','input':sample,'channels':[1]},
            'opacity':{'op':'multiply','a':{'op':'mask','input':sample,'channels':[3]},
                'b':{'op':'unsupported','reason':'DitherTemporalAA'}},
            'metallic':{'op':'constant','value':[1]},'emissive':sample},
            'issues':['Connected Pixel Depth Offset is unsupported unless the captured value is provably zero']}
        original=copy.deepcopy(mat)
        result=recover(mat,{'image':{},'normal':{}})
        self.assertEqual(mat,original)
        self.assertEqual(set(result['inputs']),{'base_color','normal','roughness','opacity'})
        compiled,issues=compile_material(result)
        self.assertFalse(issues)
        self.assertEqual(compiled['opacity'].channels,(3,))
        self.assertEqual(compiled['roughness'].channels,(1,))
        self.assertEqual(compiled['normal'].color_space,'raw')

    def test_billboard_mip_maps_keep_source_override_and_use_mesh_uv(self):
        sample={'op':'texture','texture':'instance_override','normal_map':False,
            'sampling_issue':'Explicit texture mip/derivative control is unsupported',
            'source_uv_channel':1,'uv':{'op':'unsupported','reason':'billboard UV'}}
        result=recover({'inputs':{'base_color':sample,'opacity':{'op':'mask','input':sample,'channels':[3]}}},
            {'instance_override':{}})
        self.assertEqual(result['inputs']['base_color']['texture'],'instance_override')
        self.assertEqual(result['inputs']['base_color']['uv'],{'op':'uv','channel':1})
        self.assertNotIn('sampling_issue',result['inputs']['base_color'])

    def test_ambiguous_layer_maps_are_not_guessed_and_sky_stays_unsupported(self):
        a={'op':'texture','texture':'a'};b={'op':'texture','texture':'b'}
        mat={'inputs':{'base_color':{'op':'lerp','a':a,'b':b,'alpha':{'op':'unsupported','reason':'DitherTemporalAA'}}}}
        self.assertIsNone(recover(mat,{'a':{},'b':{}}))
        for issue in ('MaterialExpressionSkyAtmosphereViewLuminance','MaterialExpressionPixelDepth'):
            self.assertIsNone(recover({'inputs':{'base_color':a},'issues':[issue]}, {'a':{}}))

    def test_main_normal_survives_split_xy_z_math_and_opacity_comparison(self):
        normal={'op':'texture','texture':'n','normal_map':True}
        image={'op':'texture','texture':'a'}
        mat={'inputs':{'base_color':image,'normal':{'op':'append',
            'a':{'op':'mask','input':normal,'channels':[0,1]},'b':{'op':'mask','input':normal,'channels':[2]}},
            'opacity':{'op':'if','a':{'op':'mask','input':image,'channels':[3]},
                'b':{'op':'constant','value':[.05]},'greater':{'op':'constant','value':[1]},
                'equal':{'op':'constant','value':[1]},'less':{'op':'constant','value':[0]}}},
            'issues':['DitherTemporalAA']}
        result=recover(mat,{'a':{},'n':{}})
        self.assertEqual(result['inputs']['normal']['channels'],[0,1,2])
        self.assertEqual(result['inputs']['opacity']['channels'],[3])

    def test_conversion_authors_basic_surface_and_retains_editable_uvs(self):
        with fixture_directory() as root:
            path=test_usd.UsdIntegrationTests().fixture(root)
            data=json.loads(path.read_text())
            data['materials']['mat']['issues']=['Connected Pixel Depth Offset is unsupported unless the captured value is provably zero']
            path.write_text(json.dumps(data))
            scene,report=convert(path)
            self.assertEqual(report['materials']['mat']['backend'],'UsdPreviewSurface')
            self.assertTrue(report['materials']['mat']['basic_surface_fallback'])
            stage=Usd.Stage.Open(str(scene))
            self.assertEqual(UsdShade.Shader(stage.GetPrimAtPath('/World/Looks/Paint/Surface')).GetIdAttr().Get(),'UsdPreviewSurface')
            self.assertEqual(tuple(stage.GetAttributeAtPath('/World/Looks/Paint.inputs:base_color_uv_scale').Get()),(2,3))
