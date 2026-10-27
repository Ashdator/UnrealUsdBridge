"""Readable Unreal names with deterministic, case-insensitive collision handling."""
import hashlib
import re
from pathlib import Path


def asset_name(source):
    return str(source).rsplit('/', 1)[-1].rsplit('.', 1)[-1]


def safe_name(value):
    value = re.sub(r'[^A-Za-z0-9_]', '_', value) or 'Asset'
    if value[0].isdigit() or value.lower() in {'con','prn','aux','nul','material','float','int','bool','texture_2d','export','import'} or re.fullmatch(r'(com|lpt)[1-9]',value,re.I):
        value = 'Asset_' + value
    return value[:120]


def names(items):
    """Map stable source IDs to preferred names; suffix only collisions."""
    result, used = {}, set()
    for key, label in sorted(items.items()):
        candidate = safe_name(label)
        if candidate.casefold() in used:
            candidate += '_' + hashlib.sha256(key.encode()).hexdigest()[:12]
        while candidate.casefold() in used:
            candidate += '_'
        used.add(candidate.casefold())
        result[key] = candidate
    return result


def material_name(material, textures):
    if material.get('name'):
        return material['name']
    if material.get('source'):
        return asset_name(material['source'])
    def find(node):
        if isinstance(node, dict):
            if node.get('op') == 'texture':
                tex = textures.get(node['texture'], {})
                return asset_name(tex['source']) if tex.get('source') else Path(tex.get('file', node['texture'])).stem
            for child in node.values():
                found = find(child)
                if found: return found
        elif isinstance(node, list):
            for child in node:
                found = find(child)
                if found: return found
    label = find(material.get('inputs', {}).get('base_color', {}))
    if label:
        label = re.sub(r'^(T_|TX_)', '', label, flags=re.I)
        label = re.sub(r'_(BaseColor|Albedo|Diffuse|BC|D)$', '', label, flags=re.I)
        return 'M_' + label
    return 'Material'
