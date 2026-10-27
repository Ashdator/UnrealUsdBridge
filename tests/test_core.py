import json
from pathlib import Path
import sys
import tempfile
import unittest
import contextlib
import shutil
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'UnrealUsdBridge/Resources/Python'))
from ash_unreal_usd601_decals.graph import Constant, Sample, UV, evaluate, compile_material, Unsupported
from ash_unreal_usd601_decals.mdl import compile_mdl


def constant(value): return {'op':'constant','value':value}
def binary(op,a,b): return {'op':op,'a':a,'b':b}

def placed_mesh(stage, name):
    """Find a source placement's mesh, whether individual or a shared prototype."""
    from pxr import UsdGeom
    prim=stage.GetPrimAtPath('/World/Objects/'+name)
    if prim:return prim
    for candidate in stage.Traverse():
        if not candidate.IsA(UsdGeom.PointInstancer):continue
        names=candidate.GetCustomDataByKey('unreal:instanceNames')
        if names is None or name not in names:continue
        index=list(names).index(name)
        pi=UsdGeom.PointInstancer(candidate)
        target=pi.GetPrototypesRel().GetTargets()[pi.GetProtoIndicesAttr().Get()[index]]
        return stage.GetPrimAtPath(target)
    raise AssertionError('Missing placement '+name)

@contextlib.contextmanager
def fixture_directory():
    parent=(Path.cwd()/'work'/'test-fixtures').resolve()
    parent.mkdir(parents=True,exist_ok=True)
    folder=parent/uuid.uuid4().hex
    folder.mkdir()
    try:
        yield folder
    finally:
        resolved=folder.resolve()
        if resolved.parent != parent:
            raise RuntimeError('Refusing to clean a fixture outside its test directory')
        shutil.rmtree(resolved)


class GraphTests(unittest.TestCase):
    def test_tiling_and_offset(self):
        uv=binary('add',binary('multiply',{'op':'uv','channel':1,'scale':[2,3]},constant([4,5])),constant([0.25,-0.1]))
        self.assertEqual(evaluate(uv),UV(1,(8,15),(0.25,-0.1)))

    def test_tint_keeps_original_texture(self):
        tex={'op':'texture','texture':'original','channels':[0,1,2]}
        result=evaluate(binary('multiply',tex,constant([0.5,0.25,2])))
        self.assertEqual(result.texture,'original')
        self.assertEqual(result.scale,(0.5,0.25,2,1))

    def test_packed_roughness_and_gloss_inversion(self):
        tex={'op':'texture','texture':'packed'}
        node={'op':'one_minus','input':{'op':'mask','input':tex,'channels':[1]}}
        result=evaluate(node)
        self.assertEqual(result.channels,(1,))
        self.assertEqual(result.scale[1],-1)
        self.assertEqual(result.bias[1],1)

    def test_normals_and_import_green_flip(self):
        node={'op':'texture','texture':'normal','normal_map':True}
        self.assertEqual(evaluate(node).scale,(2,-2,2,1))
        self.assertEqual(evaluate(dict(node,flip_green=True)).scale,(2,2,2,1))

    def test_rejects_two_texture_multiply(self):
        with self.assertRaises(Unsupported):
            evaluate(binary('multiply',{'op':'texture','texture':'a'},{'op':'texture','texture':'b'}))

    def test_rejects_invalid_uv_and_swizzle(self):
        with self.assertRaises(Unsupported): evaluate({'op':'uv','channel':-1})
        _,issues=compile_material({'inputs':{'base_color':{'op':'texture','texture':'a','channels':[2,1,0]}}})
        self.assertTrue(issues)

    def test_constants_and_division(self):
        self.assertEqual(evaluate(binary('divide',constant([4,6]),constant(2))),Constant((2,3)))
        with self.assertRaises(Unsupported): evaluate(binary('divide',constant(1),constant(0)))

    def test_nested_instance_values_already_resolved(self):
        node={'op':'multiply','a':{'op':'uv'},'b':dict(constant(7),parameter='Tiling')}
        self.assertEqual(evaluate(node).scale,(7,7))

    def test_identity_color_operations_keep_texture_and_nonidentity_rejects(self):
        tex={'op':'texture','texture':'t','channels':[0,1,2]}
        node={'op':'desaturate','input':binary('power',tex,constant(1)),'fraction':constant(0)}
        self.assertEqual(evaluate(node),evaluate(tex))
        self.assertEqual(evaluate(binary('power',constant(-2),constant(1))),Constant((0,)))
        with self.assertRaises(Unsupported): evaluate(binary('power',tex,constant(1.3)))

    def test_main_normal_rnm_recognition_preserves_layer_masks_and_uvs(self):
        from ash_unreal_usd601_decals.material_policy import main_normals
        def mask(n,channels): return {'op':'mask','input':n,'channels':channels}
        tex={'op':'texture','texture':'main','normal_map':True,'uv':{'op':'uv','scale':[3,4]}}
        base={'op':'lerp','a':mask(tex,[0,1,2]),'b':constant([0,0,1]),'alpha':constant(1)}
        detail=mask({'op':'texture','texture':'detail','normal_map':True},[0,1,2])
        t=binary('append',mask(base,[0,1]),binary('add',mask(base,[2]),constant(1)))
        u=binary('append',binary('multiply',mask(detail,[0,1]),constant(-1)),mask(detail,[2]))
        rnm={'op':'normalize','input':binary('subtract',binary('multiply',t,binary('dot',t,u)),binary('multiply',t['b'],u))}
        original={'inputs':{'normal':rnm}}
        result,notes=main_normals(original)
        self.assertEqual(evaluate(result['inputs']['normal']).texture,'main')
        self.assertEqual(evaluate(result['inputs']['normal']).uv.scale,(3,4))
        self.assertEqual(len(notes),2)
        self.assertEqual(original['inputs']['normal']['op'],'normalize')
        layered={'inputs':{'normal':{'op':'lerp','a':rnm,'b':detail,'alpha':{'op':'vertex_color'}}}}
        result,notes=main_normals(layered)
        self.assertEqual(result['inputs']['normal']['op'],'lerp')
        self.assertEqual(result['inputs']['normal']['alpha'],{'op':'vertex_color'})




