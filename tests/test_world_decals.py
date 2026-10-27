import copy, json, unittest
from pxr import Usd, UsdShade
from test_core import fixture_directory, placed_mesh
import test_decals
from test_decals import IDENTITY, decal
from ash_unreal_usd601_decals.world_decals import prepare, MAX_SHARED_DECALS
from ash_unreal_usd601_decals.usd_writer import convert
from ash_unreal_usd601_decals.decals import compose,projection,constant
from ash_unreal_usd601_decals.mdl import compile_mdl
from ash_unreal_usd601_decals.mdl_sharing import canonical_program


class SharedWorldTests(unittest.TestCase):
    def test_empty_slots_convert_when_decals_are_disabled(self):
        with fixture_directory() as root:
            path,data=self.distributed(root,1)
            data['instances'][0]['materials']=['']
            path.write_text(json.dumps(data))
            scene,report=convert(path,allow_partial=True,include_decals=False)
            stage=Usd.Stage.Open(str(scene))
            subset=placed_mesh(stage,'Tire0').GetChild('section_0')
            bound=UsdShade.MaterialBindingAPI(subset).ComputeBoundMaterial()[0]
            self.assertTrue(bound)
            self.assertIn('BridgeMissingMaterial',str(bound.GetPath()))
            self.assertEqual(report['counts']['projected_decals'],0)
            self.assertEqual(report['counts']['shared_base_materials'],0)
            scope=stage.GetPrimAtPath('/World/Decals')
            self.assertFalse(scope and scope.GetChildren())

    def test_missing_static_and_instanced_slots_keep_geometry_and_fallback(self):
        with fixture_directory() as root:
            path,data=self.distributed(root,1)
            empty=copy.deepcopy(data['instances'][0])
            empty.update(source='/Game/Empty',name='Empty',materials=[''])
            instanced=copy.deepcopy(empty)
            instanced.update(source='/Game/UnassignedInstances',name='UnassignedInstances',
                             materials=['unknown-material'],transforms=[IDENTITY,IDENTITY])
            data['instances'].append(empty);data['instancers']=[instanced]
            path.write_text(json.dumps(data))
            scene,report=convert(path,allow_partial=True)
            stage=Usd.Stage.Open(str(scene))
            empty_prim=placed_mesh(stage,'Empty').GetChild('section_0')
            fallback=UsdShade.MaterialBindingAPI(empty_prim).ComputeBoundMaterial()[0]
            self.assertTrue(fallback)
            self.assertIn('BridgeMissingMaterial',str(fallback.GetPath()))
            prototypes=stage.GetPrimAtPath('/World/Foliage').GetChildren()[0].GetRelationship('prototypes').GetTargets()
            self.assertEqual(len(prototypes),1)
            bound=UsdShade.MaterialBindingAPI(stage.GetPrimAtPath(str(prototypes[0])+'/section_0')).ComputeBoundMaterial()[0]
            self.assertEqual(bound.GetPath(),fallback.GetPath())
            self.assertEqual(report['counts']['foliage_instances'],2)
            self.assertEqual(report['counts']['projected_decals'],1)
            self.assertTrue(any('missing material in slot' in issue for issue in report['issues']))

    def test_missing_slot_retains_binding_in_complete_decal_partition(self):
        with fixture_directory() as root:
            count=MAX_SHARED_DECALS+1
            path,data=self.distributed(root,count)
            mesh=json.loads((root/'meshes/m.json').read_text())
            points=[];indices=[];uvs=[]
            for i in range(count+1):
                points.extend([[i*1000,0,0],[i*1000+100,0,0],[i*1000,100,0]])
                indices.extend([i*3,i*3+2,i*3+1]);uvs.extend([[0,0],[1,0],[0,1]])
            mesh.update(points=points,indices=indices,normals=[[0,0,1]]*len(points),uvs=[uvs],
                        sections=[{'slot':0,'first_face':0,'face_count':count},
                                  {'slot':1,'first_face':count,'face_count':1}])
            (root/'meshes/m.json').write_text(json.dumps(mesh))
            data['instances']=data['instances'][:1];data['instances'][0]['materials']=['mat','']
            path.write_text(json.dumps(data))
            scene,_=convert(path,allow_partial=True)
            stage=Usd.Stage.Open(str(scene))
            subsets=UsdShade.MaterialBindingAPI(placed_mesh(stage,'Tire0')).GetMaterialBindSubsets()
            target=[subset for subset in subsets if list(subset.GetIndicesAttr().Get())==[count]]
            self.assertEqual(len(target),1)
            bound=UsdShade.MaterialBindingAPI(target[0]).ComputeBoundMaterial()[0]
            self.assertTrue(bound)
            self.assertIn('BridgeMissingMaterial',str(bound.GetPath()))

    def test_fixed_projectors_share_texture_handles_but_keep_distinct_uvs_and_controls(self):
        layers=[]
        for i in range(2):
            d=decal('Repeated'+str(i),i);d['matrix'][12]=i*10
            frame=projection(d);frame['fixed_transform']=True
            image={'op':'texture','texture':'normal','color_space':'raw','normal_map':True}
            layers.append((d,{'inputs':{'normal':{'op':'mask','input':image,'channels':[0,1,2]}}},frame))
        program,issues=compile_mdl(compose({'inputs':{}},layers,['normal']),{'normal':{'file':'textures/normal.png'}})
        self.assertFalse(issues)
        textures=[p for p in program['parameters'].values() if p['type']=='texture_2d']
        self.assertEqual(len(textures),1)
        self.assertTrue(textures[0]['shared_projection_texture'])
        self.assertEqual(len([p for p in program['parameters'].values() if p.get('projection_field')=='amount']),2)
        self.assertEqual(program['source'].count('tex::lookup_float4('),2)
        self.assertIn('material_geometry(normal:world_normal',program['source'])
        shared=canonical_program(program)
        line=next(line for line in shared['source'].splitlines() if 'uniform texture_2d' in line)
        self.assertIn('anno::hidden()',line)
        self.assertIn('anno::in_group("Decals")',line)

    def test_fixed_transform_retains_only_live_intensity_and_texture_inputs(self):
        d=decal('Fixed',0);frame=projection(d);frame['fixed_transform']=True
        color=dict(constant([1,0,0]),parameter='Unused decal color')
        program,issues=compile_mdl(compose({'inputs':{}},[(d,{'inputs':{'base_color':color}},frame)],['base_color']),{})
        self.assertFalse(issues)
        self.assertEqual([p.get('projection_field') for p in program['parameters'].values()],['amount'])
        self.assertIn('float3 decal_',program['source'])
        self.assertIn('state::coordinate_world',program['source'])

    def test_generation_supports_64_distinct_projection_controls(self):
        layers=[]
        for i in range(64):
            d=decal('Slot'+str(i),i)
            layers.append((d,{'inputs':{'base_color':constant([1,0,0]),'opacity':constant([1])}},projection(d)))
        program,issues=compile_mdl(compose({'inputs':{}},layers,['base_color']),{})
        self.assertFalse(issues)
        amounts=[p for p in program['parameters'].values() if p.get('projection_field')=='amount']
        self.assertEqual(len(amounts),64)
        self.assertEqual({p['projection_id'] for p in amounts},{'Slot'+str(i) for i in range(64)})

    def distributed(self, root, count):
        path, data = test_decals.DecalTests().data(root)
        template = copy.deepcopy(data['instances'][0])
        data['instances'] = []; data['instancers'] = []; data['decals'] = []
        for i in range(count):
            inst = copy.deepcopy(template)
            inst.update(name='Tire'+str(i), source='/Game/Tire'+str(i))
            inst['matrix'][12] = i*1000
            data['instances'].append(inst)
            d = decal('Stain'+str(i), count-i)
            d['matrix'][12] = i*1000
            data['decals'].append(d)
        return path, data

    def test_thirteen_tires_share_one_clean_base_and_only_local_decal_controls(self):
        with fixture_directory() as root:
            path, data = self.distributed(root, 13)
            path.write_text(json.dumps(data))
            scene, report = convert(path)
            stage = Usd.Stage.Open(str(scene))
            paths = {UsdShade.MaterialBindingAPI(placed_mesh(stage,'Tire'+str(i)).GetChild('section_0')).ComputeBoundMaterial()[0].GetPath() for i in range(13)}
            self.assertEqual(len(paths), 13)
            masters={stage.GetPrimAtPath(p).GetCustomDataByKey('unreal:baseMaterial') for p in paths}
            self.assertEqual(len(masters),1)
            self.assertEqual(report['counts']['shared_base_materials'],1)
            self.assertEqual(report['counts']['max_decals_per_material'], 1)
            self.assertEqual(report['counts']['projected_decals'], 13)
            self.assertEqual(report['counts']['unique_meshes'], 1)
            self.assertEqual(report['counts']['decal_material_regions'], 0)
            layers = [m['decal_layers'] for m in report['materials'].values()]
            self.assertEqual({key for group in layers for key in group}, {'Stain'+str(i) for i in range(13)})
            order = {d['source']:d['sort_order'] for d in data['decals']}
            self.assertTrue(all(group == sorted(group,key=order.__getitem__) for group in layers))
            self.assertEqual(len(stage.GetPrimAtPath('/World/Decals').GetChildren()), 13)

    def test_distributed_decals_create_bounded_groups_without_drops(self):
        with fixture_directory() as root:
            count = MAX_SHARED_DECALS + 1
            _, data = self.distributed(root, count)
            audits, issues = prepare(data, root)
            self.assertFalse(issues)
            self.assertEqual(sum(a['status']=='projected' for a in audits), count)
            groups = data['world_decal_groups']
            self.assertEqual(len(groups), count)
            self.assertTrue(all(len(g['decals'])==1 for g in groups))
            self.assertTrue(all(len(g['decals'])<=MAX_SHARED_DECALS for g in groups))
            self.assertEqual({d for g in groups for d in g['decals']}, {d['source'] for d in data['decals']})

    def test_disabled_and_vegetation_receivers_do_not_join_shared_groups(self):
        with fixture_directory() as root:
            _, data = self.distributed(root, 2)
            disabled = copy.deepcopy(data['instances'][0])
            disabled.update(source='/Game/Disabled', name='Disabled', receives_decals=False)
            plant = copy.deepcopy(disabled)
            plant.update(source='/Game/Plant', name='Plant', vegetation=True, receives_decals=True)
            data['instances'].extend([disabled, plant])
            prepare(data, root)
            self.assertEqual(disabled['materials'], ['mat'])
            self.assertEqual(plant['materials'], ['mat'])
            self.assertNotEqual(data['instances'][0]['materials'], ['mat'])

    def test_receivers_outside_boxes_keep_the_base_without_decal_cost(self):
        with fixture_directory() as root:
            _, data = test_decals.DecalTests().data(root)
            prepare(data, root)
            self.assertEqual(data['instances'][0]['materials'],data['instances'][1]['materials'])
            self.assertEqual(data['instances'][2]['materials'],['mat'])
            self.assertEqual(data['instances'][2]['materials'],data['instances'][3]['materials'])
            self.assertNotEqual(data['instances'][0]['materials'],data['instances'][2]['materials'])

    def test_spatial_groups_keep_separated_receivers_local(self):
        with fixture_directory() as root:
            _, data = self.distributed(root, 17)
            prepare(data,root)
            groups=data['world_decal_groups']
            self.assertEqual(len(groups),17)
            for group in groups:
                positions=[int(source.rsplit('Tire',1)[1]) for source in group['receivers']]
                self.assertEqual(max(positions)-min(positions),0)
            self.assertEqual({key for group in groups for key in group['decals']},{d['source'] for d in data['decals']})

    def test_true_overlap_is_preserved_above_the_group_target(self):
        with fixture_directory() as root:
            _, data = self.distributed(root,1)
            data['decals']=[decal('Overlap'+str(i),i) for i in range(MAX_SHARED_DECALS+1)]
            audits,issues=prepare(data,root)
            self.assertFalse(issues)
            self.assertEqual(sum(a['status']=='projected' for a in audits),MAX_SHARED_DECALS+1)
            groups=data['world_decal_groups']
            self.assertEqual(len(groups),1)
            self.assertTrue(groups[0]['over_budget'])
            self.assertEqual(len(groups[0]['decals']),MAX_SHARED_DECALS+1)

    def test_split_prop_retains_its_unaffected_original_section(self):
        with fixture_directory() as root:
            count=MAX_SHARED_DECALS+1
            path,data=self.distributed(root,count)
            points=[];indices=[];uvs=[]
            for i in range(count+1):
                points.extend([[i*1000,0,0],[i*1000+100,0,0],[i*1000,100,0]])
                indices.extend([i*3,i*3+2,i*3+1]);uvs.extend([[0,0],[1,0],[0,1]])
            mesh=json.loads((root/'meshes/m.json').read_text())
            mesh.update(points=points,indices=indices,normals=[[0,0,1]]*len(points),uvs=[uvs],
                        sections=[{'slot':0,'first_face':0,'face_count':count},
                                  {'slot':1,'first_face':count,'face_count':1}])
            (root/'meshes/m.json').write_text(json.dumps(mesh))
            data['instances']=data['instances'][:1];data['instances'][0]['materials']=['mat','mat']
            prepare(data,root)
            regions=data['instances'][0]['decal_sections']
            self.assertEqual(sorted(face for region in regions for face in region['faces']),list(range(count+1)))
            original=[region for region in regions if region['section']==1]
            self.assertEqual(len(original),1)
            self.assertEqual(original[0]['material'],'mat')

    def test_prop_overflow_uses_regions_instead_of_dropping_decals(self):
        with fixture_directory() as root:
            count = MAX_SHARED_DECALS + 1
            path, data = self.distributed(root, count)
            mesh_path = root/'meshes/m.json'; mesh=json.loads(mesh_path.read_text())
            points=[]; indices=[]; uvs=[]
            for i in range(count):
                points.extend([[i*1000,0,0],[i*1000+100,0,0],[i*1000,100,0]])
                indices.extend([i*3,i*3+2,i*3+1]);uvs.extend([[0,0],[1,0],[0,1]])
            mesh.update(points=points,indices=indices,normals=[[0,0,1]]*len(points),uvs=[uvs],
                        sections=[{'slot':0,'first_face':0,'face_count':count}])
            mesh_path.write_text(json.dumps(mesh));data['instances']=data['instances'][:1]
            path.write_text(json.dumps(data)); scene, report=convert(path)
            self.assertEqual(report['counts']['projected_decals'],count)
            self.assertLessEqual(report['counts']['max_decals_per_material'],MAX_SHARED_DECALS)
            self.assertGreater(report['counts']['decal_material_regions'],0)
            stage=Usd.Stage.Open(str(scene));mesh_prim=placed_mesh(stage,'Tire0')
            self.assertEqual(list(mesh_prim.GetAttribute('faceVertexIndices').Get()),indices)
