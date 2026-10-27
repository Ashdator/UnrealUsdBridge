"""Run USD construction outside the interactive Isaac process.

The process exits before the scene is opened, releasing Python graphs, USD
authoring buffers and allocator arenas rather than retaining them in Kit.
"""
import json
import os
from pathlib import Path
import sys
import traceback


def main():
    manifest=Path(sys.argv[1]); usd=Path(sys.argv[2])
    sys.path[:0]=[str(usd),str(Path(__file__).resolve().parents[1])]
    kit=Path(sys.executable).resolve().parents[1]
    handles=[]
    if os.name=='nt':
        for folder in (usd/'bin',kit,kit/'kernel/plugins'):
            if folder.is_dir(): handles.append(os.add_dll_directory(str(folder)))
    from ash_unreal_usd601_decals.usd_writer import convert
    scene,report=convert(manifest,allow_partial=sys.argv[3]=='1',
                         include_decals=len(sys.argv)<5 or sys.argv[4]=='1',
                         hide_unsupported_sky=len(sys.argv)>=6 and sys.argv[5]=='1',
                         export_cameras=len(sys.argv)<7 or sys.argv[6]=='1',
                         export_lights=len(sys.argv)<8 or sys.argv[7]=='1',
                         progress=lambda value:print(value,flush=True))
    print('BRIDGE_USD_COMPLETE '+str(scene),flush=True)
    return 0


if __name__=='__main__':
    try: sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
