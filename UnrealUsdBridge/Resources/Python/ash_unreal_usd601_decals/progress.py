"""Overall stage progress; unknown-length Unreal reading is not a file percentage."""
import re


def fraction(message, previous=0.0):
    value = previous
    phases = {
        'Reading input files': .02, 'Preparing a temporary project': .05,
        'Unreal is reading': .10, 'Building USD': .35,
        'Preparing decal receivers': .36, 'Decals disabled;': .36,
        'Grouping repeated static meshes': .75,
    }
    for prefix, amount in phases.items():
        if message.startswith(prefix): value = amount
    for prefix, start, span in (
        ('Preparing decal map', .36,.01), ('Translating material', .37,.13), ('Writing geometry',.50,.15),
        ('Writing material',.65,.10), ('Placing object',.75,.07)):
        match = re.match(re.escape(prefix)+r' (\d+)/(\d+)', message)
        if match:
            index,total = map(int,match.groups())
            value = start+span*max(0,index-1)/max(1,total)
    if message.startswith(('Writing foliage:', 'Writing repeated meshes:')): value = .82
    if message.startswith('BRIDGE_USD_COMPLETE'): value = .85
    # Only the caller's successful completion marks 100%; failures/waits retain
    # the current stage and must never masquerade as a completed conversion.
    if message == 'Conversion complete': value = 1.0
    return min(1.0,max(previous,value))
