"""Exclude identified water surfaces without treating glass or decals as water."""
import re


def excluded(material):
    if material.get('domain','surface')!='surface':return False
    if material.get('water_surface'):return True
    # Older manifests have no shading-model identity. Use an exact asset/path
    # token AND a translucent surface, never arbitrary substrings or DepthFade.
    source=material.get('name','')+' '+material.get('source','')
    return bool(material.get('translucent') and re.search(r'(?i)(?:^|[_/ .])water(?:$|[_/ .])',source))
