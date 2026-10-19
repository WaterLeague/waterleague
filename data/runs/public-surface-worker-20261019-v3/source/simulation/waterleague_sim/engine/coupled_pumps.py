"""원 관망에 결속한 펌프 설계를 저류·지표 파생 뒤에 합성."""
import hashlib
from pathlib import Path

from .connected_pumps import compile_pumps
from .flood_errors import require
from ..ingestion.published_network import digest


def compile(original, prepared):
    request = original['connectedPumpDesign']
    source = original['network']['inputText'].encode()
    current = prepared['network']['inputText'].encode()
    require(isinstance(request, dict) and request.get('sourceNetworkSha256') == digest(source),
            'COUPLED_PUMP_SOURCE_BINDING_INVALID')
    used = {str(p['id']).upper() for key in ('connectedStorageDesign', 'connectedFacilityDesign', 'surfaceBasinDesign')
            for p in original.get(key, {}).get('placements', [])}
    require(isinstance(request.get('placements'), list)
        and all(isinstance(p, dict) and isinstance(p.get('id'), str) and p['id'].upper() not in used
                for p in request['placements']), 'COUPLED_PUMP_SHARED_ID_CONFLICT')
    raw, design = compile_pumps(current, request | {'sourceNetworkSha256': digest(current)})
    metadata = {'schemaVersion': 1, 'originalNetworkSha256': digest(source),
        'preparedNetworkSha256': digest(current), 'derivedNetworkSha256': digest(raw),
        'request': request, 'compiled': design,
        'adapterSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'rankingEligible': False}
    return prepared | {'network': prepared['network'] | {'inputText': raw.decode()}}, metadata


def summary(metadata, operation):
    return {'design': metadata, 'operation': operation,
        'scope': 'INTERNAL_TRANSFER_ALREADY_INCLUDED_IN_NETWORK_AND_SURFACE_BALANCE',
        'additionalExternalInflowM3': 0, 'additionalExternalOutflowM3': 0,
        'rankingEligible': False, 'completeInstalledCostKrw': None}
