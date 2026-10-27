"""Narrow recovery for completed static exports with legacy character XR errors."""
import json
import re


def character_only_failure(exit_code, log_path, manifest_path, expected_map):
    """Return a report note only when the known unrelated failure is proven.

    Do not use the existence of a manifest alone to bypass an Unreal failure.
    Crashes, unknown errors, incomplete output and exported character references
    remain failures. Unsupported environment materials remain the USD writer's
    responsibility and still obey its strict/partial setting.
    """
    if exit_code != 1:
        return None
    try:
        log=log_path.read_text(encoding='utf-8',errors='replace')
        data=json.loads(manifest_path.read_text(encoding='utf-8-sig'))
        if re.search(r'Fatal error|Assertion failed|Unhandled Exception|Critical error',log,re.I):
            return None
        errors=re.findall(r'\b(Log\w+):\s+(Error|Fatal):\s*(.*)',log)
        if not errors:
            return None
        kinds=set()
        for category,severity,message in errors:
            if category!='LogBlueprint' or severity!='Error':return None
            match=re.fullmatch(r'\[AssetLog\] (.+[\\/]ThirdPersonCharacter\.uasset): \[Compiler\] (.*)',message)
            if not match:return None
            detail=' '.join(match[2].split())
            if detail=='In use pin <Unnamed> no longer exists on node Reset Orientation and Position . Please refresh node or break links to remove pin.':
                kinds.add('pin')
            elif detail=='Could not find a function named "ResetOrientationAndPosition" in \'ThirdPersonCharacter\'.':
                kinds.add('function')
            else:return None
        if kinds!={'pin','function'}:return None
        if 'finished execution (result 0)' not in log or 'LogExit: Exiting.' not in log:return None
        if data.get('schema_version')!=1 or data.get('map')!=expected_map:return None
        for field in ('meshes','materials','textures'):
            if not isinstance(data.get(field),dict):return None
        for field in ('instances','instancers'):
            if not isinstance(data.get(field),list):return None
        complete=re.findall(r'BRIDGE_COMPLETE: (\d+) meshes, (\d+) materials, (\d+) instancer groups',log)
        if len(complete)!=1 or tuple(map(int,complete[0]))!=(len(data['meshes']),len(data['materials']),len(data['instancers'])):return None
        for field in ('meshes','materials','instances','instancers','lights','cameras'):
            if 'thirdpersoncharacter' in json.dumps(data.get(field,[])).lower():return None
        root=manifest_path.parent.resolve()
        for section in ('meshes','textures'):
            for ref in data[section].values():
                file=(root/ref['file']).resolve()
                if root not in file.parents or not file.is_file() or file.stat().st_size==0:return None
        return ('Environment extraction completed. Ignored only the legacy ThirdPersonCharacter '
                'ResetOrientationAndPosition/XRBase Blueprint errors after validating completion, '
                'asset files and absence of character references in the export. See unreal.log; '
                'no character or XR support was added.')
    except (OSError,ValueError,KeyError,TypeError):
        return None
