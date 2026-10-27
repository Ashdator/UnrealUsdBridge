import unittest
import numpy as np
from ash_unreal_usd601_decals.decal_regions import spatial_regions
from ash_unreal_usd601_decals.shared_base import resolve
from ash_unreal_usd601_decals.decals import projection,constant
from ash_unreal_usd601_decals.mdl import compile_mdl
from ash_unreal_usd601_decals.mdl_sharing import canonical_program
from test_decals import decal


class LocalProjectionTests(unittest.TestCase):
    def test_texture_display_names_do_not_duplicate_shader_definitions(self):
        programs=[]
        for label in ('Wood_Old_BaseColor','Metal_Barrel_BaseColor'):
            material={'inputs':{'base_color':{'op':'texture','texture':'color','color_space':'sRGB'}}}
            program,issues=compile_mdl(material,{'color':{'file':'textures/'+label+'.png','source':label}})
            self.assertFalse(issues);programs.append(canonical_program(program))
        self.assertEqual(programs[0]['source'],programs[1]['source'])
        textures=[next(p for p in pr['parameters'].values() if p['type']=='texture_2d') for pr in programs]
        self.assertNotEqual(textures[0]['label'],textures[1]['label'])
        self.assertNotEqual(textures[0]['file'],textures[1]['file'])

    def test_different_projector_boxes_share_program_but_not_placement_values(self):
        programs=[]
        for i in range(2):
            d=decal('Source'+str(i));d['matrix'][12]=i*300
            frame=projection(d);frame.update(fixed_transform=True,parameterized_transform=True)
            material,_=resolve({'inputs':{'base_color':constant([.2,.4,.6])}}, {},
                               [(d,{'inputs':{'base_color':constant([1,0,0])}},frame)])
            program,issues=compile_mdl(material,{})
            self.assertFalse(issues);programs.append(canonical_program(program))
        self.assertEqual(programs[0]['source'],programs[1]['source'])
        centers=[next(p['value'] for p in pr['parameters'].values() if p.get('projection_field')=='center') for pr in programs]
        self.assertNotEqual(*centers)
        self.assertIn('anno::hidden()',programs[0]['source'])

    def test_spatial_partition_covers_every_face_and_its_actual_projectors(self):
        points=[];triangles=[]
        for i in range(256):
            points.extend([[i,0,0],[i,1,0],[i+.5,0,0]]);triangles.append([i*3,i*3+1,i*3+2])
        masks=[np.arange(256)//16==i for i in range(16)]
        regions=spatial_regions(np.array(points),np.array(triangles),masks,100,budget=8)
        seen=[]
        for active,faces in regions:
            self.assertLessEqual(len(active),8)
            for face in faces:
                seen.append(face)
                actual={i for i,mask in enumerate(masks) if mask[face-100]}
                self.assertTrue(actual<=set(active))
        self.assertEqual(sorted(seen),list(range(100,356)))

    def test_nearby_mask_combinations_do_not_require_one_material_per_combination(self):
        faces=np.tile([[0,1,2]],(128,1));points=np.array([[0,0,0],[1,0,0],[0,1,0]])
        masks=[(np.arange(128)>>i)&1==1 for i in range(8)]
        regions=spatial_regions(points,faces,masks,0,budget=8)
        self.assertLess(len(regions),128)
        self.assertEqual(sum(len(ids) for _,ids in regions),128)

    def test_genuine_nine_layer_stack_is_preserved(self):
        points=np.array([[0,0,0],[1,0,0],[0,1,0]])
        regions=spatial_regions(points,np.array([[0,1,2]]),[np.array([True])]*9,0,budget=8)
        self.assertEqual(regions,[(list(range(9)),[0])])
