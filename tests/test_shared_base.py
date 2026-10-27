import copy,json,unittest
from pathlib import Path
import numpy as np
from pxr import Sdf,Usd,UsdGeom,UsdShade
from test_core import fixture_directory, placed_mesh
import test_decals
from ash_unreal_usd601_decals.usd_writer import convert
from ash_unreal_usd601_decals.decal_controls import DecalControls
from ash_unreal_usd601_decals.material_links import selection_links


class SharedBaseTests(unittest.TestCase):
    def scene(self,root):
        path,data=test_decals.DecalTests().data(root)
        data['materials']['mat']['inputs']['roughness']={'op':'constant','value':[.4],'parameter':'Roughness'}
        data['materials']['mat']['inputs']['base_color']['uv']={'op':'multiply','a':{'op':'uv'},'b':{'op':'constant','value':[2,3],'parameter':'Wood tiling'}}
        data['decals']=[test_decals.decal('First',0),test_decals.decal('Second',1)]
        path.write_text(json.dumps(data));scene,report=convert(path)
        stage=Usd.Stage.Open(str(scene))
        material=UsdShade.MaterialBindingAPI(placed_mesh(stage,'Actor').GetChild('section_0')).ComputeBoundMaterial()[0]
        master=stage.GetPrimAtPath(material.GetPrim().GetCustomDataByKey('unreal:baseMaterial'))
        return stage,material,master,report,data

    def shader(self,mat):
        return UsdShade.Shader(UsdShade.Material(mat).GetSurfaceOutput('mdl').GetConnectedSource()[0].GetPrim())

    def test_shared_evaluator_has_no_decal_logic_and_regions_share_shader_definitions(self):
        with fixture_directory() as root:
            stage,mat,master,report,_=self.scene(root)
            source=(root/next(iter(report['base_shader_modules'].values()))).read_text()
            self.assertIn('EvaluateBase',source)
            self.assertNotIn('decal',source)
            self.assertNotIn('coordinate_world',source)
            regional=Path(self.shader(mat).GetSourceAsset('mdl').resolvedPath).read_text()
            self.assertEqual(regional.count('::EvaluateBase('),1)
            self.assertIn('state::coordinate_world',regional);self.assertNotIn('bridge_decalUVW',regional)
            self.assertNotIn('state::texture_coordinate(',regional)
            master_source=Path(self.shader(master).GetSourceAsset('mdl').resolvedPath).read_text()
            self.assertNotIn('bridge_decalUVW',master_source)
            self.assertFalse(master.GetRelationship('unreal:decals'))
            row=selection_links(stage,[mat.GetPath()])['materials'][0]
            self.assertEqual(row['base_material'],str(master.GetPath()))

    def test_base_edits_propagate_tiling_roughness_texture_and_time_samples(self):
        with fixture_directory() as root:
            stage,mat,master,_,_=self.scene(root)
            before=stage.GetRootLayer().ExportToString()
            sync=DecalControls(stage)
            self.assertEqual(stage.GetRootLayer().ExportToString(),before)
            inputs=self.shader(master).GetInputs()
            rough=next(i.GetAttr() for i in inputs if i.GetAttr().GetDisplayName()=='Roughness')
            tiling=next(i.GetAttr() for i in inputs if i.GetAttr().GetDisplayName()=='Wood tiling')
            image=next(i.GetAttr() for i in inputs if i.GetTypeName()==Sdf.ValueTypeNames.Asset)
            rough.Set(.71);rough.Set(.29,2);tiling.Set((4,5,0,0))
            replacement=root/'replacement.png';replacement.write_bytes(Path(image.Get().resolvedPath).read_bytes())
            image.Set(Sdf.AssetPath('./replacement.png'))
            for source in (rough,tiling,image):
                targets=[a for p in stage.Traverse() for a in p.GetAttributes() if a.GetCustomDataByKey('unreal:baseControl')==str(source.GetPath())]
                self.assertTrue(targets)
                for target in targets:
                    if source==image:self.assertEqual(target.Get().resolvedPath,source.Get().resolvedPath)
                    else:self.assertEqual(target.Get(),source.Get())
                    self.assertTrue(target.GetMetadata('hidden'))
                    if source==rough:self.assertAlmostEqual(target.Get(2),.29,places=5)
            rough.ClearAtTime(2)
            self.assertTrue(all(not a.GetTimeSamples() for p in stage.Traverse() for a in p.GetAttributes() if a.GetCustomDataByKey('unreal:baseControl')==str(rough.GetPath())))
            sync.close()

    def test_base_asset_overrides_and_connections_use_the_active_edit_layer(self):
        with fixture_directory() as root:
            stage,mat,master,_,_=self.scene(root)
            sync=DecalControls(stage)
            image=next(i.GetAttr() for i in self.shader(master).GetInputs() if i.GetTypeName()==Sdf.ValueTypeNames.Asset)
            rough=next(i.GetAttr() for i in self.shader(master).GetInputs() if i.GetAttr().GetDisplayName()=='Roughness')
            folder=root/'edits';folder.mkdir();edit=Sdf.Layer.CreateNew(str(folder/'edit.usda'))
            stage.GetRootLayer().subLayerPaths.insert(0,'edits/edit.usda')
            # A stronger session layer can carry shared controls and all their copies.
            stage.SetEditTarget(stage.GetSessionLayer())
            replacement=root/'override.png';replacement.write_bytes(Path(image.Get().resolvedPath).read_bytes())
            image.Set(Sdf.AssetPath(str(replacement)));image.SetColorSpace('raw')
            image.Set(Sdf.AssetPath(str(replacement)),3)
            control=stage.DefinePrim('/World/Looks/Control','Shader').CreateAttribute('inputs:r',Sdf.ValueTypeNames.Float)
            control.Set(.2);rough.SetConnections([control.GetPath()])
            for p in stage.Traverse():
                for attr in p.GetAttributes():
                    source=attr.GetCustomDataByKey('unreal:baseControl')
                    if source==str(image.GetPath()):
                        self.assertEqual(attr.Get().resolvedPath,str(replacement))
                        self.assertEqual(attr.Get(3).resolvedPath,str(replacement))
                        self.assertEqual(attr.GetColorSpace(),'raw')
                    elif source==str(rough.GetPath()):self.assertEqual(attr.GetConnections(),[control.GetPath()])
            sync.close()

    def test_generated_uv_controls_are_shared_with_decal_regions(self):
        with fixture_directory() as root:
            path,data=test_decals.DecalTests().data(root)
            path.write_text(json.dumps(data));scene,_=convert(path)
            stage=Usd.Stage.Open(str(scene));sync=DecalControls(stage)
            master=stage.GetPrimAtPath('/World/Looks/Paint/MDL')
            for label,value in (('UV 0 Tiling',(4,5)),):
                source=next(a for a in master.GetAttributes() if a.GetDisplayName()==label)
                source.Set(value)
                copies=[a for p in stage.Traverse() for a in p.GetAttributes() if a.GetCustomDataByKey('unreal:baseControl')==str(source.GetPath())]
                self.assertTrue(copies)
                self.assertTrue(all(a.Get()==source.Get() for a in copies))
            sync.close()

    def test_world_projection_retains_base_uvs_without_receiver_coordinate_arrays(self):
        with fixture_directory() as root:
            stage,mat,master,report,data=self.scene(root)
            mesh=json.loads((root/data['meshes']['mesh']['file']).read_text())
            for name in ('Actor','Raised'):
                prim=placed_mesh(stage,name);api=UsdGeom.PrimvarsAPI(prim)
                np.testing.assert_allclose(api.GetPrimvar('st').ComputeFlattened(),[[uv[0],1-uv[1]] for uv in mesh['uvs'][0]])
                self.assertFalse(api.GetPrimvar('bridge_decalUVW0'))
                self.assertFalse(api.GetPrimvar('st'+str(len(mesh['uvs']))))
                self.assertEqual(list(prim.GetAttribute('faceVertexIndices').Get()),mesh['indices'])
            self.assertEqual(report.get('projected_coordinate_bytes',0),0)

    def test_no_removal_metadata_is_exported_and_controls_remain_linked(self):
        with fixture_directory() as root:
            stage,mat,master,_,_=self.scene(root)
            self.assertFalse((root/'DecalEditRecipes.json').exists())
            for p in stage.Traverse():
                self.assertIsNone(p.GetCustomDataByKey('unreal:decalRecipeAsset'))
                self.assertIsNone(p.GetCustomDataByKey('unreal:decalRecipeKey'))
            rows=selection_links(stage,[mat.GetPath()])['materials'][0]
            self.assertEqual(len(rows['decals']),2)
            self.assertNotIn('removal_available',rows)
            self.assertEqual(rows['base_material'],str(master.GetPath()))

    def test_receiver_specific_uvs_allow_identical_regional_shader_definitions(self):
        with fixture_directory() as root:
            from test_world_decals import SharedWorldTests
            path,data=SharedWorldTests().distributed(root,13);path.write_text(json.dumps(data))
            scene,report=convert(path)
            region_defs={r['mdl_definition'] for r in report['materials'].values() if r.get('decal_layers')}
            self.assertEqual(len(region_defs),1)
            self.assertEqual(report['counts']['max_decals_per_material'],1)
            self.assertEqual(report['counts']['shared_base_materials'],1)

    def test_unsupported_receiver_is_reported_in_partial_preview(self):
        with fixture_directory() as root:
            path,data=test_decals.DecalTests().data(root)
            data['materials']['mat']['inputs']['roughness']={'op':'unsupported_test_node'}
            path.write_text(json.dumps(data))
            scene,report=convert(path,allow_partial=True)
            self.assertTrue(scene.is_file())
            self.assertEqual(report['status'],'partial')
            self.assertTrue(any('unsupported_test_node' in str(r['issues']) for r in report['materials'].values()))

if __name__=='__main__':unittest.main()
