"""공개 2022 관측과 선행 7일 입력의 단계별 첨두·원 EPA 이진 대조."""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))
from waterleague_sim import shared_model
from waterleague_sim.engine import continuous, initialization, swmm
from waterleague_sim.historical_antecedent import load as load_antecedent
from waterleague_sim.historical_evaporation import load as load_evaporation
from waterleague_sim.model_catalog import read_catalog


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2) + '\n')


def run(root):
    if root.exists():
        raise ValueError('기존 근거 덮어쓰기 거부')
    root.mkdir(parents=True)
    district = '2410520'
    snapshot = shared_model.candidate_snapshot(district)
    model_hash, observed = next((key, json.loads(raw)) for key, raw in read_catalog(ROOT/'data/models').items()
        if json.loads(raw).get('mapId') == 'seoul-osm-v1-' + district
        and json.loads(raw).get('rainfall', {}).get('start', '').startswith('2022-08-08'))
    evaporation = load_evaporation(model_hash, observed, root/'sources')
    antecedent = load_antecedent(model_hash, root/'sources')
    cases = []
    for kind in ('BIORETENTION', 'GREEN_ROOF'):
        cell = next(c for c in snapshot['cells'] if kind in c['allowedTypes'])
        model, _, _ = shared_model.resolve({'district_id': district, 'cell_id': cell['id'],
            'model_hash': shared_model.site_catalog()[district]['sha256']})
        model['rainfall'] = observed['rainfall']
        model = shared_model.with_observed_forcing(model, evaporation)
        expanded, pet = initialization.prepend(model, evaporation, antecedent)
        placement = {'cellId': cell['id'], 'facilityType': kind, 'areaM2': 20}
        start = time.monotonic()
        result = continuous.experiment(expanded, placement, root/kind, pet)
        duration = time.monotonic() - start
        write(root/kind/'evaporation.json', pet)
        compared = []
        for name in ('baseline', 'strategy'):
            directory = root/kind
            lib = C.CDLL(str(swmm.library_path()))
            try:
                assert lib.swmm_open(os.fsencode(directory/f'{name}.inp'),
                    os.fsencode(directory/f'{name}-original.rpt'), os.fsencode(directory/f'{name}-original.out')) == 0
                assert lib.swmm_start(1) == 0
                elapsed = C.c_double()
                for _ in range(len(expanded['rainfall']['depthsMm']) * 60):
                    assert lib.swmm_step(C.byref(elapsed)) == 0
                assert lib.swmm_end() == 0
                assert lib.swmm_report() == 0
            finally:
                lib.swmm_close()
            assert (directory/f'{name}.out').read_bytes() == (directory/f'{name}-original.out').read_bytes()
            compared.append({'id': name, 'officialOutExact': True,
                'outSha256': hashlib.sha256((directory/f'{name}.out').read_bytes()).hexdigest()})
        cases.append({'facilityType': kind, 'cellId': cell['id'], 'elapsedSeconds': duration,
            'outComparison': compared, 'comparison': result['runoffComparison']})
        print(kind, '완료', round(duration, 3), flush=True)
    paths = [Path(__file__), ROOT/'simulation/waterleague_sim/engine/runoff_metrics.py',
        ROOT/'simulation/waterleague_sim/engine/continuous.py', ROOT/'simulation/waterleague_sim/engine/swmm.py',
        ROOT/'simulation/waterleague_sim/engine/initialization.py', ROOT/'simulation/waterleague_sim/engine/facilities.py']
    for source in paths:
        target = root/'source'/source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    for source in (continuous.library_path(), continuous.library_path().parent/'live-build.json', swmm.library_path()):
        folder = 'observed-engine' if source.parent == continuous.library_path().parent else 'official-engine'
        target = root/folder/source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    report = {'schemaVersion': 1, 'classification': 'OBSERVED_RAIN_SELECTED_SURFACES_NOT_FIELD_VALIDATION',
        'stationId': observed['rainfall']['stationId'], 'rainfallModelSha256': model_hash,
        'rainfallMm': sum(observed['rainfall']['depthsMm']), 'warmupDays': 7, 'cases': cases,
        'files': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(root.rglob('*')) if p.is_file()}}
    write(root/'manifest.json', report)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    run(args.output.resolve())
