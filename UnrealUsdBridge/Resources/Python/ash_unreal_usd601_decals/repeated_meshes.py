"""Plan PointInstancers for repeated ordinary static mesh components."""
import hashlib
import json
from collections import Counter

IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def prepare(data, mesh_data, representable):
    buckets, skipped = {}, Counter()
    for instance in data['instances']:
        mesh_id = instance['mesh']
        mesh = mesh_data[mesh_id]
        reference = data['meshes'][mesh_id]
        if instance.get('mesh_kind') == 'skeletal_rest_pose' or reference.get('mesh_kind') == 'skeletal_rest_pose':
            skipped['skeletal_rest_pose'] += 1
            continue
        source = (reference.get('source', '') + ' ' + instance.get('name', '')).casefold()
        if mesh.get('unified_landscape') or 'landscape' in mesh.get('geometry_source', '').casefold():
            skipped['landscape'] += 1
            continue
        if 'skysphere' in source or 'skydome' in source:
            skipped['sky'] += 1
            continue
        if not representable(instance['matrix']):
            skipped['non_srt_transform'] += 1
            continue
        buckets.setdefault((mesh_id, bool(instance.get('visible', True))), []).append(instance)

    consumed, groups = set(), []
    for (mesh_id, visible), members in buckets.items():
        if len(members) < 2:
            continue
        prototypes, lookup, indices = [], {}, []
        for instance in members:
            # Geometry IDs are shared; local material/paint/face partitions must
            # match too. Decal recipes have already been assigned by this stage.
            prototype = {'materials': instance['materials']}
            for key in ('colors', 'decal_sections'):
                if instance.get(key):
                    prototype[key] = instance[key]
            digest = hashlib.sha256(json.dumps(prototype, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            if digest not in lookup:
                lookup[digest] = len(prototypes)
                prototypes.append(prototype)
            indices.append(lookup[digest])
            consumed.add(instance['source'])
        mesh_name = data['meshes'][mesh_id].get('source', mesh_id).rsplit('/', 1)[-1].split('.')[0]
        group = {
            'name': mesh_name + '_Repeated',
            'source': 'bridge:repeated_static:' + mesh_id + (':visible' if visible else ':hidden'),
            'mesh': mesh_id, 'materials': members[0]['materials'],
            'matrix': list(IDENTITY), 'visible': visible,
            'instance_source': 'bridge_repeated_static',
            'prototypes': prototypes, 'decal_proto_indices': indices,
            'transforms': [i['matrix'] for i in members],
            'source_components': [i['source'] for i in members],
            'source_names': [i['name'] for i in members],
        }
        if any('object_position' in i for i in members):
            group['object_positions'] = [i.get('object_position', [0, 0, 0]) for i in members]
        groups.append(group)
    remaining = [i for i in data['instances'] if i['source'] not in consumed]
    audit = {'policy': 'Automatic PointInstancers for repeated static meshes; per-prototype materials, vertex paint and decal regions preserved.',
             'source_placements': len(data['instances']), 'individual_mesh_prims': len(remaining),
             'instances': len(consumed), 'groups': len(groups),
             'prototypes': sum(len(g['prototypes']) for g in groups),
             'excluded_placements': dict(skipped),
             'meshes': [{'mesh': g['mesh'], 'name': g['name'], 'source': data['meshes'][g['mesh']].get('source', ''),
                         'instances': len(g['transforms']), 'prototypes': len(g['prototypes']), 'visible': g['visible']}
                        for g in groups]}
    return remaining, groups, audit