class MdlTests(unittest.TestCase):
    def test_requested_channels_and_connectable_displacement(self):
        inputs={k:{'op':'unsupported'} for k in ('occlusion','subsurface')}
        program,issues=compile_mdl({'inputs':inputs,'foliage':True},{})
        self.assertEqual(issues,[])
        self.assertIn('float3 geometry_displacement = float3(0.0)',program['source'])
        self.assertNotIn('uniform float3 geometry_displacement',program['source'])
        self.assertIn('displacement:geometry_displacement',program['source'])
        self.assertNotIn('diffuse_transmission',program['source'])
        self.assertNotIn('subsurface',program['source'])

    def test_readable_names_and_collisions(self):
        from ash_unreal_usd601_decals.naming import names, material_name
        labels=names({'/a':'MI_Leaves','/b':'mi_leaves','/c':'MI_Leaves','/d':'Wall'})
        self.assertEqual(labels['/a'],'MI_Leaves')
        self.assertEqual(labels['/d'],'Wall')
        self.assertEqual(len({v.lower() for v in labels.values()}),4)
        self.assertEqual(material_name({'inputs':{'base_color':{'op':'texture','texture':'t'}}},{'t':{'source':'/Game/T_Leaves_BaseColor.T_Leaves_BaseColor'}}),'M_Leaves')
    def test_layer_weights_tiling_and_foliage_random_remain_live(self):
        uv=binary('multiply',{'op':'uv'},dict(constant(7),parameter='Tiling'))
        color={'op':'texture','texture':'color','uv':uv}
        weight={'op':'mask','input':{'op':'texture','texture':'weight','uv':{'op':'uv','channel':1}},'channels':[1]}
        inputs={'base_color':binary('multiply',color,weight),'roughness':{'op':'per_instance_random'}}
        program,issues=compile_mdl({'inputs':inputs},{'color':{'file':'textures/color.png'},'weight':{'file':'textures/weight.png'}})
        self.assertEqual(issues,[])
        self.assertEqual(program['uv_channels'],[0,1])
        self.assertIn('unreal_instance_random',program['source'])
        self.assertEqual(sum(p['type']=='texture_2d' for p in program['parameters'].values()),2)
        tiling=next(p for p in program['parameters'].values() if p['label']=='Tiling')
        self.assertEqual((tiling['type'],tiling['value']),('float',7))


if __name__=='__main__': unittest.main()
