import json,unittest,tracemalloc
from pathlib import Path
from test_core import fixture_directory
from ash_unreal_usd601_decals.manifest_io import texture_span,update_texture_paths

class ManifestIOTests(unittest.TestCase):
    def test_root_field_ignores_nested_and_escaped_names_across_chunks(self):
        data={'materials':{'nested':{'textures':{'not':'root'},'text':'quote \" braces {} [] slash \\ snow 雪'}},'textures':{'a':{'file':'textures/a.png'}},'instancers':[{'transforms':[[1,2,3]]}]}
        with fixture_directory() as root:
            path=root/'source.json';raw=json.dumps(data,ensure_ascii=False).encode();path.write_bytes(raw)
            for size in (1,2,7,4096):
                start,end=texture_span(path,size);self.assertEqual(json.loads(raw[start:end]),data['textures'])
            target=root/'manifest.json';update_texture_paths(path,target,{'a':{'file':'textures/readable.png'}})
            data['textures']['a']['file']='textures/readable.png'
            self.assertEqual(json.loads(target.read_text(encoding='utf-8')),data);self.assertEqual(path.read_bytes(),target.read_bytes())
    def test_truncated_texture_dictionary_does_not_replace_input(self):
        with fixture_directory() as root:
            path=root/'source.json';raw=b'{"textures":{"a":';path.write_bytes(raw)
            with self.assertRaises(ValueError):update_texture_paths(path,root/'out.json',{})
            self.assertEqual(path.read_bytes(),raw);self.assertFalse((root/'out.json').exists())
    def test_streamed_suffix_uses_bounded_memory(self):
        with fixture_directory() as root:
            path=root/'source.json'
            with path.open('wb') as f:
                f.write(b'{"textures":{},"placements":"');f.write(b'x'*16000000);f.write(b'"}')
            tracemalloc.start()
            try:
                update_texture_paths(path,root/'manifest.json',{'a':{'file':'a.png'}})
                _,peak=tracemalloc.get_traced_memory()
            finally:tracemalloc.stop()
            self.assertLess(peak,6*1024*1024)
            self.assertEqual(path.stat().st_size,(root/'manifest.json').stat().st_size)

    def test_retry_reuses_texture_renamed_by_interrupted_run(self):
        import test_usd
        from ash_unreal_usd601_decals.usd_writer import convert
        with fixture_directory() as root:
            path=test_usd.UsdIntegrationTests().fixture(root);data=json.loads(path.read_text())
            texture=data['textures']['tex'];texture['source']='/Game/T_Readable.T_Readable'
            (root/texture['file']).rename(root/'textures/T_Readable.png')
            path.write_text(json.dumps(data))
            scene,report=convert(path)
            self.assertTrue(scene.is_file());self.assertTrue((root/'textures/T_Readable.png').is_file())
            saved=json.loads(path.read_text());self.assertEqual(saved['textures']['tex']['file'],'textures/T_Readable.png')
    def test_retry_does_not_hide_missing_original_and_missing_target(self):
        import test_usd
        from ash_unreal_usd601_decals.usd_writer import convert
        with fixture_directory() as root:
            path=test_usd.UsdIntegrationTests().fixture(root);data=json.loads(path.read_text())
            data['textures']['tex']['file']='textures/not-found.png';data['textures']['tex']['source']='/Game/T_Missing.T_Missing'
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'Missing texture'):convert(path)
