import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'UnrealUsdBridge/Resources/Python'))
from ash_unreal_usd601_decals.usd_writer import convert
from test_core import fixture_directory

try:
    from pxr import Usd, UsdGeom, UsdShade, Gf
except ImportError:
    Usd=None


@unittest.skipIf(Usd is None,'Requires USD Python, available inside Isaac Sim')
class UsdIntegrationTests(unittest.TestCase):
    def test_component_position_uses_component_matrix_for_static_and_instanced_mesh(self):
        with fixture_directory() as root:
            manifest=self.fixture(root);data=json.loads(manifest.read_text())
            data['materials']['mat']['inputs']['base_color']={'op':'local_position','origin':'component'}
            matrix=data['instances'][0]['matrix']
            # Component has scale, rotation and translation; instance placement
            # is deliberately different from the shared component frame.
            matrix[:12]=[0,2,0,0,-3,0,0,0,0,0,4,0]
            data['instancers'][0]['matrix']=matrix
            manifest.write_text(json.dumps(data));scene,_=convert(manifest)
            stage=Usd.Stage.Open(str(scene))
            component=Gf.Matrix4d(*[matrix[4*i+j]*(1,-1,1,1)[i]*(1,-1,1,1)[j]*(.01 if i==3 and j<3 else 1) for i in range(4) for j in range(4)])
            local=Gf.Vec4d(.4,.5,.6,1);world=local*component
            self.assertFalse(stage.GetPrimAtPath('/World/Objects/Actor').GetAttribute('primvars:unreal_instance_to_component_0'))
            instancer=next(p for p in stage.Traverse() if p.IsA(UsdGeom.PointInstancer))
            for index,flat in enumerate(data['instancers'][0]['transforms']):
                relative=Gf.Matrix4d(*[flat[4*i+j]*(1,-1,1,1)[i]*(1,-1,1,1)[j]*(.01 if i==3 and j<3 else 1) for i in range(4) for j in range(4)])
                expected=local*relative
                recovered=[Gf.Dot(local,Gf.Vec4d(*instancer.GetAttribute('primvars:unreal_instance_to_component_'+str(i)).Get()[index])) for i in range(3)]
                for i in range(3):self.assertAlmostEqual(recovered[i],expected[i],places=6)
            # Moving the component does not alter its relative coordinate maps.
            before=instancer.GetAttribute('primvars:unreal_instance_to_component_0').Get()
            UsdGeom.Xformable(instancer).GetOrderedXformOps()[0].Set(Gf.Matrix4d(1))
            self.assertEqual(instancer.GetAttribute('primvars:unreal_instance_to_component_0').Get(),before)

    def test_original_geometry_preserved_and_audited(self):
        with fixture_directory() as root:
            manifest=self.fixture(root)
            file=root/'meshes/m.json'
            mesh=json.loads(file.read_text())
            mesh.update(geometry_source='original_hi_res',source_triangles=1,render_lod0_triangles=0)
            file.write_text(json.dumps(mesh))
            path,report=convert(manifest)
            self.assertEqual(report['geometry']['mesh']['triangles'],1)
            self.assertEqual(report['geometry']['mesh']['render_lod0_triangles'],0)
            geometry=Usd.Stage.Open(str(root/'Geometry.usdc'))
            prim=next(p for p in geometry.Traverse() if p.IsA(UsdGeom.Mesh))
            self.assertEqual(prim.GetCustomDataByKey('unreal:geometrySource'),'original_hi_res')
            self.assertEqual(list(UsdGeom.Mesh(prim).GetFaceVertexIndicesAttr().Get()),mesh['indices'])

    def test_original_geometry_cannot_silently_lose_triangles(self):
        with fixture_directory() as root:
            manifest=self.fixture(root)
            file=root/'meshes/m.json'
            mesh=json.loads(file.read_text())
            mesh.update(geometry_source='original_lod0',source_triangles=2)
            file.write_text(json.dumps(mesh))
            with self.assertRaisesRegex(ValueError,'Original mesh triangle count changed'):
                convert(manifest)

    def fixture(self,root,unsupported=False):
        (root/'meshes').mkdir(); (root/'textures').mkdir()
        (root/'textures/check.png').write_bytes(b'placeholder')
        mesh={'source':'/Game/Mesh','points':[[0,0,0],[100,0,0],[0,100,0]],'normals':[[0,0,1]]*3,
              'indices':[0,2,1],'uvs':[[[0,0],[1,0],[0,1]]],
              'sections':[{'slot':0,'first_face':0,'face_count':1}]}
        (root/'meshes/m.json').write_text(json.dumps(mesh))
        matrix=[1,0,0,0,0,1,0,0,0,0,1,0,10,20,30,1]
        instance={'source':'/Game/Actor','name':'Actor','mesh':'mesh','materials':['mat'],'matrix':matrix}
        instancer=dict(instance,source='/Game/Foliage',transforms=[matrix,matrix],random_values=[0.125,0.875])
        texture={'op':'texture','texture':'tex','uv':{'op':'add','a':{'op':'uv','scale':[2,3]},'b':{'op':'constant','value':[0.25,0.2]}}}
        mat={'name':'Paint','source':'/Game/Material','inputs':{'base_color':texture},'issues':['Custom HLSL'] if unsupported else []}
        data={'schema_version':1,'materials':{'mat':mat},'textures':{'tex':{'file':'textures/check.png'}},
              'meshes':{'mesh':{'file':'meshes/m.json'}},'instances':[instance],'instancers':[instancer]}
        path=root/'manifest.json'; path.write_text(json.dumps(data)); return path

    def test_stage_units_binding_uvs_and_point_instancer(self):
        with fixture_directory() as root:
            path,report=convert(self.fixture(root),preview_fallback=True)
            stage=Usd.Stage.Open(str(path))
            self.assertEqual(UsdGeom.GetStageMetersPerUnit(stage),1.0)
            self.assertEqual(UsdGeom.GetStageUpAxis(stage),'Z')
            self.assertEqual(report['counts']['foliage_instances'],2)
            instancers=[UsdGeom.PointInstancer(p) for p in stage.Traverse() if p.IsA(UsdGeom.PointInstancer)]
            self.assertEqual(len(instancers),1)
            for actual,expected in zip(instancers[0].GetPositionsAttr().Get()[0],(0.1,-0.2,0.3)):
                self.assertAlmostEqual(actual,expected)
            self.assertEqual(list(UsdGeom.PrimvarsAPI(instancers[0]).GetPrimvar('unreal_instance_random').Get()),[0.125,0.875])
            meshes=[UsdGeom.Mesh(p) for p in stage.Traverse() if p.IsA(UsdGeom.Mesh)]
            self.assertEqual(list(meshes[0].GetFaceVertexIndicesAttr().Get()),[0,2,1])
            self.assertEqual(tuple(meshes[0].GetPointsAttr().Get()[1]),(1,0,0))
            mesh=meshes[0]
            points=mesh.GetPointsAttr().Get(); ids=mesh.GetFaceVertexIndicesAttr().Get()
            face=Gf.Cross(points[ids[1]]-points[ids[0]],points[ids[2]]-points[ids[0]])
            self.assertGreater(Gf.Dot(face,mesh.GetNormalsAttr().Get()[ids[0]]),0)
            self.assertEqual(tuple(UsdGeom.PrimvarsAPI(meshes[0]).GetPrimvar('st').Get()[0]),(0,1))
            subsets=UsdShade.MaterialBindingAPI(meshes[0]).GetMaterialBindSubsets()
            binding,_=UsdShade.MaterialBindingAPI(subsets[0]).ComputeBoundMaterial()
            self.assertEqual(str(binding.GetPath()),'/World/Looks/Paint')
            offset=stage.GetAttributeAtPath('/World/Looks/Paint.inputs:base_color_uv_translation').Get()
            self.assertAlmostEqual(offset[0],0.25)
            self.assertAlmostEqual(offset[1],-2.2,places=5)

    def test_coincident_instances_keep_individual_primvars(self):
        with fixture_directory() as root:
            manifest=self.fixture(root)
            data=json.loads(manifest.read_text())
            data['instancers'][0]['object_positions']=[[100,200,300],[100,200,300]]
            manifest.write_text(json.dumps(data))
            path,report=convert(manifest)
            stage=Usd.Stage.Open(str(path))
            pi=next(UsdGeom.PointInstancer(p) for p in stage.Traverse() if p.IsA(UsdGeom.PointInstancer))
            self.assertEqual(report['counts']['foliage_instances'],2)
            self.assertEqual(pi.GetPositionsAttr().Get()[0],pi.GetPositionsAttr().Get()[1])
            self.assertEqual(list(pi.GetIdsAttr().Get()),[0,1])
            self.assertEqual(list(UsdGeom.PrimvarsAPI(pi).GetPrimvar('unreal_instance_random').Get()),[0.125,0.875])
            self.assertEqual(len(UsdGeom.PrimvarsAPI(pi).GetPrimvar('unreal_object_position').Get()),2)

    def test_misaligned_foliage_positions_rejected(self):
        with fixture_directory() as root:
            manifest=self.fixture(root)
            data=json.loads(manifest.read_text())
            data['instancers'][0]['object_positions']=[[100,200,300]]
            manifest.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'object positions must match'):
                convert(manifest)

    def test_light_and_camera_transform(self):
        from pxr import UsdLux
        with fixture_directory() as root:
            manifest=self.fixture(root)
            data=json.loads(manifest.read_text())
            matrix=data['instances'][0]['matrix']
            data['lights']=[dict(source='/Game/Sun',kind='distant',color=[1,0.8,0.6],intensity=10,matrix=matrix)]
            data['cameras']=[dict(source='/Game/Camera',fov=90,aspect=2,matrix=matrix)]
            manifest.write_text(json.dumps(data))
            path,_=convert(manifest)
            stage=Usd.Stage.Open(str(path))
            camera=next(UsdGeom.Camera(p) for p in stage.Traverse() if p.IsA(UsdGeom.Camera))
            light=next(UsdLux.DistantLight(p) for p in stage.Traverse() if p.IsA(UsdLux.DistantLight))
            self.assertEqual(light.GetIntensityAttr().Get(),10)
            self.assertAlmostEqual(camera.GetHorizontalApertureAttr().Get(),1)
            self.assertAlmostEqual(camera.GetFocalLengthAttr().Get(),0.5)
            transform=UsdGeom.Xformable(camera).GetLocalTransformation()
            self.assertEqual(tuple(transform.ExtractTranslation()),(0.1,-0.2,0.3))
            forward=transform.TransformDir(Gf.Vec3d(0,0,-1))
            self.assertAlmostEqual(forward[0],1)

    def test_strict_stops_before_writing_scene(self):
        with fixture_directory() as root:
            with self.assertRaisesRegex(ValueError,'unsupported'):
                convert(self.fixture(root,unsupported=True))
            self.assertFalse((root/'Scene.usdc').exists())
            self.assertEqual(json.loads((root/'conversion-report.json').read_text())['status'],'blocked')

    def test_light_dimensions_orthographic_width_and_graph_space(self):
        from pxr import UsdLux
        with fixture_directory() as root:
            manifest=self.fixture(root)
            data=json.loads(manifest.read_text())
            matrix=data['instances'][0]['matrix']
            data['instances'][0]['object_position']=[100,200,300]
            data['lights']=[dict(source='/Game/Rect',kind='rect',width=200,height=100,color=[1,1,1],intensity=5,matrix=matrix),
                            dict(source='/Game/Point',kind='point',radius=50,color=[1,1,1],intensity=5,matrix=matrix)]
            data['cameras']=[dict(source='/Game/Ortho',orthographic=True,ortho_width=1000,fov=90,aspect=2,matrix=matrix)]
            manifest.write_text(json.dumps(data))
            path,_=convert(manifest)
            stage=Usd.Stage.Open(str(path))
            rect=next(UsdLux.RectLight(p) for p in stage.Traverse() if p.IsA(UsdLux.RectLight))
            sphere=next(UsdLux.SphereLight(p) for p in stage.Traverse() if p.IsA(UsdLux.SphereLight))
            camera=next(UsdGeom.Camera(p) for p in stage.Traverse() if p.IsA(UsdGeom.Camera))
            self.assertEqual((rect.GetWidthAttr().Get(),rect.GetHeightAttr().Get()),(2,1))
            self.assertEqual(sphere.GetRadiusAttr().Get(),0.5)
            # 100 tenths-of-a-meter = original 1000 cm field of view.
            self.assertEqual(camera.GetHorizontalApertureAttr().Get(),100)
            self.assertAlmostEqual(camera.GetClippingRangeAttr().Get()[0],0.01)
            prim=stage.GetPrimAtPath('/World/Objects/Actor')
            self.assertEqual(tuple(UsdGeom.PrimvarsAPI(prim).GetPrimvar('unreal_object_position').Get()),(100,200,300))

    def test_partial_is_marked_and_magenta(self):
        with fixture_directory() as root:
            path,report=convert(self.fixture(root,unsupported=True),allow_partial=True)
            stage=Usd.Stage.Open(str(path))
            self.assertEqual(report['status'],'partial')
            self.assertEqual(tuple(stage.GetAttributeAtPath('/World/Looks/Paint/Surface.inputs:diffuseColor').Get()),(1,0,1))

    def test_unsupported_sky_is_visible_magenta_by_default(self):
        with fixture_directory() as root:
            manifest=self.fixture(root,unsupported=True);data=json.loads(manifest.read_text())
            data['instances'][0]['name']='SM_SkySphere'
            manifest.write_text(json.dumps(data));path,report=convert(manifest,allow_partial=True)
            stage=Usd.Stage.Open(str(path))
            self.assertFalse(report['hide_unsupported_sky'])
            self.assertEqual(report['hidden_unsupported_sky'],[])
            mesh=stage.GetPrimAtPath('/World/Objects/SM_SkySphere')
            self.assertEqual(UsdGeom.Imageable(mesh).ComputeVisibility(),UsdGeom.Tokens.inherited)
            self.assertEqual(tuple(stage.GetAttributeAtPath('/World/Looks/Paint/Surface.inputs:diffuseColor').Get()),(1,0,1))

    def test_explicit_sky_hide_option_remains_available(self):
        with fixture_directory() as root:
            manifest=self.fixture(root,unsupported=True);data=json.loads(manifest.read_text())
            data['instances'][0]['name']='SM_SkySphere'
            manifest.write_text(json.dumps(data));path,report=convert(manifest,allow_partial=True,hide_unsupported_sky=True)
            stage=Usd.Stage.Open(str(path))
            mesh=stage.GetPrimAtPath('/World/Objects/SM_SkySphere')
            self.assertEqual(UsdGeom.Imageable(mesh).ComputeVisibility(),UsdGeom.Tokens.invisible)
            self.assertEqual(len(report['hidden_unsupported_sky']),1)

    def test_preview_names_and_ignored_maps(self):
        with fixture_directory() as root:
            manifest=self.fixture(root)
            data=json.loads(manifest.read_text())
            data['textures']['ao']={'file':'textures/not-present.png','source':'/Game/Unwanted_AO.Unwanted_AO'}
            data['materials']['mat']['inputs']['occlusion']={'op':'texture','texture':'ao'}
            data['materials']['mat']['inputs']['subsurface']={'op':'unsupported','reason':'must not be evaluated'}
            manifest.write_text(json.dumps(data))
            path,report=convert(manifest)
            stage=Usd.Stage.Open(str(path))
            material=stage.GetPrimAtPath('/World/Looks/Paint')
            self.assertTrue(material)
            self.assertTrue(stage.GetPrimAtPath('/World/Looks/Paint/Surface'))
            self.assertFalse(stage.GetPrimAtPath('/World/Looks/Paint/MDL'))
            self.assertEqual(report['counts']['textures'],1)
            self.assertNotIn('not-present',stage.GetRootLayer().ExportToString())
            self.assertTrue(stage.GetPrimAtPath('/World/Objects/Actor'))
            geometry=Usd.Stage.Open(str(root/'Geometry.usdc'))
            self.assertTrue(geometry.GetPrimAtPath('/Meshes/Mesh'))

    def test_complex_material_has_only_mdl_and_keeps_main_normal(self):
        with fixture_directory() as root:
            manifest=self.fixture(root)
            data=json.loads(manifest.read_text())
            material=data['materials']['mat']
            material['inputs']['base_color']={'op':'power','a':material['inputs']['base_color'],'b':{'op':'constant','value':[1.7]}}
            material['inputs']['normal']={'op':'mask','input':{'op':'texture','texture':'tex','normal_map':True},'channels':[0,1,2]}
            manifest.write_text(json.dumps(data))
            path,report=convert(manifest,preview_fallback=True)
            stage=Usd.Stage.Open(str(path))
            self.assertTrue(stage.GetPrimAtPath('/World/Looks/Paint/MDL'))
            self.assertFalse(stage.GetPrimAtPath('/World/Looks/Paint/Surface'))
            mat=UsdShade.Material(stage.GetPrimAtPath('/World/Looks/Paint'))
            self.assertFalse(mat.GetSurfaceOutput().HasConnectedSource())
            self.assertTrue(mat.GetSurfaceOutput('mdl').HasConnectedSource())
            self.assertEqual(report['materials']['mat']['backend'],'MDL')
            self.assertTrue(any('base_color' in issue for issue in report['materials']['mat']['preview_limitations']))

    def test_foliage_is_stock_omnipbr_with_normal_and_live_packed_channel(self):
        with fixture_directory() as root:
            manifest=self.fixture(root)
            data=json.loads(manifest.read_text()); mat=data['materials']['mat']
            mat['foliage']=True; mat['two_sided']=True; mat['opacity_threshold']=0.4
            mat['inputs']['normal']={'op':'mask','input':{'op':'texture','texture':'tex','normal_map':True},'channels':[0,1,2]}
            mat['inputs']['roughness']={'op':'mask','input':{'op':'texture','texture':'tex'},'channels':[1]}
            mat['inputs']['opacity']={'op':'mask','input':{'op':'texture','texture':'tex'},'channels':[3]}
            mat['inputs']['occlusion']={'op':'unsupported','reason':'must be ignored'}
            mat['inputs']['subsurface']={'op':'unsupported','reason':'must be ignored'}
            manifest.write_text(json.dumps(data))
            path,report=convert(manifest)
            stage=Usd.Stage.Open(str(path))
            shader=UsdShade.Shader.Get(stage,'/World/Looks/Paint/OmniPBR')
            self.assertEqual(shader.GetSourceAsset('mdl').path,'OmniPBR.mdl')
            self.assertEqual(shader.GetSourceAssetSubIdentifier('mdl'),'OmniPBR')
            self.assertEqual(shader.GetInput('normalmap_texture').GetAttr().GetColorSpace(),'raw')
            self.assertTrue(shader.GetInput('flip_tangent_v').Get())
            self.assertEqual(shader.GetInput('bump_factor').Get(),1)
            self.assertTrue(shader.GetInput('reflection_roughness_constant').HasConnectedSource())
            self.assertEqual(shader.GetInput('ao_to_diffuse').Get(),0)
            self.assertFalse(shader.GetInput('ao_texture'))
            self.assertFalse(stage.GetPrimAtPath('/World/Looks/Paint/Surface'))
            self.assertEqual(report['materials']['mat']['backend'],'OmniPBR')
            self.assertIn('.y', (root/'materials/Paint/roughness.mdl').read_text())
            self.assertIn('.w', (root/'materials/Paint/opacity.mdl').read_text())

    def test_preview_normal_is_decoded_and_connected_after_flatten_removal(self):
        with fixture_directory() as root:
            manifest=self.fixture(root)
            data=json.loads(manifest.read_text()); mat=data['materials']['mat']
            mat['inputs']['normal']={'op':'lerp','a':{'op':'mask','input':{'op':'texture','texture':'tex','normal_map':True},'channels':[0,1,2]},'b':{'op':'constant','value':[0,0,1]},'alpha':{'op':'constant','value':[1]}}
            manifest.write_text(json.dumps(data))
            path,report=convert(manifest)
            stage=Usd.Stage.Open(str(path))
            surface=UsdShade.Shader.Get(stage,'/World/Looks/Paint/Surface')
            self.assertTrue(surface.GetInput('normal').HasConnectedSource())
            texture=UsdShade.Shader.Get(stage,'/World/Looks/Paint/normal_texture')
            self.assertEqual(texture.GetInput('sourceColorSpace').Get(),'raw')
            self.assertEqual(tuple(texture.GetInput('scale').Get()),(2,-2,2,1))
            self.assertEqual(tuple(texture.GetInput('bias').Get()),(-1,1,-1,0))
            self.assertTrue(report['materials']['mat']['normal_changes'])

    def test_foliage_function_filename_does_not_overwrite_named_material(self):
        with fixture_directory() as root:
            manifest=self.fixture(root)
            data=json.loads(manifest.read_text()); data['materials']['mat']['foliage']=True
            data['materials']['other']={'name':'Paint_base_color','inputs':{'base_color':{'op':'power','a':{'op':'texture','texture':'tex'},'b':{'op':'constant','value':1.3}}}}
            import copy
            other=copy.deepcopy(data['instances'][0]);other.update(name='Other',source='/Game/Other',materials=['other'])
            data['instances'].append(other)
            manifest.write_text(json.dumps(data))
            _,report=convert(manifest)
            self.assertIn('export color Evaluate', (root/'materials/Paint/base_color.mdl').read_text())
            self.assertIn('export material UnrealMaterial', (root/report['materials']['other']['mdl_definition']).read_text())


if __name__=='__main__': unittest.main()
