"""지하 저류·역류 수치 진단 입력. 서울 실제 자산이나 설치 후보가 아님."""
from copy import deepcopy

from waterleague_sim.ingestion.published_network import digest
from waterleague_sim.reference.coupled_facilities import coupled_facility_case


def design(raw, *, inlet='TANK', receiver='RECEIVER', invert=0., depth=1.4, area=.25,
           initial=0., inlet_crest=.2, drain_crest=.05, overflow_crest=.9, flap=False):
    evidence = '명시적 수치 시험 설계; 실제 서울 시설 치수·용량·계수 아님'
    def port(node, crest, diameter):
        return {'nodeId': node, 'crestM': crest, 'diameterM': diameter,
                'dischargeCoefficient': .65, 'flapGate': flap, 'evidence': evidence}
    return {'schemaVersion': 1, 'sourceNetworkSha256': digest(raw), 'placements': [{
        'id': 'Tank', 'facilityType': 'UNDERGROUND_STORAGE', 'basis': 'EXPLICIT_DESIGN_NOT_SITE_MEASURED',
        'evidence': evidence, 'invertM': invert,
        'depthAreaCurve': [{'depthM': 0., 'areaM2': area}, {'depthM': depth, 'areaM2': area}],
        'initialDepthM': initial, 'surchargeDepthM': 0., 'cover': 'COVERED', 'lining': 'SEALED',
        'inlet': port(inlet, inlet_crest, .2), 'drain': port(receiver, drain_crest, .03),
        'overflow': port(receiver, overflow_crest, .12)}]}


def with_receiver(model):
    value = deepcopy(model)
    text = value['network']['inputText']
    text = text.replace('[STORAGE]', '[STORAGE]\nRECEIVER 0 5 0 FUNCTIONAL 0 0 1 0 0')
    text = text.replace('DRAIN TANK OUT BOTTOM', 'DRAIN TANK RECEIVER BOTTOM')
    text = text.replace('[ORIFICES]', '[ORIFICES]\nTAIL RECEIVER OUT BOTTOM 0 0.65 NO 0')
    text = text.replace('[XSECTIONS]', '[XSECTIONS]\nTAIL CIRCULAR .2 0 0 0')
    value['network']['inputText'] = text
    return value


def case(lids=None, *, backwater=False, flap=False, route_ms=2):
    model = with_receiver(coupled_facility_case(lids))
    text = model['network']['inputText']
    model['network']['inputText'] = text.replace('ROUTING_STEP 0.01', f'ROUTING_STEP {route_ms/1000}').replace(
        'MINIMUM_STEP 0.01', 'MINIMUM_STEP 0.001').replace('MAX_TRIALS 40', 'MAX_TRIALS 200')
    if backwater:
        model['network']['inputText'] = model['network']['inputText'].replace(
            'OUT 0 FIXED 0 NO', 'OUT 0 FIXED 1.2 NO')
    raw = model['network']['inputText'].encode()
    model['connectedStorageDesign'] = design(raw, flap=flap)
    return model
