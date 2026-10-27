import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'UnrealUsdBridge/Resources/Python'))
from ash_unreal_usd601_decals.vegetation import exclusion_reason, plant_asset_name
from ash_unreal_usd601_decals.decals import prepare, material_keys
from ash_unreal_usd601_decals.usd_writer import convert
from test_core import fixture_directory, placed_mesh
import test_decals


class VegetationDecalTests(unittest.TestCase):
    def test_asset_leaf_classification_avoids_folders_and_substrings(self):
        for value in ('/Game/Props/SM_Pine_Tree_01.SM_Pine_Tree_01', 'SM_GrassPatch02',
                      'Shrubs_1_Single', 'Cat_Tail', 'Palm01', 'Fern_2'):
            self.assertTrue(plant_asset_name(value),value)
        for value in ('/Game/Foliage/River_Stone.River_Stone', 'Grasshopper',
                      'Wooden_Planks', 'Treehouse', 'Bushings', 'Power_Pole'):
            self.assertFalse(plant_asset_name(value),value)

    def test_whole_tree_including_bark_excluded_and_source_settings_preserved(self):
        with fixture_directory() as root:
            _,data=test_decals.DecalTests().data(root)
            data['materials']['leaves']=dict(data['materials']['mat'],foliage=True)
            tree=copy.deepcopy(data['instances'][0])
            tree.update(source='/Game/Tree',name='Tree',materials=['mat','leaves'],receives_decals=True)
            data['instances'].append(tree)
            audits,issues=prepare(data,root)
            self.assertFalse(issues)
            self.assertEqual(tree['materials'],['mat','leaves'])
            self.assertTrue(tree['receives_decals'])
            self.assertNotIn('decal_sections',tree)
            self.assertNotIn(tree['source'],audits[0]['receivers'])
            self.assertIn('/Game/Actor',audits[0]['receivers'])
            self.assertEqual(data['decal_receiver_exclusions'][0]['reason'],'Unreal foliage shading model')

    def test_painted_vegetation_excluded_but_painted_rocks_keep_decals(self):
        with fixture_directory() as root:
            _,data=test_decals.DecalTests().data(root)
            grass=copy.deepcopy(data['instancers'][0])
            grass.update(source='/Game/GrassGroup',name='GrassGroup',materials=['grass'],receives_decals=True)
            data['materials']['grass']=dict(data['materials']['mat'],foliage=True)
            rocks=data['instancers'][0]
            rocks['receives_decals']=True
            data['instancers'].append(grass)
            audits,_=prepare(data,root)
            self.assertNotIn(grass['source'],audits[0]['receivers'])
            self.assertNotIn('decal_prototypes',grass)
            self.assertIn(rocks['source'],audits[0]['receivers'])
            self.assertTrue(any(data['materials'][key].get('decal_layers') for key in material_keys(rocks)))

    def test_named_vegetation_with_default_lit_material_excluded(self):
        data={'materials':{'bark':{'name':'Generic','foliage':False}},
              'meshes':{'mesh':{'source':'/Game/Models/SM_Pine_Tree_01.SM_Pine_Tree_01'}}}
        instance={'mesh':'mesh','materials':['bark']}
        self.assertEqual(exclusion_reason(data,instance),'vegetation mesh asset name')
        data['meshes']['mesh']['source']='/Game/Foliage/River_Stone.River_Stone'
        self.assertIsNone(exclusion_reason(data,instance))

    def test_export_keeps_omnipbr_and_base_parameters_reports_filter(self):
        from pxr import Usd, UsdShade
        with fixture_directory() as root:
            path,data=test_decals.DecalTests().data(root)
            plant=data['instances'][0]
            plant['materials']=['grass']
            data['materials']['grass']=dict(data['materials']['mat'],foliage=True,name='Grass')
            path.write_text(json.dumps(data))
            scene,report=convert(path)
            self.assertTrue(report['vegetation_decals_excluded'])
            self.assertEqual(report['counts']['vegetation_components_excluded_from_decals'],1)
            self.assertEqual(report['materials']['grass']['backend'],'OmniPBR')
            self.assertEqual(report['materials']['grass']['decal_layers'],[])
            stage=Usd.Stage.Open(str(scene))
            material=UsdShade.MaterialBindingAPI(placed_mesh(stage,'Actor').GetChild('section_0')).ComputeBoundMaterial()[0]
            self.assertTrue(stage.GetPrimAtPath(str(material.GetPath())+'/OmniPBR'))
            self.assertIn('/Game/Raised',report['decals'][0]['supported_receivers'])
            # Extraction remains reproducible, without rewriting Unreal flags.
            source=json.loads((root/'source-manifest.json').read_text())
            self.assertEqual(source['instances'][0]['materials'],['grass'])


if __name__=='__main__':unittest.main()
