import json, unittest
from pathlib import Path
from test_core import constant, binary, fixture_directory
import test_usd
import test_decals
from test_usd import Usd, UsdShade
from ash_unreal_usd601_decals.emission import uses_emission, prepare
from ash_unreal_usd601_decals.graph import compile_material, Constant, Sample
from ash_unreal_usd601_decals.mdl import compile_mdl
from ash_unreal_usd601_decals.mdl_sharing import canonical_program
from ash_unreal_usd601_decals.omnipbr import compile_omnipbr
from ash_unreal_usd601_decals.usd_writer import convert
from ash_unreal_usd601_decals.decals import compose


class EmissionTests(unittest.TestCase):
    def test_unused_black_does_not_change_material(self):
        mat={'inputs':{'emissive':constant([0,0,0])}}
        prepare(mat)
        self.assertNotIn('emissive',mat['inputs'])
        program,issues=compile_mdl(mat,{})
        self.assertFalse(issues)
        self.assertNotIn('diffuse_edf',program['source'])
        self.assertFalse(any(p.get('emission_control') for p in program['parameters'].values()))

    def test_hdr_constant_and_zero_parameter_are_retained(self):
        for node in [constant([12,.5,2]),dict(constant([0,0,0]),parameter='Glow Color')]:
            mat={'inputs':{'emissive':node}}
            prepare(mat)
            self.assertTrue(uses_emission(mat))
            values,issues=compile_material(mat)
            self.assertFalse(issues)
            self.assertEqual(values['emissive'].value,tuple(node['value']))

    def test_emission_texture_preserves_hdr_multiplier_uv_and_colorspace(self):
        tex={'op':'texture','texture':'glow','channels':[0,1,2],'uv':{'op':'uv','channel':1,'scale':[2,3]},'color_space':'sRGB'}
        mat={'inputs':{'emissive':binary('multiply',tex,constant([8,4,2]))}}
        values,issues=compile_material(mat)
        self.assertFalse(issues)
        self.assertIsInstance(values['emissive'],Sample)
        self.assertEqual(values['emissive'].scale[:3],(8,4,2))
        self.assertEqual(values['emissive'].uv.channel,1)
        self.assertEqual(values['emissive'].uv.scale,(2,3))
        self.assertEqual(values['emissive'].color_space,'sRGB')

    def test_complex_emission_has_graph_and_live_gain(self):
        mat={'inputs':{'emissive':binary('power',dict(constant([2]),parameter='Glow'),constant([2]))}}
        program,issues=compile_mdl(mat,{})
        self.assertFalse(issues)
        self.assertIn('df::diffuse_edf()',program['source'])
        self.assertIn('math::pow',program['source'])
        self.assertEqual(program['parameters']['unreal_emissive_strength']['value'],1)
        shared=canonical_program(program)
        self.assertIn('anno::in_group("Emission")',shared['source'])
        self.assertEqual(sum(p.get('emission_control',False) for p in shared['parameters'].values()),1)

    def test_unsupported_emission_is_reported(self):
        mat={'inputs':{'emissive':{'op':'unsupported','reason':'Custom glow HLSL'}}}
        prepare(mat)
        _,issues=compile_mdl(mat,{})
        self.assertTrue(any('Custom glow HLSL' in i for i in issues))

    def test_omnipbr_compiles_emission_function_with_distinct_uv(self):
        tex={'op':'texture','texture':'glow','uv':{'op':'uv','channel':1,'scale':[4,5]},'color_space':'sRGB'}
        program,issues=compile_omnipbr({'inputs':{'emissive':binary('multiply',tex,constant([6]))}},
                                     {'glow':{'file':'textures/glow.png'}})
        self.assertFalse(issues)
        self.assertIn('emissive',program['functions'])
        self.assertIn(1,program['uv_channels'])

    def test_emissive_decal_adds_without_erasing_receiver_glow(self):
        frame={'id':'GlowSticker','label':'GlowSticker','center':[0,0,0],'half_size':[1,1,1],
               'axis_x':[1,0,0],'axis_y':[0,1,0],'axis_z':[0,0,1],'fixed_transform':True}
        base={'inputs':{'emissive':constant([2,0,0])}}
        definition={'inputs':{'emissive':constant([0,5,0]),'opacity':constant([.5])},'decal_channels':['emissive']}
        result=compose(base,[({'source':'GlowSticker'},definition,frame)],('base_color',))
        node=result['inputs']['emissive']
        self.assertEqual(node['op'],'add')
        self.assertEqual(node['a']['value'],[2,0,0])
        program,issues=compile_mdl(result,{})
        self.assertFalse(issues)
        self.assertTrue(any(p.get('projection_field')=='amount' for p in program['parameters'].values()))


