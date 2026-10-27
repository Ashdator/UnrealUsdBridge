import unittest
from ash_unreal_usd601_decals.graph import evaluate, Constant, Unsupported
from ash_unreal_usd601_decals.mdl import compile_mdl,Compiler


def constant(value):
    return {'op':'constant','value':value if isinstance(value,list) else [value]}


class MaterialCompatibilityTests(unittest.TestCase):
    def test_only_proven_zero_depth_offset_can_remove_its_blocker(self):
        from ash_unreal_usd601_decals.material_policy import main_normals
        marker='Connected Pixel Depth Offset is unsupported unless the captured value is provably zero'
        for value in (0,.001):
            material={'inputs':{},'pixel_depth_offset':constant(value),'issues':[marker,'Keep this other issue']}
            prepared,notes=main_normals(material)
            self.assertEqual(marker in prepared['issues'],value!=0)
            self.assertIn('Keep this other issue',prepared['issues'])
            self.assertEqual(material['issues'],[marker,'Keep this other issue'])
    def test_affine_vertex_interpolation_preserves_world_mapping_and_parameters(self):
        node={'op':'vertex_interpolator','input':{'op':'multiply','a':{'op':'world_position'},'b':dict(constant(.01),parameter='World tiling')}}
        program,issues=compile_mdl({'inputs':{'base_color':node}},{})
        self.assertFalse(issues)
        self.assertTrue(any(p['label']=='World tiling' for p in program['parameters'].values()))
        self.assertIn('state::coordinate_world,state::position()',program['source'])

    def test_nonlinear_vertex_interpolation_is_not_silently_evaluated_per_pixel(self):
        for value in ({'op':'normalize','input':{'op':'world_position'}},
                      {'op':'multiply','a':{'op':'world_position'},'b':{'op':'world_position'}},
                      {'op':'divide','a':constant(1),'b':{'op':'uv'}}):
            program,issues=compile_mdl({'inputs':{'base_color':{'op':'vertex_interpolator','input':value}}},{})
            self.assertIsNone(program)
            self.assertIn('Nonlinear VertexInterpolator requires preserved vertex-stage evaluation',issues)

    def test_local_position_preserves_instance_space_and_requires_explicit_origin(self):
        program,issues=compile_mdl({'inputs':{'base_color':{'op':'local_position','origin':'instance','include_offsets':False}}},{})
        self.assertFalse(issues)
        self.assertIn('state::coordinate_object,state::position()',program['source'])
        _,issues=compile_mdl({'inputs':{'base_color':{'op':'local_position','origin':'primitive'}}},{})
        self.assertTrue(issues)

    def test_uniform_object_scale_keeps_vertex_interpolator_affine(self):
        axis={'op':'transform_vector','from':'object','to':'world','input':constant([1,0,0])}
        scale={'op':'distance','a':constant(0),'b':axis}
        node={'op':'vertex_interpolator','input':{'op':'multiply','a':scale,
              'b':{'op':'local_position','origin':'component'}}}
        program,issues=compile_mdl({'inputs':{'base_color':node}},{})
        self.assertFalse(issues);self.assertIn('math::length(',program['source'])
        self.assertIn('unreal_instance_to_component_0',program['source'])
        axis['from']='tangent'
        _,issues=compile_mdl({'inputs':{'base_color':node}},{})
        self.assertTrue(any('Nonlinear VertexInterpolator' in i for i in issues))

    def test_component_and_preskinned_coordinates_are_distinguished(self):
        for origin in ('component','instance_pre_skinning'):
            program,issues=compile_mdl({'inputs':{'base_color':{'op':'local_position','origin':origin}}},{})
            self.assertFalse(issues)
            self.assertEqual('unreal_instance_to_component_0' in program['source'],origin=='component')

    def test_distance_and_cross_product_validate_widths(self):
        for node in ({'op':'distance','a':constant([1,2]),'b':constant([1,2,3])},
                     {'op':'cross','a':constant([1,2]),'b':constant([1,2,3])}):
            _,issues=compile_mdl({'inputs':{'base_color':node}},{})
            self.assertTrue(issues)
        program,issues=compile_mdl({'inputs':{'normal':{'op':'cross','a':constant([1,0,0]),'b':constant([0,1,0])}}},{})
        self.assertFalse(issues);self.assertIn('math::cross(',program['source'])

    def test_two_sided_sign_and_legacy_node_keep_front_back_sign(self):
        for node in ({'op':'two_sided_sign'},{'op':'unsupported','reason':'MaterialExpressionTwoSidedSign at /Game/Leaf:Sign'}):
            program,issues=compile_mdl({'two_sided':True,'inputs':{'roughness':node}}, {})
            self.assertFalse(issues)
            self.assertNotIn('state::direction()',program['source'])
            self.assertIn('backface:back.surface',program['source'])
            self.assertTrue(program['two_sided_sign_surfaces'])

    def test_two_sided_sign_cannot_silently_change_cutout_between_faces(self):
        program,issues=compile_mdl({'two_sided':True,'inputs':{'opacity':{'op':'two_sided_sign'}}},{})
        self.assertIsNone(program)
        self.assertTrue(any('shared cutout' in issue for issue in issues))

    def test_world_normal_uses_world_to_internal_transform_not_tangent_basis(self):
        program,issues=compile_mdl({'normal_space':'world','inputs':{'normal':constant([0,1,0])}}, {})
        self.assertFalse(issues)
        self.assertIn('state::transform_normal(state::coordinate_world,state::coordinate_internal,',program['source'])
        self.assertNotIn('float3 tangent_normal =',program['source'])

    def test_legacy_world_normal_diagnostic_recovers_only_the_known_flag(self):
        from ash_unreal_usd601_decals.material_policy import main_normals
        mat={'inputs':{'normal':constant([0,0,1])},'issues':['World-space normal materials are not translated','Another unsupported effect']}
        resolved,notes=main_normals(mat)
        self.assertEqual(resolved['normal_space'],'world')
        self.assertEqual(resolved['issues'],['Another unsupported effect'])
        self.assertEqual(len(mat['issues']),2)

    def test_signed_remainder_matches_unreal_for_both_divisor_signs(self):
        for divisor in (2,-2):
            node={'op':'fmod','a':constant([-3.25,3.25,-2.5]),'b':constant(divisor)}
            self.assertEqual(evaluate(node),Constant((-1.25,1.25,-0.5)))

    def test_zero_divisor_is_reported_as_unsupported(self):
        with self.assertRaisesRegex(Unsupported,'nonzero divisor'):
            evaluate({'op':'fmod','a':constant(1),'b':constant(0)})

    def test_varying_remainder_uses_mdl_and_keeps_original_uv_channel(self):
        node={'op':'fmod','a':{'op':'uv','channel':1,'scale':[2,3]},'b':constant([1,2])}
        with self.assertRaisesRegex(Unsupported,'richer shader backend'):evaluate(node)
        texture={'op':'texture','texture':'original','uv':node,'color_space':'sRGB'}
        program,issues=compile_mdl({'inputs':{'base_color':texture}},
                                  {'original':{'file':'textures/original.png'}})
        self.assertFalse(issues)
        self.assertEqual(program['uv_channels'],[1])
        self.assertIn('math::fmod(',program['source'])
        self.assertEqual(len([p for p in program['parameters'].values() if p['type']=='texture_2d']),1)

    def test_collection_names_do_not_collide_but_keep_readable_labels(self):
        a=dict(constant(0.3),parameter='/Game/A/MPC.MPC::Roughness',parameter_label='MPC.Roughness')
        b=dict(constant(0.6),parameter='/Game/B/MPC.MPC::Roughness',parameter_label='MPC.Roughness')
        program,issues=compile_mdl({'inputs':{'roughness':{'op':'multiply','a':a,'b':b}}},{})
        self.assertFalse(issues)
        params=[p for p in program['parameters'].values() if p.get('label')=='MPC.Roughness']
        self.assertEqual(len(params),2)
        self.assertEqual(sorted(p['value'] for p in params),[0.3,0.6])

    def test_fmod_rejects_incompatible_vector_widths(self):
        _,issues=compile_mdl({'inputs':{'roughness':{'op':'fmod',
            'a':constant([1,2]),'b':constant([1,2,3])}}},{})
        self.assertTrue(any('matching vector widths' in issue for issue in issues))

    def test_cube_uses_directional_sampling_and_preserves_hdr_texture(self):
        textures={'hdr':{'file':'textures/City.exr','resolution':[2048,1024]}}
        cube={'op':'texture','texture':'hdr','texture_dimension':'cube_longlat',
              'direction':{'op':'reflection_vector'},'color_space':'raw'}
        with self.assertRaisesRegex(Unsupported,'cubemap sampling requires MDL'):evaluate(cube)
        program,issues=compile_mdl({'inputs':{'base_color':cube}},textures)
        self.assertFalse(issues)
        self.assertIn('state::direction()',program['source'])
        self.assertIn('math::atan2(',program['source'])
        self.assertIn('tex::wrap_repeat, tex::wrap_clamp',program['source'])
        params=[p for p in program['parameters'].values() if p['type']=='texture_2d']
        self.assertEqual([(p['file'],p['color_space']) for p in params],[('textures/City.exr','raw')])

    def test_cube_requires_real_three_component_direction_and_resolution(self):
        cube={'op':'texture','texture':'hdr','texture_dimension':'cube_longlat','direction':constant([1,0])}
        _,issues=compile_mdl({'inputs':{'base_color':cube}},{'hdr':{'file':'City.exr','resolution':[4,2]}})
        self.assertTrue(any('three components' in issue for issue in issues))
        cube['direction']=constant([1,0,0])
        _,issues=compile_mdl({'inputs':{'base_color':cube}},{'hdr':{'file':'City.exr'}})
        self.assertTrue(any('resolution is missing' in issue for issue in issues))

    def test_normal_dependency_cycle_is_reported_for_cube_reflection(self):
        cube={'op':'texture','texture':'hdr','texture_dimension':'cube_longlat','direction':{'op':'reflection_vector'}}
        _,issues=compile_mdl({'inputs':{'normal':cube}},{'hdr':{'file':'City.exr','resolution':[4,2]}})
        self.assertTrue(any('normal dependency cycle' in issue.lower() for issue in issues))

    def test_vector_transform_supports_surface_and_object_coordinate_pairs(self):
        for source in ('tangent','object','world'):
            for target in ('tangent','object','world'):
                node={'op':'transform_vector','from':source,'to':target,'input':constant([0.2,0.3,0.4])}
                program,issues=compile_mdl({'inputs':{'base_color':node}}, {})
                self.assertFalse(issues,(source,target,issues))
                compiler=Compiler({});result=compiler.compile(node)
                self.assertEqual(result[1],3)
                self.assertNotIn('math::normalize(','\n'.join(compiler.lines))

    def test_vector_transform_reports_unavailable_camera_space_and_bad_width(self):
        for node in ({'op':'transform_vector','from':'camera','to':'world','input':constant([1,0,0])},
                     {'op':'transform_vector','from':'tangent','to':'world','input':constant([1,0])}):
            _,issues=compile_mdl({'inputs':{'base_color':node}}, {})
            self.assertTrue(issues)

    def test_materialx_remap_equation_extrapolates_and_preserves_texture_adjustment(self):
        # The remap's affine range equation must retain values outside the input
        # interval, and a packed texture channel should remain editable.
        low,high,target_low,target_high=constant(-2),constant(2),constant(10),constant(18)
        def remap(value):
            return {'op':'add','a':target_low,'b':{'op':'multiply',
                'a':{'op':'subtract','a':value,'b':low},
                'b':{'op':'divide','a':{'op':'subtract','a':target_high,'b':target_low},
                     'b':{'op':'subtract','a':high,'b':low}}}}
        self.assertEqual(evaluate(remap(constant(3))),Constant((20.0,)))
        from ash_unreal_usd601_decals.graph import Sample
        value={'op':'mask','input':{'op':'texture','texture':'packed'},'channels':[1]}
        sample=evaluate(remap(value))
        self.assertIsInstance(sample,Sample)
        self.assertEqual((sample.texture,sample.channels,sample.scale[1],sample.bias[1]),('packed',(1,),2.0,14.0))

    def test_rounding_preserves_negative_values_and_mdl_texture_sampling(self):
        values=constant([-2.5,2.5,-3,0])
        self.assertEqual(evaluate({'op':'ceil','input':values}),Constant((-2,3,-3,0)))
        self.assertEqual(evaluate({'op':'floor','input':values}),Constant((-3,2,-3,0)))
        for operation in ('ceil','floor'):
            texture={'op':'texture','texture':'source','uv':{'op':operation,'input':{'op':'uv','channel':1}}}
            program,issues=compile_mdl({'inputs':{'base_color':texture}},{'source':{'file':'source.png'}})
            self.assertFalse(issues)
            self.assertEqual(program['uv_channels'],[1])
            self.assertIn('math::'+operation+'(',program['source'])

    def test_vertex_normal_remains_independent_of_surface_normal_dependencies(self):
        compiler=Compiler({});compiler.surface_normal={'op':'unsupported','reason':'unavailable normal map'}
        result=compiler.compile({'op':'vertex_normal'})
        self.assertEqual(result[1],3)
        self.assertIn('state::normal()','\n'.join(compiler.lines))
        self.assertNotIn('state::texture_tangent_','\n'.join(compiler.lines))
