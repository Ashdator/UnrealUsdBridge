"""Run portable regression tests with Isaac Sim's bundled Python/USD."""
import argparse,os,sys,unittest
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--isaac',type=Path,required=True,help='Isaac Sim 6.0.1 installation folder')
    args=parser.parse_args()
    if os.name!='nt':parser.error('The supported test runtime is Windows x64.')
    isaac=args.isaac.resolve()
    if not (isaac/'kit/python/python.exe').is_file():parser.error('Missing kit/python/python.exe in the Isaac installation.')
    tag=f'cp{sys.version_info.major}{sys.version_info.minor}'
    candidates=sorted((isaac/'extscache').glob('omni.usd.libs-*.wx64.r.'+tag))
    if not candidates:parser.error('No matching USD runtime. Run this script with Isaac bundled Python.')
    usd=candidates[-1];root=Path(__file__).resolve().parents[1]
    sys.dont_write_bytecode=True
    os.environ['PYTHONDONTWRITEBYTECODE']='1'
    os.environ['UNREAL_USD_BRIDGE_ISAAC']=str(isaac)
    os.chdir(root)
    sys.path[:0]=[str(usd),str(root/'UnrealUsdBridge/Resources/Python'),str(root/'tests')]
    handles=[os.add_dll_directory(str(p)) for p in (usd/'bin',isaac/'kit',isaac/'kit/kernel/plugins')]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(str(root/'tests')))
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':sys.exit(main())
