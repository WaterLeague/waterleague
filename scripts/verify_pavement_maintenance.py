"""실제 원형 후보·보관 관측으로 문헌 막힘 조건의 재생·물수지 대조."""
import argparse
from contextlib import closing
import copy
import hashlib
import json
from pathlib import Path

from waterleague_sim.engine import pavement_maintenance as study
from waterleague_sim.engine.continuous import digest, input_source
from waterleague_sim.forcing.game_climate import load as load_climate
from waterleague_sim.installation_model import with_observed_forcing
from waterleague_sim.spatial.game_catalog import regions, forcing
from waterleague_sim.spatial.play_bundle import open_catalog


def verify(output, district, event):
    if output.exists():
        raise ValueError('PAVEMENT_VERIFICATION_OUTPUT_EXISTS')
    region = regions()[district]
    model_hash = region['eventModelHashes'][event] if event else region['defaultModelHash']
    source = forcing(model_hash)
    observed = json.loads(source)
    reader = open_catalog()
    with closing(reader.connection()) as database:
        row = database.execute('''SELECT id FROM sites WHERE district_id=? AND allowed_mask & 2 <> 0
            AND json_extract(body,'$.areaM2') BETWEEN 25 AND 1000 ORDER BY fid LIMIT 1''',
            (district,)).fetchone()
    if row is None:
        raise ValueError('PAVEMENT_VERIFICATION_SITE_UNAVAILABLE')
    model = reader.model(row[0], district=district)
    model['rainfall'] = observed['rainfall']
    output.mkdir(parents=True, mode=0o700)
    evaporation, antecedent = load_climate(model_hash, observed, output)
    model = with_observed_forcing(model, evaporation)
    placement = {
        'cellId': row[0], 'facilityType': 'PERMEABLE_PAVEMENT',
        'areaM2': model['cells'][0]['maxAreaM2'],
    }
    unchanged = copy.deepcopy((model, placement, evaporation, antecedent))
    ordinary_input = input_source(model, [placement], evaporation)
    reports = [study.analyze(model, placement, evaporation, antecedent, output/name)
               for name in ('first', 'repeat')]
    if any(r['status'] != 'SUCCEEDED' or r['rankingEligible']
           or r['cleaningRecovery']['status'] != 'UNAVAILABLE'
           or r['cleaningRecovery']['value'] is not None for r in reports):
        raise ValueError('PAVEMENT_VERIFICATION_INCOMPLETE')
    if reports[0] != reports[1] or unchanged != (model, placement, evaporation, antecedent):
        raise ValueError('PAVEMENT_VERIFICATION_REPLAY_CHANGED')
    if input_source(model, [placement], evaporation) != ordinary_input:
        raise ValueError('PAVEMENT_VERIFICATION_DEFAULT_CHANGED')
    ids = [v['id'] for v in study.catalog()['cases']]
    hashes = {}
    for identifier in ['baseline', *ids]:
        for suffix in ('.inp', '.out'):
            name = identifier+suffix
            first = (output/'first'/name).read_bytes()
            repeat = (output/'repeat'/name).read_bytes()
            if first != repeat:
                raise ValueError('PAVEMENT_VERIFICATION_NATIVE_REPLAY_CHANGED')
            hashes[name] = digest(first)
    fresh = (output/'first/FRESH.inp').read_text().splitlines()
    for identifier in ids[1:]:
        other = (output/'first'/(identifier+'.inp')).read_text().splitlines()
        differences = [(a, b) for a, b in zip(fresh, other, strict=True) if a != b]
        if len(differences) != 1 or any(not s.startswith('PP PAVEMENT ') for s in differences[0]):
            raise ValueError('PAVEMENT_VERIFICATION_COMMON_CONDITIONS_CHANGED')
    report = {
        'schemaVersion': 1, 'status': 'PASS', 'districtId': district, 'eventId': event,
        'candidateId': row[0], 'geometrySha256': model['cells'][0]['geometrySha256'],
        'rainfallModelSha256': model_hash, 'catalogSha256': study.CATALOG_SHA256,
        'sourcePolicySha256': reports[0]['sourcePolicySha256'],
        'sourcePdfSha256': study.catalog()['source']['sha256'],
        'verifierSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'nativeFiles': hashes, 'resultSha256': digest(study.encode(reports[0])),
        'cases': [{'id': c['scenario']['id'], 'metrics': c['metrics'],
                   'runoffContinuityPercent': c['runoffContinuityPercent'],
                   'evaluationBalanceResidualM3': c['evaluationBalanceResidualM3']}
                  for c in reports[0]['cases']],
        'nativeReplayByteIdentical': True, 'commonConditionsPreserved': True,
        'ordinaryDesignInputUnchanged': True, 'fieldValidated': False,
        'rankingEligible': False, 'serviceIntegrated': False,
    }
    (output/'summary.json').write_bytes(study.encode(report))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--district', choices=sorted(regions()), default='11200')
    parser.add_argument('--event', choices=('seoul-20100921', 'seoul-20110727', 'seoul-20220808'),
                        default='seoul-20220808')
    args = parser.parse_args()
    result = verify(args.output, args.district, args.event)
    print(json.dumps({
        'status': result['status'], 'candidateId': result['candidateId'],
        'cases': len(result['cases']), 'serviceIntegrated': result['serviceIntegrated'],
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
