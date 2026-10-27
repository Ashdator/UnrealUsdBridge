import json
import unittest
from test_core import fixture_directory
from ash_unreal_usd601_decals.extraction_status import character_only_failure


class ExtractionStatusTests(unittest.TestCase):
    def fixture(self,root):
        (root/'mesh.json').write_text('{}');(root/'texture.png').write_bytes(b'texture')
        data={'schema_version':1,'map':'/Game/Environment','meshes':{'m':{'file':'mesh.json'}},
              'textures':{'t':{'file':'texture.png'}},'materials':{},'instances':[],'instancers':[]}
        manifest=root/'manifest.json';manifest.write_text(json.dumps(data))
        prefix='LogBlueprint: Error: [AssetLog] C:/Project/ThirdPersonCharacter.uasset: [Compiler] '
        log=(prefix+'In use pin  <Unnamed>  no longer exists on node  Reset Orientation and Position . Please refresh node or break links to remove pin.\n'+
             prefix+'Could not find a function named "ResetOrientationAndPosition" in \'ThirdPersonCharacter\'.\n'+
             'BRIDGE_COMPLETE: 1 meshes, 0 materials, 0 instancer groups\n'+
             'Commandlet UnrealUsdExtractCommandlet_0 finished execution (result 0)\nLogExit: Exiting.\n')
        path=root/'unreal.log';path.write_text(log)
        return path,manifest,data,log

    def test_completed_character_error_is_reported(self):
        with fixture_directory() as root:
            log,manifest,_,text=self.fixture(root)
            # Unreal repeats compiler errors in the final warning/error summary.
            with log.open('a') as stream:stream.write('LogInit: Display: '+text.splitlines()[0]+'\n')
            self.assertIn('Environment extraction completed',character_only_failure(1,log,manifest,'/Game/Environment'))

    def test_unknown_environment_error_and_crash_are_not_ignored(self):
        with fixture_directory() as root:
            log,manifest,_,text=self.fixture(root)
            for extra in ('LogTemp: Error: Could not export mesh','LogBlueprint: Error: Broken environment Blueprint',
                          'Fatal error: crash','Unhandled Exception: access violation'):
                with self.subTest(extra=extra):
                    log.write_text(text+'\n'+extra)
                    self.assertIsNone(character_only_failure(1,log,manifest,'/Game/Environment'))

    def test_incomplete_or_different_run_is_rejected(self):
        with fixture_directory() as root:
            log,manifest,_,text=self.fixture(root)
            for before,after in [('BRIDGE_COMPLETE:','INCOMPLETE:'),('1 meshes','2 meshes'),
                                 ('result 0','result 4'),('LogExit: Exiting.','')]:
                with self.subTest(before=before):
                    log.write_text(text.replace(before,after))
                    self.assertIsNone(character_only_failure(1,log,manifest,'/Game/Environment'))
            log.write_text(text)
            self.assertIsNone(character_only_failure(1,log,manifest,'/Game/Other'))
            for code in (0,4,-1,3221225477):
                self.assertIsNone(character_only_failure(code,log,manifest,'/Game/Environment'))

    def test_missing_assets_invalid_manifest_and_character_references_block(self):
        with fixture_directory() as root:
            log,manifest,data,_=self.fixture(root)
            for value in ('missing.png','../outside.png'):
                data['textures']['t']['file']=value;manifest.write_text(json.dumps(data))
                self.assertIsNone(character_only_failure(1,log,manifest,'/Game/Environment'))
            data['textures']['t']['file']='texture.png'
            data['instances']=[{'source':'/Game/ThirdPersonCharacter.StaticMeshComponent'}]
            manifest.write_text(json.dumps(data))
            self.assertIsNone(character_only_failure(1,log,manifest,'/Game/Environment'))
            manifest.write_text('{invalid')
            self.assertIsNone(character_only_failure(1,log,manifest,'/Game/Environment'))

    def test_other_blueprint_even_with_same_function_remains_blocked(self):
        with fixture_directory() as root:
            log,manifest,_,text=self.fixture(root)
            log.write_text(text.replace('ThirdPersonCharacter.uasset','EnvironmentController.uasset'))
            self.assertIsNone(character_only_failure(1,log,manifest,'/Game/Environment'))
