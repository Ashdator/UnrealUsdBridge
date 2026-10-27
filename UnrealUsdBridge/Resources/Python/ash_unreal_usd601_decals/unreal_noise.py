"""Unreal 5.7 computational Voronoi, without a substituted noise pattern.

The lattice hash, quality searches and octave weighting follow RandomPCG.ush,
Random.ush and Common.ush in the installed Unreal source. MDL's unsigned shift
is essential: a signed shift changes the point distribution.
"""
import math
from .graph import Unsupported


def configuration(node):
    settings = node.get('noise_settings', {})
    if settings.get('function') != 5:
        raise Unsupported('Only computational Unreal Voronoi Noise is translated')
    if 'position' not in node:
        raise Unsupported('Unreal Voronoi currently requires a connected position; implicit large-world position is unsupported')
    quality, levels = settings.get('quality'), settings.get('levels')
    if quality not in (1, 2, 3, 4) or levels not in range(1, 11):
        raise Unsupported('Unreal Voronoi requires quality 1–4 and levels 1–10')
    for key in ('scale', 'level_scale', 'output_min', 'output_max', 'repeat_size'):
        if not isinstance(settings.get(key), (float, int)) or not math.isfinite(settings[key]):
            raise Unsupported('Missing or non-finite Unreal Noise setting: '+key)
    if settings['level_scale'] <= 0 or (settings.get('tiling') and settings['repeat_size'] <= 0):
        raise Unsupported('Invalid Unreal Noise level scale or tile size')
    return settings


HELPERS = '''
// Same 32-bit PCG state and unsigned high-16-bit result as Unreal.
int3 bridge_pcg16(int3 v) {
    v = v * 1664525 + 1013904223;
    v.x += v.y*v.z;
    v.y += v.z*v.x;
    v.z += v.x*v.y;
    v.x += v.y*v.z;
    v.y += v.z*v.x;
    v.z += v.x*v.y;
    return v >>> 16;
}
float3 bridge_noise_wrap(float3 p, uniform bool tiling, float repeat_size) {
    return tiling ? math::frac(p/repeat_size)*repeat_size : p;
}
float3 bridge_voronoi_corner(float3 cell, uniform int quality) {
    float3 jitter = float3(bridge_pcg16(int3(cell)))/65535.0 - 0.5;
    return quality<=2 ? math::normalize(jitter)*0.2588 :
           quality==3 ? math::normalize(jitter)*0.3090 : jitter;
}
float bridge_voronoi_candidate(float3 lattice, float3 fraction, float3 offset,
    uniform int quality, uniform bool tiling, float repeat_size, float seed_offset) {
    float3 jitter = offset + bridge_voronoi_corner(
        bridge_noise_wrap(lattice+offset,tiling,repeat_size)+seed_offset,quality);
    float3 delta = fraction-jitter;
    return math::dot(delta,delta);
}
float bridge_voronoi(float3 p, uniform int quality, uniform bool tiling, float repeat_size) {
    float3 lattice = math::floor(p);
    float3 fraction = math::frac(p);
    float3 shifted_lattice = math::floor(p+0.5);
    float3 shifted_fraction = math::frac(p+0.5);
    float minimum = 100.0;
    uniform int start = quality==3 ? -1 : 0;
    uniform int stop = 1;
    for (int x=start; x<=stop; ++x)
        for (int y=start; y<=stop; ++y)
            for (int z=start; z<=stop; ++z) {
                float3 offset = float3(x,y,z);
                minimum = math::min(minimum,bridge_voronoi_candidate(
                    quality==3 ? shifted_lattice : lattice,
                    quality==3 ? shifted_fraction : fraction,
                    offset,quality,tiling,repeat_size,0.0));
                if (quality==2)
                    minimum = math::min(minimum,bridge_voronoi_candidate(
                        shifted_lattice,shifted_fraction,offset,quality,tiling,repeat_size,467.0));
            }
    if (quality==4)
        for (int x=-1; x<=2; x+=3)
            for (int y=0; y<=1; ++y)
                for (int z=0; z<=1; ++z) {
                    minimum = math::min(minimum,bridge_voronoi_candidate(lattice,fraction,float3(x,y,z),quality,tiling,repeat_size,0.0));
                    minimum = math::min(minimum,bridge_voronoi_candidate(lattice,fraction,float3(y,z,x),quality,tiling,repeat_size,0.0));
                    minimum = math::min(minimum,bridge_voronoi_candidate(lattice,fraction,float3(z,x,y),quality,tiling,repeat_size,0.0));
                }
    return math::sqrt(minimum)*2.0-1.0;
}
float bridge_unreal_noise(float3 position, float filter_width, uniform float scale,
    uniform int quality, uniform int levels, uniform float level_scale,
    uniform float output_min, uniform float output_max,
    uniform bool turbulence, uniform bool tiling, uniform float repeat_size) {
    position *= scale;
    filter_width *= scale;
    float amplitude = 1.0;
    float result = 0.0;
    float tile = repeat_size;
    for (int level=0; level<levels; ++level) {
        amplitude *= math::clamp(1.0-filter_width,0.0,1.0);
        float value = bridge_voronoi(position,quality,tiling,tile);
        result += (turbulence ? math::abs(value) : value)*amplitude;
        position *= level_scale;
        tile *= level_scale;
        amplitude /= level_scale;
        filter_width *= level_scale;
    }
    if (!turbulence) result=result*0.5+0.5;
    return math::lerp(output_min,output_max,result);
}
'''
