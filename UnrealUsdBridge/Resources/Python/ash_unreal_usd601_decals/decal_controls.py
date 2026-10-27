"""Copy shared decal intensity to renderer-visible MDL values on demand.

RTX does not propagate edits to interfaces outside a material. Ordinary
local shader values keep a saved USD portable. No simulation or polling.
"""
from pathlib import Path
import os
from pxr import Sdf, Tf, Usd

SOURCE_KEY = "unreal:decalControl"


def same_value(left,right):
    if isinstance(left,Sdf.AssetPath) and isinstance(right,Sdf.AssetPath):
        if left.resolvedPath and right.resolvedPath:
            return os.path.normcase(left.resolvedPath)==os.path.normcase(right.resolvedPath)
        return left.path==right.path
    return left==right


def copy_value(value,layer):
    if isinstance(value,Sdf.AssetPath) and value.resolvedPath:
        return Sdf.AssetPath(os.path.relpath(value.resolvedPath,Path(layer.realPath).parent).replace('\\','/')) if layer.realPath else Sdf.AssetPath(value.resolvedPath.replace('\\','/'))
    return value


class DecalControls:
    def __init__(self, stage, schedule=None):
        self.stage = stage
        self.schedule = schedule
        self.pending = set()
        self.queued = False
        self.closed = False
        self.writing = False
        self.targets_dirty = False
        self.targets = {}
        self._scan_targets()
        self.notice = Tf.Notice.Register(Usd.Notice.ObjectsChanged, self._changed, stage)
        self.pending.update(self.targets)
        self.pending.update(self.leaf_targets)
        self.flush()

    def _scan_targets(self):
        self.targets={}
        self.leaf_targets={}
        stage=self.stage
        for prim in stage.Traverse():
            for attr in prim.GetAttributes():
                leaf=attr.GetCustomDataByKey('unreal:leafColorTarget')
                if leaf:self.leaf_targets[attr.GetPath()]=leaf
                base=attr.GetCustomDataByKey('unreal:baseControl')
                if base:self.targets.setdefault(Sdf.Path(base),[]).append(attr)
                source = attr.GetCustomDataByKey(SOURCE_KEY)
                if source and str(source).endswith('.inputs:amount'):
                    self.targets.setdefault(Sdf.Path(source), []).append(attr)

    def _changed(self, notice, sender):
        if self.closed or self.writing:
            return
        paths = notice.GetChangedInfoOnlyPaths()
        resync = notice.GetResyncedPaths()
        if any(path.HasPrefix('/World/Looks') or Sdf.Path('/World/Looks').HasPrefix(path) for path in resync):
            self.targets_dirty=True
            if not self.queued:
                self.queued=True
                if self.schedule:self.schedule(self.flush)
                else:self.flush()
            return
        if not any(path.HasPrefix('/World/Decals') or path.HasPrefix('/World/Looks') for path in list(paths)+list(resync)):
            return
        for source in set(self.targets)|set(self.leaf_targets):
            if source in paths or any(source.HasPrefix(path) for path in resync):
                self.pending.add(source)
        if self.pending and not self.queued:
            self.queued = True
            if self.schedule:
                self.schedule(self.flush)
            else:
                self.flush()

    def flush(self):
        self.queued = False
        if self.closed:
            return
        if self.targets_dirty:
            self.targets_dirty=False;self._scan_targets();self.pending.update(self.targets);self.pending.update(self.leaf_targets)
        if not self.pending:return
        pending, self.pending = self.pending, set()
        self.writing = True
        try:
            # Respect the current edit layer. Opening saved scenes with
            # matching values does not author opinions or dirty the stage.
            with Sdf.ChangeBlock():
                for path in pending:
                    if path in self.leaf_targets:
                        from .leaf_controls import update_preview
                        update_preview(self.stage,self.leaf_targets[path])
                    source = self.stage.GetAttributeAtPath(path)
                    if not source:
                        continue
                    value = source.Get()
                    for target in self.targets.get(path,[]):
                        if not target:continue
                        layer=self.stage.GetEditTarget().GetLayer()
                        if value is not None and not same_value(target.Get(),value):target.Set(copy_value(value,layer))
                        if target.GetCustomDataByKey('unreal:baseControl'):
                            if target.GetConnections()!=source.GetConnections():target.SetConnections(source.GetConnections())
                            if target.GetColorSpace()!=source.GetColorSpace():target.SetColorSpace(source.GetColorSpace())
                            source_times=set(source.GetTimeSamples());target_times=set(target.GetTimeSamples())
                            for time in target_times-source_times:target.ClearAtTime(time)
                            for time in source_times:
                                time_value=source.Get(time)
                                if not same_value(target.Get(time),time_value):target.Set(copy_value(time_value,layer),time)
        finally:
            self.writing = False

    def close(self):
        self.closed = True
        self.notice.Revoke()
        self.pending.clear()
        self.targets.clear()
        self.leaf_targets.clear()
        self.stage = None
