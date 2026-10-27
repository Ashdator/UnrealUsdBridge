import unittest
from ash_unreal_usd601_decals.graph import Unsupported
from ash_unreal_usd601_decals.mdl import compile_mdl, compile_function
from ash_unreal_usd601_decals.shared_base import evaluator


def noise(**changes):
    settings = dict(function=5, quality=1, levels=2, scale=1., level_scale=2.,
                    output_min=0., output_max=1., turbulence=True, tiling=False,
                    repeat_size=512, position_origin=0)
    settings.update(changes)
    return {'op':'unreal_noise', 'noise_settings':settings,
            'position':{'op':'append','a':{'op':'uv','channel':1},
                        'b':{'op':'constant','value':[0]}}}


class UnrealNoiseTests(unittest.TestCase):
    def test_all_quality_tiling_and_turbulence_settings_are_preserved(self):
        for quality in range(1,5):
            for tiling in (False,True):
                for turbulence in (False,True):
                    program,issues=compile_mdl({'inputs':{'roughness':noise(quality=quality,tiling=tiling,turbulence=turbulence)}},{})
                    self.assertFalse(issues,issues)
                    self.assertEqual(program['uv_channels'],[1])
                    self.assertIn('return v >>> 16;',program['source'])
                    self.assertEqual(program['source'].count('float bridge_unreal_noise('),1)

    def test_captured_noise_diagnostics_can_be_reprocessed_without_new_extraction(self):
        node=noise();node['op']='unsupported';node['reason']='MaterialExpressionNoise at /Game/Parent:Noise'
        program,issues=compile_mdl({'inputs':{'roughness':node}},{})
        self.assertFalse(issues)
        self.assertIn('bridge_unreal_noise(',program['source'])

    def test_other_noise_algorithms_or_implicit_positions_are_not_substituted(self):
        for function in range(5):
            _,issues=compile_mdl({'inputs':{'roughness':noise(function=function)}},{})
            self.assertTrue(any('Only computational' in issue for issue in issues))
        node=noise();del node['position']
        _,issues=compile_mdl({'inputs':{'roughness':node}},{})
        self.assertTrue(any('connected position' in issue for issue in issues))

    def test_invalid_settings_width_and_missing_filter_input_are_reported(self):
        for changed in (dict(quality=0),dict(levels=11),dict(level_scale=0),dict(scale=float('nan')),
                        dict(tiling=True,repeat_size=0)):
            _,issues=compile_mdl({'inputs':{'roughness':noise(**changed)}},{})
            self.assertTrue(issues,changed)
        node=noise();node['position']={'op':'uv'}
        _,issues=compile_mdl({'inputs':{'roughness':node}},{})
        self.assertTrue(any('three components' in issue for issue in issues))
        node=noise();node['filter_width']={'op':'unsupported','reason':'derivative input missing'}
        _,issues=compile_mdl({'inputs':{'roughness':node}},{})
        self.assertIn('derivative input missing',issues)

    def test_original_parameter_and_filter_width_remain_editable(self):
        node=noise();node['filter_width']={'op':'constant','value':[.2],'parameter':'Noise footprint'}
        node['position']={'op':'multiply','a':node['position'],
                          'b':{'op':'constant','value':[4],'parameter':'Noise scale'}}
        program,issues=compile_mdl({'inputs':{'roughness':node}},{})
        self.assertFalse(issues)
        self.assertTrue({'Noise footprint','Noise scale'} <= {p['label'] for p in program['parameters'].values()})

    def test_helpers_exist_in_function_and_shared_base_backends_only_when_needed(self):
        node=noise()
        programs=(compile_function(node,{},'float'),evaluator({'inputs':{'roughness':node}},{}))
        for program in programs:self.assertIn('float bridge_unreal_noise(',program['source'])
        program,issues=compile_mdl({'inputs':{}},{})
        self.assertFalse(issues)
        self.assertNotIn('bridge_pcg16',program['source'])
