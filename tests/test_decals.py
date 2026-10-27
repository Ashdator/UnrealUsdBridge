import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'UnrealUsdBridge/Resources/Python'))
from ash_unreal_usd601_decals.decals import projection, overlaps, response_channels, compose, prepare, constant
from ash_unreal_usd601_decals.mdl import compile_mdl
from ash_unreal_usd601_decals.usd_writer import convert
from ash_unreal_usd601_decals.decal_controls import DecalControls, SOURCE_KEY
from test_core import fixture_directory, placed_mesh
import test_usd
from pxr import Usd, UsdGeom, UsdShade, Gf


IDENTITY=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]


def decal(name='TestDecal',order=0):
    # Project along X; cover two heights at z=0 and z=50 cm.
    return {'source':name,'name':name,'material':'decalmat','sort_order':order,
            'matrix':[200,0,0,0,0,200,0,0,0,0,200,0,0,0,0,1]}


class DecalTests(unittest.TestCase):
    def test_specular_decal_channel_is_ignored_in_legacy_response(self):
        base={'inputs':{'roughness':constant([.5])}}
        layer={'inputs':{'specular':constant([.2]),'opacity':constant([1])},'decal_channels':['specular']}
        frame=projection(decal())
        included=compose(base,[(decal(),layer,frame)],response_channels(7))
        excluded=compose(base,[(decal(),layer,frame)],response_channels(2))
        self.assertNotIn('specular',included['inputs'])
        self.assertNotIn('specular',excluded['inputs'])
        program,issues=compile_mdl(included,{})
        self.assertFalse(issues)
        self.assertIn('normal_reflectivity:0.08',program['source'])

    def test_partial_decal_keeps_original_prop_section_and_clips_in_world(self):
        with fixture_directory() as root:
            path,data=self.data(root)
            mesh_path=root/'meshes/m.json';mesh=json.loads(mesh_path.read_text())
            mesh['points'] += [[400,0,0],[500,0,0],[400,100,0]]
            mesh['normals'] *= 2;mesh['uvs'][0] *= 2
            mesh['indices'] += [3,5,4];mesh['sections'][0]['face_count']=2
            mesh_path.write_text(json.dumps(mesh));path.write_text(json.dumps(data))
            scene,report=convert(path);stage=Usd.Stage.Open(str(scene))
            actor=placed_mesh(stage,'Actor')
            self.assertEqual([p.GetName() for p in actor.GetChildren()],['section_0'])
            self.assertEqual(list(actor.GetChild('section_0').GetAttribute('indices').Get()),[0,1])
            self.assertEqual(len(actor.GetAttribute('faceVertexCounts').Get()),2)
            self.assertEqual(report['counts']['decal_material_regions'],0)
            self.assertEqual(report['counts']['max_decals_per_material'],1)

    def data(self,root):
        path=test_usd.UsdIntegrationTests().fixture(root)
        d=json.loads(path.read_text()); d['instances'][0]['matrix']=IDENTITY[:]
        second=copy.deepcopy(d['instances'][0]); second.update(source='/Game/Raised',name='Raised')
        second['matrix'][14]=50; d['instances'].append(second)
        outside=copy.deepcopy(second); outside.update(source='/Game/Outside',name='Outside')
        outside['matrix'][12]=1000; d['instances'].append(outside)
        disabled=copy.deepcopy(second); disabled.update(source='/Game/Disabled',name='Disabled',receives_decals=False)
        d['instances'].append(disabled)
        d['materials']['decalmat']={'name':'Stain','source':'/Game/Stain','domain':'decal',
            'decal_channels':['base_color','roughness','normal'],
            'inputs':{'base_color':{'op':'texture','texture':'tex'},'opacity':constant([.7]),
                      'roughness':constant([.2]),'normal':constant([.1,.2,.97])}}
        d['decals']=[decal()]
        return path,d

    def test_projection_axes_units_and_ue_uv_swizzle(self):
        d=decal(); d['matrix'][13]=120
        f=projection(d)
        self.assertEqual(f['center'],[0,-1.2,0])
        self.assertEqual(f['half_size'],[2,2,2])
        self.assertEqual(f['axis_y'],[0,-1,0])
        m=compose({'inputs':{}},[(d,{'inputs':{'base_color':{'op':'texture','texture':'t'}}},f)],['base_color'])
        program,issues=compile_mdl(m,{'t':{'file':'textures/t.png'}})
        self.assertFalse(issues)
        self.assertIn('.z*0.5+0.5)',program['source'])
        self.assertIn('.y*0.5+0.5)',program['source'])
        self.assertIn('state::meters_per_scene_unit()',program['source'])

    def test_zero_size_rejected(self):
        d=decal(); d['matrix'][0]=0
        with self.assertRaisesRegex(ValueError,'zero size'): projection(d)

    def test_two_heights_and_unaffected_shared_material(self):
        with fixture_directory() as root:
            path,d=self.data(root); path.write_text(json.dumps(d))
            scene,report=convert(path)
            s=Usd.Stage.Open(str(scene))
            low=UsdShade.MaterialBindingAPI(placed_mesh(s,'Actor').GetChild('section_0')).ComputeBoundMaterial()[0]
            raised=UsdShade.MaterialBindingAPI(placed_mesh(s,'Raised').GetChild('section_0')).ComputeBoundMaterial()[0]
            outside=UsdShade.MaterialBindingAPI(placed_mesh(s,'Outside').GetChild('section_0')).ComputeBoundMaterial()[0]
            disabled=UsdShade.MaterialBindingAPI(placed_mesh(s,'Disabled').GetChild('section_0')).ComputeBoundMaterial()[0]
            self.assertEqual(low.GetPath(),raised.GetPath())
            self.assertNotEqual(low.GetPath(),outside.GetPath())
            self.assertEqual(outside.GetPath(),disabled.GetPath())
            self.assertEqual(report['counts']['decal_material_variants'],1)
            self.assertEqual(report['counts']['unique_meshes'],1)
            self.assertEqual(report['counts']['mesh_placements'],4)
            self.assertEqual(report['counts']['foliage_instances'],2)
            self.assertEqual(report['counts']['projected_decals'],1)
            self.assertEqual(report['extension_version'],'0.6.6')

    def test_shared_control_edits_and_independent_tiling(self):
        with fixture_directory() as root:
            path,d=self.data(root); path.write_text(json.dumps(d))
            scene,report=convert(path); s=Usd.Stage.Open(str(scene))
            p=s.GetPrimAtPath('/World/Decals/TestDecal')
            sync=DecalControls(s)
            shader=next(x for x in s.Traverse() if any(a.GetCustomDataByKey(SOURCE_KEY)=='/World/Decals/TestDecal.inputs:amount' for a in x.GetAttributes()))
            intensity=next(a for a in shader.GetAttributes() if a.GetCustomDataByKey(SOURCE_KEY)=='/World/Decals/TestDecal.inputs:amount')
            self.assertFalse(intensity.GetConnections())
            self.assertEqual(intensity.GetCustomDataByKey(SOURCE_KEY),'/World/Decals/TestDecal.inputs:amount')
            p.GetAttribute('inputs:amount').Set(.3)
            self.assertAlmostEqual(intensity.Get(),.3)
            sync.close()
            p.GetAttribute('inputs:amount').Set(.6)
            self.assertAlmostEqual(intensity.Get(),.3)
            sources=[p.read_text() for p in (root/'materials').glob('*.mdl')]
            source=next(source for source in sources if 'export BridgeSurfaceData EvaluateBase' in source)
            self.assertIn('state::texture_coordinate(0)',source)
            self.assertTrue(any('state::coordinate_world' in source for source in sources))
            # Dedicated decal coordinates leave the original 2x3 texture tiling intact.
            tiling=[a for p in s.Traverse() for a in p.GetAttributes() if a.GetDisplayName()=='UV 0 Tiling']
            self.assertTrue(tiling);self.assertTrue(all(tuple(a.Get())==(2,3) for a in tiling))

    def test_base_and_decal_parameter_names_are_independent(self):
        with fixture_directory() as root:
            path,d=self.data(root)
            d['materials']['mat']['inputs']['base_color']={'op':'constant','value':[.2],'parameter':'Tiling'}
            d['materials']['decalmat']['inputs']['roughness']={'op':'constant','value':[.7],'parameter':'Tiling'}
            path.write_text(json.dumps(d)); scene,_=convert(path); s=Usd.Stage.Open(str(scene))
            p=s.GetPrimAtPath('/World/Decals/TestDecal')
            self.assertEqual([a.GetName() for a in p.GetAttributes() if a.GetName().startswith('inputs:')],['inputs:amount'])
            shared=p.GetAttribute('inputs:amount')
            queue=[]; sync=DecalControls(s,queue.append)
            targets=[a for prim in s.Traverse() for a in prim.GetAttributes() if a.GetCustomDataByKey(SOURCE_KEY)==str(shared.GetPath())]
            self.assertTrue(targets)
            shared.Set(.4); shared.Set(.8)
            self.assertEqual(len(queue),1)
            self.assertAlmostEqual(targets[0].Get(),1.0)
            queue.pop()()
            self.assertAlmostEqual(targets[0].Get(),.8)
            base=next(a for prim in s.Traverse() if prim.GetName()=='MDL' for a in prim.GetAttributes() if a.GetDisplayName()=='Tiling' and not a.GetCustomDataByKey(SOURCE_KEY))
            self.assertAlmostEqual(base.Get(),.2)
            fixed=[a for prim in s.Traverse() if prim.GetName()=='MDL' for a in prim.GetAttributes() if a.GetDisplayName()=='Tiling' and a.GetMetadata('hidden')]
            self.assertTrue(fixed)
            self.assertTrue(all(a.GetCustomDataByKey('unreal:baseControl') for a in fixed))
            # Source decal parameters are constants; the base control remains live.
            self.assertTrue(any('float4(0.7)' in p.read_text() for p in (root/'materials').glob('*.mdl')))
            sync.close()

    def test_opacity_blends_surface_instead_of_cutting_holes(self):
        f=projection(decal())
        m=compose({'inputs':{'opacity':constant([1])}},[(decal(),{'inputs':{'base_color':constant([1,0,0]),'opacity':constant([0])}},f)],['base_color'])
        self.assertEqual(m['inputs']['opacity'],constant([1]))
        self.assertNotEqual(m['inputs']['base_color']['layers'][0]['alpha'],constant([1]))

    def test_large_receiver_preserves_86_decals_without_depth_failure(self):
        layers=[]
        for i in range(86):
            d=decal('Decal'+str(i),i)
            layers.append((d,{'inputs':{'base_color':constant([.2,.3,.4]),'normal':constant([.1,.2,.97])}},projection(d)))
        mat=compose({'inputs':{}},layers,['base_color','normal'])
        program,issues=compile_mdl(mat,{})
        self.assertFalse(issues)
        self.assertEqual(len(mat['inputs']['base_color']['layers']),86)
        self.assertEqual(len(mat['decal_world_normal']['layers']),86)
        self.assertEqual(sum(p.get('projection_field')=='amount' for p in program['parameters'].values()),86)

    def test_receiver_response_and_sort_order(self):
        self.assertEqual(response_channels(0),())
        with fixture_directory() as root:
            _,d=self.data(root); d['materials']['mat']['decal_response']=2
            d['decals']=[decal('Top',7),decal('Bottom',1)]
            audits,issues=prepare(d,root)
            self.assertFalse(issues)
            variant=d['materials'][d['instances'][0]['materials'][0]]
            self.assertEqual(variant['decal_layers'],['Bottom','Top'])
            self.assertNotIn('decal_world_normal',variant)
            self.assertNotIn('roughness',variant['inputs'])

    def test_unsupported_decal_reported_base_retained(self):
        with fixture_directory() as root:
            path,d=self.data(root)
            d['materials']['decalmat']['issues']=['Custom emissive blend unsupported']
            path.write_text(json.dumps(d)); _,report=convert(path,allow_partial=True)
            self.assertEqual(report['decals'][0]['status'],'unsupported')
            self.assertEqual(report['counts']['decal_material_variants'],0)
            self.assertEqual(report['status'],'partial')

    def test_instancer_uses_instance_world_transforms(self):
        d=decal(); bounds=[(0,100)]*3
        base=IDENTITY[:]; base[12]=1000
        inside=IDENTITY[:]; inside[12]=-1000
        self.assertTrue(overlaps({'matrix':base,'transforms':[inside]},bounds,d))
        self.assertFalse(overlaps({'matrix':base,'transforms':[IDENTITY]},bounds,d))

    def test_projected_normals_use_decal_basis_and_world_blend(self):
        f=projection(decal())
        m=compose({'inputs':{}},[(decal(),{'inputs':{'normal':constant([.1,.2,.97])}},f)],['normal'])
        program,issues=compile_mdl(m,{})
        self.assertFalse(issues)
        self.assertIn('state::transform_normal(state::coordinate_world,state::coordinate_internal',program['source'])
        self.assertIn('_axis_z',program['source'])
        self.assertIn('normal:world_normal',program['source'])
        self.assertIn('material_geometry(normal:world_normal',program['source'])
        self.assertIn('base:dielectric,normal:state::normal()',program['source'])


if __name__=='__main__': unittest.main()
