import json,unittest
import test_usd
from test_core import fixture_directory
from ash_unreal_usd601_decals.usd_writer import convert
from ash_unreal_usd601_decals.decal_controls import DecalControls
from ash_unreal_usd601_decals.leaf_controls import mark
from ash_unreal_usd601_decals.mdl import compile_mdl,compile_function
from pxr import Usd,Gf,UsdShade


class LeafControlsTests(unittest.TestCase):
    def test_leaf_classification_does_not_change_bark_or_instanced_props(self):
        data={'materials':{'leaf':{'name':'Pine_Leaves','foliage':True},
            'bark':{'name':'BirchBark','foliage':True},'rock':{'name':'Rock'},
            'grass':{'name':'Grass_Patch','inputs':{'opacity':{}}},
            'bb':{'name':'Beech_03_BB','inputs':{'opacity':{}}},
            'misspelled':{'name':'MI_MI_beerchLeafes','foliage':False,'two_sided':True},
            'joined_billboard':{'name':'MI_MI_beerchbillboard_03b','inputs':{'opacity':{}}}},'meshes':{},'instances':[],
            'instancers':[{'mesh':'m','materials':['rock'],'name':'FoliageTool'}]}
        mark(data)
        self.assertTrue(data['materials']['leaf']['leaf_surface'])
        self.assertTrue(data['materials']['grass']['leaf_surface'])
        self.assertTrue(data['materials']['bb']['leaf_surface'])
        self.assertTrue(data['materials']['misspelled']['leaf_surface'])
        self.assertEqual(data['materials']['misspelled']['name'],'MI_MI_beerchLeafes')
        self.assertTrue(data['materials']['joined_billboard']['leaf_surface'])
        self.assertFalse(data['materials']['bark']['leaf_surface'])
        self.assertFalse(data['materials']['rock']['leaf_surface'])

    def test_preview_leaf_color_edits_preserve_opacity_and_fixed_uvs(self):
        with fixture_directory() as root:
            path=test_usd.UsdIntegrationTests().fixture(root);data=json.loads(path.read_text())
            data['materials']['mat']['name']='Pine_Leaves'
            data['materials']['mat']['inputs']['opacity']={'op':'mask','channels':[3],
                'input':{'op':'texture','texture':'tex'}}
            data['materials']['mat']['opacity_threshold']=.3333
            path.write_text(json.dumps(data));scene,report=convert(path)
            self.assertEqual(report['materials']['mat']['backend'],'UsdPreviewSurface')
            stage=Usd.Stage.Open(str(scene));sync=DecalControls(stage)
            mat=stage.GetPrimAtPath('/World/Looks/Pine_Leaves')
            self.assertTrue(mat.GetAttribute('inputs:base_color_uv_scale').IsHidden())
            self.assertEqual(tuple(mat.GetAttribute('inputs:base_color_uv_scale').Get()),(2,3))
            image=stage.GetPrimAtPath(str(mat.GetPath())+'/base_color_texture')
            opacity=UsdShade.Shader(stage.GetPrimAtPath(str(mat.GetPath())+'/Surface')).GetInput('opacity').GetConnectedSource()
            mat.GetAttribute('inputs:leaf_tint').Set(Gf.Vec3f(.5,1,.25))
            mat.GetAttribute('inputs:leaf_brightness').Set(2.)
            mat.GetAttribute('inputs:leaf_darkening').Set(.5)
            self.assertEqual(tuple(image.GetAttribute('inputs:scale').Get()),(.5,1,.25,1))
            unchanged=UsdShade.Shader(stage.GetPrimAtPath(str(mat.GetPath())+'/Surface')).GetInput('opacity').GetConnectedSource()
            self.assertEqual(unchanged[0].GetPath(),opacity[0].GetPath())
            self.assertEqual(unchanged[1:],opacity[1:])
            self.assertAlmostEqual(stage.GetAttributeAtPath(str(mat.GetPath())+'/Surface.inputs:opacityThreshold').Get(),.3333,places=6)
            stage.GetRootLayer().Save();sync.close()
            reopened=Usd.Stage.Open(str(scene))
            self.assertEqual(tuple(reopened.GetAttributeAtPath(str(image.GetPath())+'.inputs:scale').Get()),(.5,1,.25,1))

    def test_mdl_leaf_uvs_fixed_color_and_source_parameters_retained(self):
        texture={'op':'texture','texture':'t','uv':{'op':'uv','scale':[2,3]}}
        graph={'op':'multiply','a':texture,'b':{'op':'constant','value':[.6], 'parameter':'Desaturation'}}
        program,issues=compile_mdl({'leaf_surface':True,'inputs':{'base_color':graph}}, {'t':{'file':'t.png'}})
        self.assertFalse(issues)
        self.assertFalse(any(p.get('uv_control') for p in program['parameters'].values()))
        labels={p['label'] for p in program['parameters'].values()}
        self.assertTrue({'Leaf color tint','Leaf brightness','Leaf darkening','Desaturation'}<=labels)
        ordinary,issues=compile_mdl({'inputs':{'base_color':graph}},{'t':{'file':'t.png'}})
        self.assertFalse(issues)
        self.assertTrue(any(p.get('uv_control') for p in ordinary['parameters'].values()))
        function=compile_function(graph,{'t':{'file':'t.png'}},'color',expose_uv=False,leaf_color=True)
        self.assertIn('leaf_brightness',function['source'])
        self.assertFalse(any(p.get('uv_control') for p in function['parameters'].values()))

    def test_omnipbr_leaf_hides_normal_uv_controls_and_exposes_color(self):
        with fixture_directory() as root:
            path=test_usd.UsdIntegrationTests().fixture(root);data=json.loads(path.read_text())
            mat=data['materials']['mat'];mat.update(name='Pine_Leaves',foliage=True)
            mat['inputs']['normal']={'op':'mask','channels':[0,1,2],
                'input':{'op':'texture','texture':'tex','normal_map':True}}
            path.write_text(json.dumps(data));scene,report=convert(path)
            self.assertEqual(report['materials']['mat']['backend'],'OmniPBR')
            stage=Usd.Stage.Open(str(scene))
            stock=stage.GetPrimAtPath('/World/Looks/Pine_Leaves/OmniPBR')
            self.assertTrue(stock.GetAttribute('inputs:texture_scale').IsHidden())
            self.assertEqual(tuple(stock.GetAttribute('inputs:texture_scale').Get()),(1,1))
            graph=stage.GetPrimAtPath('/World/Looks/Pine_Leaves/base_color_graph')
            self.assertEqual(tuple(graph.GetAttribute('inputs:leaf_tint').Get()),(1,1,1))
            self.assertEqual(graph.GetAttribute('inputs:leaf_brightness').Get(),1.)
            self.assertEqual(graph.GetAttribute('inputs:leaf_darkening').Get(),0.)
            self.assertFalse(any('Tiling' in a.GetDisplayName() and not a.IsHidden() for a in graph.GetAttributes()))
