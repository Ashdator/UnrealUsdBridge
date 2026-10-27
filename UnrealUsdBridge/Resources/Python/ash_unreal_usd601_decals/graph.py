"""Lower a resolved Unreal graph to the editable USD Preview Surface subset.

No parameter-name guessing and no image/material baking. An operation that cannot
be represented exactly by this subset raises Unsupported, with its graph path.
"""
from dataclasses import dataclass, replace
import math


class Unsupported(ValueError):
    pass


@dataclass(frozen=True)
class Constant:
    value: tuple


@dataclass(frozen=True)
class UV:
    channel: int = 0
    scale: tuple = (1.0, 1.0)
    offset: tuple = (0.0, 0.0)


@dataclass(frozen=True)
class Sample:
    texture: str
    uv: UV
    channels: tuple = (0, 1, 2)
    scale: tuple = (1.0, 1.0, 1.0, 1.0)
    bias: tuple = (0.0, 0.0, 0.0, 0.0)
    color_space: str = "raw"
    wrap_s: str = "repeat"
    wrap_t: str = "repeat"


def numbers(value):
    result = tuple(float(v) for v in (value if isinstance(value, (list, tuple)) else [value]))
    if not result or not all(math.isfinite(v) for v in result):
        raise Unsupported("Empty or non-finite numeric value")
    return result


def broadcast(value, length):
    if len(value) == length:
        return value
    if len(value) == 1:
        return value * length
    raise Unsupported(f"Cannot broadcast {len(value)} components to {length}")


def mask(value, channels):
    try:
        if isinstance(value, Constant):
            values = value.value * 4 if len(value.value) == 1 else value.value
            return Constant(tuple(values[i] for i in channels))
        if isinstance(value, Sample):
            return replace(value, channels=tuple(value.channels[i] for i in channels))
    except IndexError as exc:
        raise Unsupported("Component mask exceeds input width") from exc
    raise Unsupported("UV component masks / arbitrary swizzles are not supported")


def affine(value, constant, multiply):
    if isinstance(value, Constant):
        size = max(len(value.value), len(constant.value))
        a, b = broadcast(value.value, size), broadcast(constant.value, size)
        return Constant(tuple(x * y if multiply else x + y for x, y in zip(a, b)))
    if isinstance(value, UV):
        c = broadcast(constant.value, 2)
        if multiply:
            return replace(value, scale=tuple(x*y for x,y in zip(value.scale,c)),
                           offset=tuple(x*y for x,y in zip(value.offset,c)))
        return replace(value, offset=tuple(x+y for x,y in zip(value.offset,c)))
    if isinstance(value, Sample):
        c = broadcast(constant.value, len(value.channels))
        scale, bias = list(value.scale), list(value.bias)
        for channel, scalar in zip(value.channels, c):
            if multiply:
                scale[channel] *= scalar
                bias[channel] *= scalar
            else:
                bias[channel] += scalar
        return replace(value, scale=tuple(scale), bias=tuple(bias))
    raise Unsupported("Unsupported arithmetic input")


