"""Identify vegetation receivers without treating every instanced prop as a plant."""
import re


_PLANT_WORDS = frozenset((
    'foliage', 'vegetation', 'tree', 'trees', 'grass', 'grasses', 'bush',
    'bushes', 'shrub', 'shrubs', 'plant', 'plants', 'fern', 'ferns', 'ivy',
    'flower', 'flowers', 'reed', 'reeds', 'cattail', 'cattails', 'palm',
    'palms', 'sapling', 'saplings',
))


def plant_asset_name(value):
    # Inspect the asset leaf only: a prop in a /Foliage/ directory is still a
    # prop. Split CamelCase and digits so GrassPatch and Grass_01 both work.
    leaf = str(value).rsplit('/', 1)[-1].split('.', 1)[0]
    leaf = re.sub(r'([a-z])([A-Z])', r'\1_\2', leaf)
    words = set(re.findall(r'[a-z]+', leaf.lower()))
    return bool(words & _PLANT_WORDS) or {'cat', 'tail'} <= words


def exclusion_reason(data, instance):
    """Return a reason for rejecting the entire vegetation component, or None.

    Rejecting the whole component also protects bark slots on a tree whose
    leaf slots use Unreal foliage shading. Geometry and source settings stay
    unchanged. Foliage-tool placement alone is not a vegetation classifier.
    """
    mesh = data['meshes'].get(instance['mesh'], {})
    if mesh.get('foliage') or mesh.get('vegetation') or instance.get('vegetation'):
        return 'vegetation metadata'
    for key in instance.get('materials', []):
        material = data['materials'].get(key, {})
        if material.get('foliage'):
            return 'Unreal foliage shading model'
    if any(plant_asset_name(mesh.get(field, '')) for field in ('source', 'name')):
        return 'vegetation mesh asset name'
    for key in instance.get('materials', []):
        material = data['materials'].get(key, {})
        if any(plant_asset_name(material.get(field, '')) for field in ('source', 'name')):
            return 'vegetation material asset name'
    return None
