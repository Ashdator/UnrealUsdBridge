import copy
import json
import struct
import unittest
import zlib
from test_core import fixture_directory
from ash_unreal_usd601_decals.decal_maps import prepare, np, linear, image_backend

Image = image_backend()


def read16(path):
    raw = path.read_bytes(); offset = 8; compressed = b''
    while offset < len(raw):
        size = struct.unpack('>I', raw[offset:offset+4])[0]
        kind = raw[offset+4:offset+8]; payload = raw[offset+8:offset+8+size]
        if kind == b'IHDR': width, height, depth, color, _, _, _ = struct.unpack('>IIBBBBB', payload)
        if kind == b'IDAT': compressed += payload
        offset += size+12
    assert depth == 16
    channels = {0:1, 2:3, 6:4}[color]
    rows = zlib.decompress(compressed); size = width*channels*2
    assert len(rows) == height*(size+1)
    values = []
    for row in range(height):
        assert rows[row*(size+1)] == 0
        values.append(np.frombuffer(rows[row*(size+1)+1:(row+1)*(size+1)], dtype='>u2').reshape(width, channels))
    return np.stack(values)/65535


class DecalMapTests(unittest.TestCase):
    def data(self, root):
        (root/'textures').mkdir(exist_ok=True)
        Image.new('RGB', (2, 2), (128, 64, 32)).save(root/'textures/color.png')
        sample = {'op':'texture', 'texture':'color', 'color_space':'sRGB'}
        normal = {'op':'mask', 'input':dict(sample, normal_map=True, color_space='raw'), 'channels':[0, 1, 2]}
        graph = {'op':'power', 'a':{'op':'mask', 'input':sample, 'channels':[0, 1, 2]}, 'b':{'op':'constant', 'value':[2]}}
        return {'decals':[{'material':'decal', 'source':'one'}, {'material':'decal', 'source':'two'}],
                'materials':{'decal':{'name':'Stain', 'domain':'decal', 'decal_channels':['base_color', 'normal'],
                                      'inputs':{'base_color':graph, 'normal':normal}},
                             'wood':{'name':'Wood', 'inputs':{'base_color':copy.deepcopy(graph)}}},
                'textures':{'color':{'file':'textures/color.png'}}}

    def test_precomputes_linear_color_once_preserving_normal_and_receiver(self):
        with fixture_directory() as root:
            data = self.data(root); original = copy.deepcopy(data)
            report = prepare(data, root)
            self.assertEqual(len(report), 1)
            self.assertEqual(report[0]['status'], 'precomputed')
            self.assertEqual(data['materials']['wood'], original['materials']['wood'])
            self.assertEqual(data['materials']['decal']['inputs']['normal'], original['materials']['decal']['inputs']['normal'])
            node = data['materials']['decal']['inputs']['base_color']['input']
            pixels = read16(root/data['textures'][node['texture']]['file'])
            decoded = linear(pixels[..., :3])
            expected = linear(np.array([128, 64, 32])/255)**2
            np.testing.assert_allclose(decoded, np.broadcast_to(expected, decoded.shape), atol=2e-5)
            self.assertEqual(len(data['textures']), 2)
            np.testing.assert_allclose(pixels[..., 3], 1)
            self.assertEqual(data['materials']['decal']['inputs']['opacity']['channels'], [3])

    def test_packed_opacity_preserves_raw_alpha_after_srgb_color_encoding(self):
        with fixture_directory() as root:
            data = self.data(root)
            data['materials']['decal']['inputs']['opacity'] = {'op':'constant', 'value':[.25]}
            report = prepare(data, root)
            texture = data['materials']['decal']['inputs']['opacity']['input']['texture']
            pixels = read16(root/data['textures'][texture]['file'])
            np.testing.assert_allclose(pixels[..., 3], .25, atol=1/65535)
            self.assertEqual(report[0]['packed_channels'], ['base_color', 'opacity'])

    def test_context_dependent_decal_stays_original_and_is_reported(self):
        with fixture_directory() as root:
            data = self.data(root); graph = {'op':'world_position'}
            data['materials']['decal']['inputs']['base_color'] = graph
            report = prepare(data, root)
            self.assertEqual(report[0]['status'], 'original_graph')
            self.assertIn('world_position', report[0]['reason'])
            self.assertEqual(data['materials']['decal']['inputs']['base_color'], graph)

    def test_opacity_above_one_is_reconstructed_before_intensity_clamping(self):
        with fixture_directory() as root:
            data = self.data(root)
            data['materials']['decal']['inputs']['opacity'] = {'op':'constant', 'value':[2]}
            report = prepare(data, root)
            self.assertEqual(report[0]['status'], 'precomputed')
            self.assertEqual(report[0]['opacity_decode'], {'scale':2, 'bias':0})
            opacity = data['materials']['decal']['inputs']['opacity']
            self.assertEqual(opacity['op'], 'multiply')
            sample = opacity['a']['input']
            pixels = read16(root/data['textures'][sample['texture']]['file'])
            restored = pixels[..., 3]*opacity['b']['value'][0]
            np.testing.assert_allclose(restored, 2)
            # A quarter intensity must give half coverage, not quarter coverage.
            np.testing.assert_allclose(np.clip(restored*.25, 0, 1), .5)

    def test_negative_opacity_range_preserves_signed_values_without_clipping(self):
        with fixture_directory() as root:
            data = self.data(root)
            Image.new('RGB', (2, 2), (0, 0, 0)).save(root/'textures/alpha.png')
            with Image.open(root/'textures/alpha.png') as source:
                pixels = source.copy()
            pixels.putpixel((1, 0), (255, 255, 255)); pixels.save(root/'textures/alpha.png')
            data['textures']['alpha'] = {'file':'textures/alpha.png'}
            node = {'op':'mask', 'input':{'op':'texture', 'texture':'alpha'}, 'channels':[0]}
            data['materials']['decal']['inputs']['opacity'] = {'op':'subtract', 'a':{'op':'multiply', 'a':node, 'b':{'op':'constant','value':[4]}}, 'b':{'op':'constant','value':[2]}}
            report = prepare(data, root)
            self.assertEqual(report[0]['opacity_decode'], {'scale':4, 'bias':-2})
            opacity = data['materials']['decal']['inputs']['opacity']
            sample = opacity['a']['a']['input']
            stored = read16(root/data['textures'][sample['texture']]['file'])
            restored = stored[..., 3]*4-2
            np.testing.assert_allclose(restored, [[-2, 2], [-2, -2]])

    def test_excessively_broad_opacity_keeps_original_graph(self):
        with fixture_directory() as root:
            data = self.data(root)
            data['materials']['decal']['inputs']['opacity'] = {'op':'constant','value':[1000]}
            report = prepare(data, root)
            self.assertEqual(report[0]['status'], 'original_graph')
            self.assertIn('too broad', report[0]['reason'])
            self.assertEqual(data['materials']['decal']['inputs']['opacity']['value'], [1000])

    def test_out_of_range_output_is_not_silently_clipped(self):
        with fixture_directory() as root:
            data = self.data(root)
            data['materials']['decal']['inputs']['base_color']['b']['value'] = [-10]
            report = prepare(data, root)
            self.assertEqual(report[0]['status'], 'original_graph')
            self.assertEqual(len(data['textures']), 1)
            self.assertFalse(list((root/'textures').glob('*.partial')))

    def test_source_file_cannot_escape_conversion_folder(self):
        with fixture_directory() as root:
            data = self.data(root); data['textures']['color']['file'] = '../outside.png'
            report = prepare(data, root)
            self.assertEqual(report[0]['status'], 'original_graph')
            self.assertIn('outside', report[0]['reason'])

    def test_hidden_decal_does_not_generate_maps(self):
        with fixture_directory() as root:
            data = self.data(root)
            for d in data['decals']: d['visible'] = False
            self.assertEqual(prepare(data, root), [])