def evaluate(node, depth=0):
    if depth > 128:
        raise Unsupported("Graph exceeds 128 levels (cycle or excessive nesting)")
    if not isinstance(node, dict):
        raise Unsupported("Missing expression")
    op = node.get("op")
    try:
        if op == "constant":
            return Constant(numbers(node["value"]))
        if op == "uv":
            channel = int(node.get("channel", 0))
            if channel < 0:
                raise Unsupported("Negative UV channel")
            return UV(channel, broadcast(numbers(node.get("scale", [1, 1])), 2))
        if op == "texture":
            if node.get('sampling_issue'):raise Unsupported(node['sampling_issue'])
            if node.get('texture_dimension')=='cube_longlat':
                raise Unsupported('Directional cubemap sampling requires MDL')
            if node.get('usage')=='landscape_weight':
                raise Unsupported('Landscape masks use the MDL bilinear sampler and softness control')
            uv = evaluate(node.get("uv", {"op":"uv"}), depth+1)
            if not isinstance(uv, UV):
                raise Unsupported("Texture coordinates are not affine mesh UVs")
            sample = Sample(node["texture"], uv,
                            channels=tuple(node.get("channels", [0,1,2,3])),
                            color_space=node.get("color_space", "raw"),
                            wrap_s=node.get("wrap_s", "repeat"),
                            wrap_t=node.get("wrap_t", "repeat"))
            if node.get("normal_map"):
                # Source pixels are unchanged. Unreal's DirectX normal convention
                # is converted for the V-flipped USD mesh UVs in shader parameters.
                flip = bool(node.get("flip_green", False))
                sample = replace(sample, scale=(2, 2 if flip else -2, 2, 1),
                                 bias=(-1, -1 if flip else 1, -1, 0), color_space="raw")
            return sample
        if op == "mask":
            return mask(evaluate(node["input"], depth+1), node["channels"])
        if op == 'fmod':
            a,b=evaluate(node['a'],depth+1),evaluate(node['b'],depth+1)
            if isinstance(a,Constant) and isinstance(b,Constant):
                size=max(len(a.value),len(b.value))
                if any(y==0 for y in b.value): raise Unsupported('Signed remainder requires a nonzero divisor')
                return Constant(tuple(math.fmod(x,y) for x,y in zip(broadcast(a.value,size),broadcast(b.value,size))))
            raise Unsupported('Varying signed remainder needs a richer shader backend')
        if op in ('ceil','floor'):
            value=evaluate(node['input'],depth+1)
            if isinstance(value,Constant):
                function=math.ceil if op=='ceil' else math.floor
                return Constant(tuple(float(function(v)) for v in value.value))
            raise Unsupported('Varying rounding needs a richer shader backend')
        if op in ('sin','cos'):
            a=evaluate(node['input'],depth+1)
            if isinstance(a,Constant):
                frequency=numbers(node.get('frequency',1))[0]
                fn=math.sin if op=='sin' else math.cos
                return Constant(tuple(fn(v*frequency) for v in a.value))
            raise Unsupported('Varying trigonometry needs a richer shader backend')
        if op == 'append':
            a,b=evaluate(node['a'],depth+1),evaluate(node['b'],depth+1)
            if isinstance(a,Constant) and isinstance(b,Constant):
                if len(a.value+b.value)>4:raise Unsupported('Append exceeds four components')
                return Constant(a.value+b.value)
            if isinstance(a,Sample) and isinstance(b,Sample):
                if (a.texture,a.uv,a.color_space,a.wrap_s,a.wrap_t)==(b.texture,b.uv,b.color_space,b.wrap_s,b.wrap_t):
                    channels=a.channels+b.channels
                    if len(channels)>4:raise Unsupported('Append exceeds four components')
                    if any((a.scale[c],a.bias[c])!=(b.scale[c],b.bias[c]) for c in set(a.channels)&set(b.channels)):
                        raise Unsupported('Append reuses a channel with different adjustments')
                    scale,bias=list(a.scale),list(a.bias)
                    for c in b.channels:scale[c],bias[c]=b.scale[c],b.bias[c]
                    return replace(a,channels=channels,scale=tuple(scale),bias=tuple(bias))
            raise Unsupported('Append of different varying sources needs a richer shader backend')
        if op == "power":
            b = evaluate(node["b"], depth+1)
            a = evaluate(node["a"], depth+1)
            if isinstance(a, Constant) and isinstance(b, Constant):
                size = max(len(a.value), len(b.value))
                return Constant(tuple(max(x, 0)**y for x,y in zip(broadcast(a.value,size),broadcast(b.value,size))))
            if isinstance(b, Constant) and all(v == 1 for v in b.value) and isinstance(a, Sample):
                # Unreal clamps the base of Power to nonnegative values. The
                # identity is safe for ordinary nonnegative texture inputs, not
                # decoded normals or signed affine adjustments.
                if all(a.scale[i]>=0 and a.bias[i]>=0 for i in a.channels): return a
            raise Unsupported("Texture power needs a richer shader backend")
        if op == "desaturate":
            t = evaluate(node["fraction"], depth+1)
            if isinstance(t, Constant) and all(v == 0 for v in t.value):
                return evaluate(node["input"], depth+1)
            raise Unsupported("Texture desaturation needs a richer shader backend")
        if op == "lerp":
            t = evaluate(node["alpha"], depth+1)
            if not isinstance(t, Constant):
                raise Unsupported("Texture-driven blending needs a richer shader backend")
            if all(v == 0 for v in t.value): return evaluate(node["a"], depth+1)
            if all(v == 1 for v in t.value): return evaluate(node["b"], depth+1)
            a, b = evaluate(node["a"], depth+1), evaluate(node["b"], depth+1)
            if isinstance(a, Constant) and isinstance(b, Constant):
                size = max(len(a.value),len(b.value),len(t.value))
                return Constant(tuple(x+(y-x)*z for x,y,z in zip(broadcast(a.value,size),broadcast(b.value,size),broadcast(t.value,size))))
            raise Unsupported("Normal/detail or color blending needs a richer shader backend")
        if op == "normalize":
            a = evaluate(node["input"], depth+1)
            if isinstance(a, Constant):
                length = math.sqrt(sum(v*v for v in a.value))
                if length: return Constant(tuple(v/length for v in a.value))
            raise Unsupported("Varying normal normalization needs a richer shader backend")
        if op == "one_minus":
            return affine(affine(evaluate(node["input"],depth+1), Constant((-1,)),True), Constant((1,)),False)
        if op in ("add", "multiply", "subtract", "divide"):
            a, b = evaluate(node["a"],depth+1), evaluate(node["b"],depth+1)
            if op == "subtract":
                b = affine(b,Constant((-1,)),True)
                op = "add"
            if op == "divide":
                if not isinstance(b,Constant) or any(x == 0 for x in b.value):
                    raise Unsupported("Division needs a nonzero constant denominator")
                b = Constant(tuple(1/x for x in b.value))
                op = "multiply"
            if isinstance(b, Constant):
                return affine(a,b,op == "multiply")
            if isinstance(a, Constant):
                return affine(b,a,op == "multiply")
            raise Unsupported("Combining two varying expressions needs a richer shader backend")
        if op == "unsupported":
            raise Unsupported(node.get("reason", "Unsupported Unreal expression"))
        raise Unsupported(f"Unknown expression {op!r}")
    except (KeyError, TypeError, IndexError) as exc:
        raise Unsupported(f"Malformed {op!r} expression: {exc}") from exc
    except (OverflowError, ZeroDivisionError) as exc:
        raise Unsupported(f"Invalid arithmetic in {op!r}: {exc}") from exc


