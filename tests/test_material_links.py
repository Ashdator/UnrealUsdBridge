import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'UnrealUsdBridge/Resources/Python'))
from ash_unreal_usd601_decals.material_links import material_decals,selection_links
from ash_unreal_usd601_decals.usd_writer import convert
from ash_unreal_usd601_decals.mdl import compile_function,name
from test_core import fixture_directory, placed_mesh
import test_decals
from pxr import Sdf,Usd,UsdShade


class MaterialLinkTests(unittest.TestCase):
    def scene(self,root):
        path,data=test_decals.DecalTests().data(root)
        path.write_text(json.dumps(data));scene,report=convert(path)
        return Usd.Stage.Open(str(scene)),report

    def material(self,stage,object_name='Actor'):
        return UsdShade.MaterialBindingAPI(placed_mesh(stage,object_name).GetChild('section_0')).ComputeBoundMaterial()[0]

    def test_material_to_shared_control_on_055_structure_is_read_only(self):
        with fixture_directory() as root:
            stage,report=self.scene(root)
            before=stage.GetRootLayer().ExportToString()
            rows=selection_links(stage,[self.material(stage).GetPath()])
            self.assertEqual(rows['mode'],'materials')
            self.assertEqual(rows['materials'][0]['decals'][0]['path'],'/World/Decals/TestDecal')
            self.assertEqual(rows['materials'][0]['decals'][0]['label'],'TestDecal')
            self.assertTrue(rows['materials'][0]['decals'][0]['available'])
            self.assertEqual(stage.GetRootLayer().ExportToString(),before)
            self.assertEqual(report['counts']['decal_material_variants'],1)
            control=stage.GetPrimAtPath('/World/Decals/TestDecal')
            self.assertFalse(control.GetRelationship('unreal:decalReceivers'))
            self.assertEqual([a.GetName() for a in control.GetAttributes() if a.GetName().startswith('inputs:')],['inputs:amount'])

    def test_objects_nodegraphs_and_empty_materials_have_no_custom_section(self):
        with fixture_directory() as root:
            stage,_=self.scene(root)
            self.assertIsNone(selection_links(stage,['/World/Decals/TestDecal']))
            self.assertIsNone(selection_links(stage,['/World/Decals']))
            self.assertIsNone(selection_links(stage,['/World/Objects/Actor']))
            self.assertIsNone(selection_links(stage,['/World/Objects']))
            self.assertIsNone(selection_links(stage,[self.material(stage,'Disabled').GetPath()]))
            self.assertIsNone(selection_links(stage,[]))
            self.assertIsNone(selection_links(None,['/World/Objects/Actor']))

    def test_shader_selection_uses_parent_material_and_nonreceiver_has_no_decals(self):
        with fixture_directory() as root:
            stage,_=self.scene(root)
            material=str(self.material(stage).GetPath())
            rows=selection_links(stage,[material+'/MDL'])
            self.assertEqual(rows['materials'][0]['path'],material)
            self.assertEqual(len(rows['materials'][0]['decals']),1)
            outside=self.material(stage,'Disabled').GetPath()
            self.assertEqual(material_decals(stage.GetPrimAtPath(outside)),[])

    def test_deleted_graph_is_reported_as_unavailable_not_recreated(self):
        with fixture_directory() as root:
            stage,_=self.scene(root)
            material=self.material(stage).GetPath()
            stage.RemovePrim('/World/Decals')
            before=stage.GetRootLayer().ExportToString()
            decals=material_decals(stage.GetPrimAtPath(material))
            self.assertEqual(len(decals),1)
            self.assertFalse(decals[0]['available'])
            self.assertEqual(decals[0]['label'],'TestDecal')
            self.assertEqual(stage.GetRootLayer().ExportToString(),before)

    def test_decal_controls_are_grouped_apart_from_surface_textures(self):
        with fixture_directory() as root:
            stage,report=self.scene(root)
            material=self.material(stage)
            shader=stage.GetPrimAtPath(material.GetPath().AppendChild('MDL'))
            controls=[a for a in shader.GetAttributes() if a.GetCustomDataByKey('unreal:decalControl')]
            self.assertTrue(controls)
            for attr in controls:
                self.assertEqual(attr.GetDisplayGroup(),'Decals')
                self.assertEqual(attr.GetCustomDataByKey('uiorder'),1000)
                self.assertFalse(attr.GetMetadata('hidden'))
                self.assertAlmostEqual(attr.Get(),1.0)
            for attr in shader.GetAttributes():
                if attr.GetTypeName()==Sdf.ValueTypeNames.Asset and not attr.GetMetadata('hidden'):
                    self.assertNotEqual(attr.GetDisplayGroup(),'Decals')
            # Canonical shader sharing must preserve MDL UI annotations too.
            source=Path(UsdShade.Shader(shader).GetSourceAsset('mdl').resolvedPath).read_text()
            self.assertIn('anno::in_group("Decals")',source)
            self.assertIn('anno::ui_order(1000)',source)
            sync=test_decals.DecalControls(stage)
            stage.GetAttributeAtPath('/World/Decals/TestDecal.inputs:amount').Set(.25)
            self.assertTrue(all(abs(a.Get()-.25)<1e-5 for a in controls))
            sync.close()

    def test_desaturation_label_fix_preserves_source_parameter_identity_and_value(self):
        node={'op':'constant','value':[.4],'parameter':'Wood Deaturation'}
        program=compile_function(node,{},'float')
        self.assertIn(name('Wood Deaturation'),program['parameters'])
        self.assertEqual(program['parameters'][name('Wood Deaturation')]['label'],'Wood Desaturation')
        self.assertAlmostEqual(program['parameters'][name('Wood Deaturation')]['value'],.4)
        self.assertIn('anno::display_name("Wood Desaturation")',program['source'])
        with fixture_directory() as root:
            path,data=test_decals.DecalTests().data(root)
            data['materials']['mat']['inputs']['roughness']=node
            path.write_text(json.dumps(data));scene,_=convert(path)
            stage=Usd.Stage.Open(str(scene))
            shader=stage.GetPrimAtPath(self.material(stage).GetPath().AppendChild('MDL'))
            corrected=[a for a in shader.GetAttributes() if a.GetDisplayName()=='Wood Desaturation']
            self.assertEqual(len(corrected),1)
            self.assertAlmostEqual(corrected[0].Get(),.4)
            self.assertNotEqual(corrected[0].GetDisplayGroup(),'Decals')

if __name__=='__main__':unittest.main()
