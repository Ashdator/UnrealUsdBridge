"""Update texture paths without loading a second copy of placement arrays."""
import json
from pathlib import Path
import re
import shutil

_STRUCT = re.compile(rb'["{}\[\]:,]')
_NESTED = re.compile(rb'["{}\[\]]')
_STRING = re.compile(rb'["\\]')


def texture_span(path, chunk_size=1024*1024):
    depth=0;inside=False;escape=False;capture=False;key=bytearray()
    pending=False;colon=False;start=None;offset=0
    with Path(path).open('rb') as source:
        while chunk:=source.read(chunk_size):
            pos=0
            while pos<len(chunk):
                if inside:
                    if escape:
                        if capture:key.append(chunk[pos])
                        pos+=1;escape=False;continue
                    match=_STRING.search(chunk,pos)
                    if not match:
                        if capture:key.extend(chunk[pos:])
                        break
                    if capture:key.extend(chunk[pos:match.start()])
                    char=chunk[match.start()];pos=match.end()
                    if char==92:
                        if capture:key.append(char)
                        escape=True
                    else:
                        inside=False
                        if capture:
                            pending=json.loads(b'"'+bytes(key)+b'"')=='textures'
                            colon=False
                    continue
                match=(_STRUCT if depth==1 else _NESTED).search(chunk,pos)
                if not match:break
                char=chunk[match.start()];absolute=offset+match.start();pos=match.end()
                if char==34:
                    inside=True;capture=depth==1;key.clear()
                elif char in (123,91):
                    if pending and colon and depth==1:
                        if char!=123:raise ValueError('Manifest textures must be an object')
                        start=absolute
                    depth+=1
                elif char in (125,93):
                    depth-=1
                    if start is not None and depth==1:return start,absolute+1
                elif char==58 and depth==1 and pending:colon=True
                elif char==44 and depth==1:pending=False;colon=False
            offset+=len(chunk)
    raise ValueError('Manifest has no complete top-level textures object')


def update_texture_paths(source_manifest, manifest, textures, *, span=None):
    source_manifest=Path(source_manifest);manifest=Path(manifest)
    start,end=span if span is not None else texture_span(source_manifest)
    temporary=source_manifest.with_name(source_manifest.name+'.paths-writing')
    with source_manifest.open('rb') as source,temporary.open('wb') as target:
        remaining=start
        while remaining:
            block=source.read(min(1024*1024,remaining))
            if not block:raise ValueError('Manifest ended while copying its prefix')
            target.write(block);remaining-=len(block)
        target.write(json.dumps(textures,ensure_ascii=True).encode('utf-8'))
        source.seek(end);shutil.copyfileobj(source,target,1024*1024)
    temporary.replace(source_manifest)
    if manifest.resolve()!=source_manifest.resolve():
        temporary=manifest.with_name(manifest.name+'.paths-writing')
        shutil.copyfile(source_manifest,temporary);temporary.replace(manifest)
