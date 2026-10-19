"""지표·지하 저류와 LID의 동시 연결 수치 사례. 서울 현장 설계가 아님."""
from copy import deepcopy

from waterleague_sim.evaluation.values import digest
from waterleague_sim.reference.connected_storage import design, with_receiver
from waterleague_sim.reference.surface_basin import case as basin_case, initialized_case


def case(*, basin=True, storage=True, exchange_ms=100):
    model = with_receiver(basin_case(route_ms=1, exchange_ms=exchange_ms))
    pond = model.pop('surfaceBasinDesign')
    if storage:
        model['connectedStorageDesign'] = design(model['network']['inputText'].encode())
    if basin:
        pond['sourceModelSha256'] = digest(model)
        model['surfaceBasinDesign'] = pond
    return model


def initialized(lids, *, route_step=.25):
    model = with_receiver(initialized_case())
    pond = model.pop('surfaceBasinDesign')
    model['network']['inputText'] = model['network']['inputText'].replace(
        'RECEIVER 0 5 0 FUNCTIONAL 0 0 1 0 0', 'RECEIVER 0 5 0 FUNCTIONAL 0 0 1000 0 0')
    model['network']['inputText'] = model['network']['inputText'].replace(
        'ROUTING_STEP 1\n', f'ROUTING_STEP {route_step}\n').replace(
        'MINIMUM_STEP 1\n', f'MINIMUM_STEP {min(route_step, 1)}\n')
    model['connectedFacilityDesign'] = deepcopy(lids)
    model['connectedStorageDesign'] = design(model['network']['inputText'].encode(), area=400)
    pond['sourceModelSha256'] = digest(model)
    model['surfaceBasinDesign'] = pond
    return model