@unittest.skipIf(Usd is None,'USD required')
class EmissionUsdTests(unittest.TestCase):
    def fixture(self,root,emission,**fields):
        path=test_usd.UsdIntegrationTests().fixture(root)
        data=json.loads(path.read_text())
        data['materials']['mat']['inputs']['emissive']=emission
        data['materials']['mat'].update(fields)
        path.write_text(json.dumps(data))
        return path

    def test_preview_hdr_color_connection(self):
        with fixture_directory() as root:
            path,report=convert(self.fixture(root,constant([9,.25,2])))
            stage=Usd.Stage.Open(str(path))
            self.assertEqual(report['materials']['mat']['backend'],'UsdPreviewSurface')
            self.assertTrue(report['materials']['mat']['emissive'])
            attr=stage.GetAttributeAtPath('/World/Looks/Paint.inputs:emissiveColor')
            self.assertEqual(tuple(attr.Get()),(9,.25,2))
            self.assertEqual(attr.GetDisplayGroup(),'Emission')
            self.assertTrue(stage.GetAttributeAtPath('/World/Looks/Paint/Surface.inputs:emissiveColor').GetConnections())

    def test_preview_texture_retained_gain_and_uv(self):
        with fixture_directory() as root:
            tex={'op':'texture','texture':'tex','color_space':'raw','uv':{'op':'uv','scale':[3,2]}}
            path,report=convert(self.fixture(root,binary('multiply',tex,constant([8]))))
            stage=Usd.Stage.Open(str(path))
            self.assertEqual(report['materials']['mat']['backend'],'UsdPreviewSurface')
            self.assertEqual(tuple(stage.GetAttributeAtPath('/World/Looks/Paint.inputs:emissive_scale').Get())[:3],(8,8,8))
            self.assertEqual(tuple(stage.GetAttributeAtPath('/World/Looks/Paint.inputs:emissive_uv_scale').Get()),(3,2))
            self.assertEqual(stage.GetAttributeAtPath('/World/Looks/Paint/emissive_texture.inputs:sourceColorSpace').Get(),'raw')
            self.assertTrue(stage.GetAttributeAtPath('/World/Looks/Paint/emissive_texture.inputs:scale').GetConnections())

    def test_omnipbr_enables_emission_and_unit_gain(self):
        with fixture_directory() as root:
            path,report=convert(self.fixture(root,constant([6,1,.2]),foliage=True))
            stage=Usd.Stage.Open(str(path))
            self.assertEqual(report['materials']['mat']['backend'],'OmniPBR')
            self.assertTrue(stage.GetAttributeAtPath('/World/Looks/Paint/OmniPBR.inputs:enable_emission').Get())
            self.assertEqual(stage.GetAttributeAtPath('/World/Looks/Paint/OmniPBR.inputs:emissive_intensity').Get(),1)
            self.assertAlmostEqual(stage.GetAttributeAtPath('/World/Looks/Paint/OmniPBR.inputs:emissive_color').Get()[0],6)

    def test_unlit_has_no_scattering_and_original_emission(self):
        with fixture_directory() as root:
            path,report=convert(self.fixture(root,constant([6,1,.2]),unlit=True))
            stage=Usd.Stage.Open(str(path))
            self.assertEqual(report['materials']['mat']['backend'],'MDL')
            mdl=list((root/'materials').glob('*.mdl'))[0].read_text()
            self.assertIn('bsdf scattering = bsdf();',mdl)
            self.assertIn('df::diffuse_edf()',mdl)

    def test_disabled_black_emission_omitted(self):
        with fixture_directory() as root:
            path,report=convert(self.fixture(root,constant([0,0,0])))
            stage=Usd.Stage.Open(str(path))
            self.assertFalse(report['materials']['mat']['emissive'])
            self.assertFalse(stage.GetAttributeAtPath('/World/Looks/Paint/Surface.inputs:emissiveColor'))

    def test_emission_only_world_decal_receives_shared_intensity(self):
        with fixture_directory() as root:
            path,data=test_decals.DecalTests().data(root)
            data['materials']['decalmat'].update(decal_channels=['emissive'],
                inputs={'emissive':constant([0,12,0]),'opacity':constant([.75])})
            path.write_text(json.dumps(data))
            scene,report=convert(path)
            self.assertEqual(report['decals'][0]['status'],'projected')
            stage=Usd.Stage.Open(str(scene))
            from ash_unreal_usd601_decals.decal_controls import DecalControls, SOURCE_KEY
            sync=DecalControls(stage)
            control=stage.GetPrimAtPath('/World/Decals').GetChildren()[0].GetAttribute('inputs:amount')
            targets=[a for p in stage.Traverse() for a in p.GetAttributes() if a.GetCustomDataByKey(SOURCE_KEY)]
            self.assertTrue(targets)
            control.Set(0);sync.flush()
            self.assertTrue(all(a.Get()==0 for a in targets));sync.close()
            self.assertTrue(any(m['emissive'] for m in report['materials'].values()))

    def test_unsupported_emissive_does_not_silently_convert_as_dark_material(self):
        with fixture_directory() as root:
            manifest=self.fixture(root,{'op':'unsupported','reason':'Unknown emission node'})
            with self.assertRaisesRegex(ValueError,'unsupported features'):
                convert(manifest)
            report=json.loads((root/'conversion-report.json').read_text())
            self.assertTrue(any('Unknown emission node' in i for i in report['materials']['mat']['issues']))
