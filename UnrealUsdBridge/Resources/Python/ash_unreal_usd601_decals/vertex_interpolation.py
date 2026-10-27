"""Recognize vertex expressions whose interpolation commutes with evaluation."""


def affine(node,depth=0):
    if depth>128 or not isinstance(node,dict):return False,False
    op=node.get('op')
    if op=='constant':return True,False
    if op in ('uv','vertex_color','world_position','local_position'):
        return True,True
    if op in ('object_position','per_instance_random'):return True,False
    if op in ('distance','cross','normalize','abs','power','floor','ceil'):
        children=[v for k,v in node.items() if k!='op' and isinstance(v,dict)]
        # Nonlinear math of uniform inputs (ObjectScale measured from unit
        # axes, for example) remains uniform. Varying nonlinear math is blocked.
        return (bool(children) and all(affine(v,depth+1)==(True,False) for v in children)),False
    if op=='transform_vector':
        if node.get('from')!=node.get('to') and 'tangent' in (node.get('from'),node.get('to')):
            return False,True
        return affine(node.get('input'),depth+1)
    if op in ('mask','vertex_interpolator'):
        return affine(node.get('input'),depth+1)
    if op in ('add','subtract','append','multiply','divide'):
        a,av=affine(node.get('a'),depth+1);b,bv=affine(node.get('b'),depth+1)
        if not a or not b:return False,False
        if op=='multiply' and av and bv:return False,False
        if op=='divide' and bv:return False,False
        return True,av or bv
    if op=='one_minus':return affine(node.get('input'),depth+1)
    if op=='lerp':
        a,av=affine(node.get('a'),depth+1);b,bv=affine(node.get('b'),depth+1);t,tv=affine(node.get('alpha'),depth+1)
        return (a and b and t and not tv),av or bv
    # Normalization, texture samples, nonlinear triplanar weights and other
    # per-vertex calculations cannot be replaced by a pixel-stage expression.
    return False,False
