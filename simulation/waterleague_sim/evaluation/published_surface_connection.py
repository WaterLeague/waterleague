"""공개 원본·교환 가정과 실제 관망/지표 입력의 재생 대조."""
from .exception import require, EvaluationError
from ..engine.flood_errors import FloodModelError
from ..engine.published_surface_connection import validate
from ..engine.coupled_numerics import compile as compile_numerics


def verify(model, result, root, read, file_digest):
    if 'publishedSurfaceConnection' not in model:
        require('publishedSurfaceConnection' not in result, 'EVALUATION_PUBLIC_CONNECTION_UNBOUND')
        return
    try:
        summary = validate(model)
        prepared, _ = compile_numerics(model)
        if 'connectedFacilityDesign' in model:
            from ..engine.connected_facilities import compile_design
            raw, _ = compile_design(prepared['network']['inputText'].encode(), model['connectedFacilityDesign'])
            prepared = prepared | {'network': prepared['network'] | {'inputText': raw.decode()}}
    except FloodModelError:
        raise EvaluationError('EVALUATION_PUBLIC_CONNECTION_INVALID') from None
    names = ('published-surface-connection.json', 'published_surface_connection.py')
    require(all(name in result['files'] for name in names)
            and read(root/names[0]) == summary == result.get('publishedSurfaceConnection')
            and file_digest(root/names[1]) == summary['compilerSha256'],
            'EVALUATION_PUBLIC_CONNECTION_PROVENANCE_MISMATCH')
    require((root/'network/network.inp').read_bytes() == prepared['network']['inputText'].encode()
            and read(root/'surface/surface-input.json') == prepared['surface'] | {
                'evaluationMetrics': prepared['evaluationMetrics']},
            'EVALUATION_PUBLIC_CONNECTION_NATIVE_MISMATCH')
