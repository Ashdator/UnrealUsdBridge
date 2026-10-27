"""Preserve active emissive graphs and omit unused black defaults."""
from .graph import Constant, Unsupported, evaluate


def uses_emission(material):
    node = material.get('inputs', {}).get('emissive')
    if node is None:
        return False
    # A source parameter initially set to zero is still an editable control.
    def parameter(value):
        if isinstance(value, dict):
            return bool(value.get('parameter')) or any(parameter(v) for v in value.values())
        return isinstance(value, (tuple, list)) and any(parameter(v) for v in value)
    if parameter(node):
        return True
    try:
        value = evaluate(node)
        return not isinstance(value, Constant) or any(v > 0 for v in value.value)
    except Unsupported:
        return True  # Never silently discard a graph we cannot translate.


def prepare(material):
    if not uses_emission(material):
        material.get('inputs', {}).pop('emissive', None)
    if material.get('unlit'):
        material.setdefault('inputs', {}).update(
            base_color={'op':'constant','value':[0,0,0]},
            metallic={'op':'constant','value':[0]},
            roughness={'op':'constant','value':[1]})
        material['inputs'].pop('normal', None)