INPUTS = {
    "base_color": ("diffuseColor", 3, (0,0,0)),
    "emissive": ("emissiveColor", 3, (0,0,0)),
    "roughness": ("roughness", 1, (0.5,)),
    "metallic": ("metallic", 1, (0,)),
    "normal": ("normal", 3, (0,0,1)),
    "opacity": ("opacity", 1, (1,)),
}


def compile_material(material):
    issues = list(material.get("issues", []))
    inputs = {}
    for name, (_, width, default) in INPUTS.items():
        if name == 'emissive' and name not in material.get('inputs', {}):
            continue
        try:
            result = evaluate(material.get("inputs", {}).get(name, {"op":"constant","value":default}))
            if isinstance(result, Constant):
                result = Constant(broadcast(result.value[:width], width))
            elif isinstance(result, Sample):
                selected = result.channels[:width]
                # USD UVTexture provides rgb or individual channels, no swizzle.
                if width == 3 and selected != (0,1,2):
                    raise Unsupported("Color needs an RGB texture output; channel replication needs MaterialX/MDL")
                if not selected or (width == 1 and len(selected) != 1):
                    raise Unsupported("Invalid texture output width")
                if result.color_space not in ("raw", "sRGB"):
                    raise Unsupported("Unrecognized texture color space")
                if result.wrap_s not in ("repeat","clamp","mirror") or result.wrap_t not in ("repeat","clamp","mirror"):
                    raise Unsupported("Unrecognized texture addressing")
                result = replace(result, channels=selected)
            else:
                raise Unsupported("A UV expression cannot feed a surface property")
            inputs[name] = result
        except Unsupported as exc:
            issues.append(f"{name}: {exc}")
    return inputs, issues
