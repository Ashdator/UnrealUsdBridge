import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'UnrealUsdBridge/Resources/Python'))
from ash_unreal_usd601_decals.decal_regions import np, performance_regions
from ash_unreal_usd601_decals.decals import compose, projection
from ash_unreal_usd601_decals.mdl import compile_mdl
from test_decals import decal, constant


class PerformanceTests(unittest.TestCase):
    def test_sparse_regions_preserve_faces_and_every_intersection(self):
        points=[]
        for i in range(512):points.extend([[i,0,0],[i+.4,0,0],[i,.4,0]])
        points=np.asarray(points)*100;triangles=np.arange(len(points)).reshape(-1,3)
        masks=[np.zeros(512,dtype=bool) for _ in range(3)]
        for mask,(a,b) in zip(masks,[(0,128),(192,256),(384,448)]):mask[a:b]=True
        regions,saving=performance_regions(points,triangles,masks,7,8,np.eye(4))
        self.assertLessEqual(len(regions),4)
        self.assertGreaterEqual(saving,.40)
        self.assertEqual(sorted(f for _,faces in regions for f in faces),list(range(7,519)))
        for active,faces in regions:
            for face in faces:
                self.assertTrue(set(np.flatnonzero(np.stack(masks)[:,face-7])).issubset(active))

    def test_actual_overlaps_and_small_meshes_keep_single_section(self):
        points=np.asarray([[0,0,0],[100,0,0],[0,100,0]])
        triangles=np.tile([[0,1,2]],(256,1))
        masks=[np.ones(256,dtype=bool) for _ in range(4)]
        self.assertIsNone(performance_regions(points,triangles,masks,0,8,np.eye(4)))
        self.assertIsNone(performance_regions(points,triangles[:20],[m[:20] for m in masks],0,8,np.eye(4)))

    def test_projected_samples_guarded_and_base_samples_unconditional(self):
        frame=dict(projection(decal()),fixed_transform=True,parameterized_transform=True,cull_texture_samples=True)
        base={'inputs':{'base_color':{'op':'texture','texture':'base','color_space':'sRGB'}}}
        normal={'op':'texture','texture':'normal','normal_map':True}
        layer={'inputs':{'base_color':{'op':'texture','texture':'color','color_space':'sRGB'},
                         'normal':normal,'opacity':constant([1])}}
        program,issues=compile_mdl(compose(base,[(decal(),layer,frame)],['base_color','normal']),
            {key:{'file':key+'.png'} for key in ['base','normal','color']})
        self.assertFalse(issues)
        lookups=[line for line in program['source'].splitlines() if 'tex::lookup_float4(' in line]
        self.assertEqual(len(lookups),3)
        self.assertEqual(sum('? tex::lookup_float4' in line for line in lookups),2)
        self.assertTrue(any(': float4(0.5,0.5,1.0,1.0)' in line for line in lookups))


if __name__=='__main__':unittest.main()
