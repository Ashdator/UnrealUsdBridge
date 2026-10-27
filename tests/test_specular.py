import unittest
from ash_unreal_usd601_decals.graph import compile_material
from ash_unreal_usd601_decals.mdl import compile_mdl


class SpecularTests(unittest.TestCase):
    def test_specular_is_not_a_custom_preview_input(self):
        result, issues = compile_material({'inputs': {'specular': {'op':'constant','value':[.25]}}})
        self.assertFalse(issues)
        self.assertNotIn('specular', result)

    def test_mdl_keeps_the_legacy_fixed_dielectric_lobe(self):
        program, issues = compile_mdl({'inputs': {'base_color': {'op':'constant','value':[.2,.3,.4]}}}, {})
        self.assertFalse(issues)
        self.assertIn('normal_reflectivity:0.08', program['source'])
        self.assertIn('weight:0.5', program['source'])

    def test_specular_only_graph_does_not_create_a_custom_control(self):
        program, issues = compile_mdl({'inputs': {'specular': {'op':'unsupported','reason':'Specular custom graph'}}}, {})
        self.assertFalse(issues)
        self.assertIsNotNone(program)
        self.assertNotIn('useSpecularWorkflow', program['source'])


if __name__ == '__main__':
    unittest.main()
