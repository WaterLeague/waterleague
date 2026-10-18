"""서울 전역 후보의 과거 관측 강우 비교. 원자료·선택 표면·수치 결과 보존."""
import json
import os
import resource
import sys
from pathlib import Path

from .engine.continuous import ROOT, digest, experiment
from .model_catalog import read_catalog
from .shared_model import resolve, with_observed_forcing
from .historical_evaporation import load as load_evaporation


def calculate(request, directory):
    models = read_catalog(ROOT/'data/models')
    source = models[request['modelHash']]
    observed = json.loads(source)
    placements = json.loads(request['placements'])
    if (digest((request['modelHash']+'\n'+request['placements']).encode()) != request['inputHash']
            or not 1 <= len(placements) <= 50):
        raise ValueError('HISTORICAL_INPUT_INVALID')
    selected = [p for p in placements if 'initializationSensitivity' in p]
    if (len(selected) > 1 or any(p['initializationSensitivity'] not in
            ('SELECTED_SURFACE_7_DAY_DRY_WET_V1', 'SELECTED_SWALE_7_DAY_STATE_V2') for p in selected)
            or any((p['initializationSensitivity'] == 'SELECTED_SWALE_7_DAY_STATE_V2')
                   != (p['facilityType'] == 'VEGETATIVE_SWALE') for p in selected)):
        raise ValueError('HISTORICAL_SENSITIVITY_INVALID')
    directory.mkdir(parents=True, exist_ok=True)
    from .admission import archive
    archive(placements[0].get('publicAssetPolicy'), directory)
    (directory/'rainfall-model.json').write_bytes(source)
    evaporation = load_evaporation(request['modelHash'], observed, directory)
    results, frames = [], []
    antecedent = None
    sensitivity_input = None
    assumptions = {'관망 없는 독립 표면 계산', '관측소 강우의 선택 표면 대표성 미검증'}
    for index, placement in enumerate(placements):
        model, _, _ = resolve({'district_id': placement['districtId'], 'cell_id': placement['cellId'],
                               'model_hash': placement['siteModelHash'],
                               'budget_policy': placement.get('budgetPolicy')})
        if observed['mapId'] != 'seoul-osm-v1-'+placement['districtId']:
            raise ValueError('HISTORICAL_DISTRICT_INVALID')
        model['rainfall'] = observed['rainfall']
        model = with_observed_forcing(model, evaporation)
        if placement in selected:
            if model.get('initializationPolicy') is None or model.get('facilityDesignSet') is None:
                raise ValueError('HISTORICAL_SENSITIVITY_UNAVAILABLE')
            sensitivity_input = model
        applied_evaporation = evaporation
        if model.get('initializationPolicy') is not None:
            from .historical_antecedent import load as load_antecedent
            from .engine.initialization import prepend
            if antecedent is None:
                antecedent = load_antecedent(request['modelHash'], directory)
            model, applied_evaporation = prepend(model, evaporation, antecedent)
        physical = {k: placement[k] for k in ('cellId','facilityType','areaM2')}
        from .costing.snapshot import archive as archive_cost
        cost_record = archive_cost(placement, model, physical, directory/str(index))
        result = experiment(model, physical, directory/str(index), applied_evaporation)
        assumptions.update(result['assumptions'])
        a, b = result['baseline']['final'], result['strategy']['final']
        results.append({k: v for k,v in placement.items() if k != 'costSnapshotRaw'} | {
            'costRecord': cost_record, 'precipitationM3': b['precipitationM3'],
            'infiltrationM3': b['infiltrationM3'], 'storageM3': b['storageM3'],
            'evaporationM3': b['evaporationM3'],
            'baselineAccountedM3': a['accountedDischargeM3'], 'designAccountedM3': b['accountedDischargeM3'],
            'differenceM3': a['accountedDischargeM3']-b['accountedDischargeM3'],
            'runoffContinuityPercent': result['strategy']['runoffContinuityPercent'],
            'physicalInputs': model['cells'][0].get('physicalInputs'),
            'facilityDesign': result.get('facilityDesign'), 'initialization': result.get('initialization')})
        results[-1]['runoffComparison'] = result['runoffComparison']
        for i, (base, design, contribution) in enumerate(zip(result['baseline']['samples'], result['strategy']['samples'], result['contribution'], strict=True)):
            if index == 0:
                frames.append({'at': base['at'], 'rainMm': observed['rainfall']['depthsMm'][i],
                               'baselineM3s': 0., 'designM3s': 0., 'differenceM3': 0.})
            frames[i]['baselineM3s'] += base['runoffM3s']
            frames[i]['designM3s'] += design['runoffM3s']
            frames[i]['differenceM3'] += contribution['cumulativeM3']
    output = {'schemaVersion': 1, 'validationLevel': 'EXPLORATORY', 'engineVersion': '5.2.4',
            'disasterEvent': observed.get('disasterEvent'),
            'evaporationMethod': evaporation['method'], 'evaporationSourceHashes': evaporation['sourceHashes'],
            'scope': 'SELECTED_INDEPENDENT_SURFACES_ONLY', 'rainfallSourceHash': observed['rainfall']['sourceHash'],
            'stationName': observed['rainfall']['stationName'], 'start': observed['rainfall']['start'],
            'end': observed['rainfall']['end'], 'facilities': results, 'frames': frames,
            'differenceM3': sum(v['differenceM3'] for v in results),
            'baselineAccountedM3': sum(v['baselineAccountedM3'] for v in results),
            'designAccountedM3': sum(v['designAccountedM3'] for v in results),
            'assumptions': sorted(assumptions)+evaporation['assumptions']}
    if selected:
        from .engine.initialization_sensitivity import analyze
        physical = {k: selected[0][k] for k in ('cellId', 'facilityType', 'areaM2')}
        version = 2 if selected[0]['initializationSensitivity'] == 'SELECTED_SWALE_7_DAY_STATE_V2' else 1
        report = analyze(sensitivity_input, physical, evaporation, antecedent, directory/'sensitivity',
                         days=(7,), schema_version=version)
        output['initializationSensitivity'] = report
    return output


def main():
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CPU, (75,75))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64*1024*1024,64*1024*1024))
    if sys.platform.startswith('linux'):
        resource.setrlimit(resource.RLIMIT_AS, (1536*1024*1024,1536*1024*1024))
    root = Path(sys.argv[1])
    result = calculate(json.loads((root/'request.json').read_text()), root)
    (root/'result.json').write_text(json.dumps(result, ensure_ascii=False, allow_nan=False)+'\n')
    (root/'historical.py').write_bytes(Path(__file__).read_bytes())
    (root/'manifest.json').write_text(json.dumps({str(p.relative_to(root)): digest(p.read_bytes())
        for p in sorted(root.rglob('*')) if p.is_file() and p != root/'manifest.json'}, indent=2)+'\n')


if __name__ == '__main__':
    main()
