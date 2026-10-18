"""보관 펌프 비교 묶음의 입력·바이너리·내부 운전 원장 재생."""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import platform

FIELDS = ('transferredM3', 'runningSeconds', 'flowingSeconds', 'startCount', 'peakFlowM3s',
    'minimumOperatingHeadM', 'maximumOperatingHeadM', 'outsideHeadCurveSeconds',
    'outsideFlowCurveSeconds', 'inRangeShaftEnergyKwh', 'maximumRequiredNpshM',
    'observedSeconds', 'routingSteps')


def replay(bundle, destination):
    bundle, destination = Path(bundle).resolve(), Path(destination).resolve()
    result = json.loads((bundle/'result.json').read_text())
    expected = result['artifactFiles']
    if result['platform'] != platform.platform(): raise ValueError('PUMP_REPLAY_PLATFORM_MISMATCH')
    for name, sha in expected.items():
        path = bundle/name
        if not path.is_relative_to(bundle) or path.resolve() != path or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            raise ValueError('PUMP_REPLAY_SOURCE_CHANGED')
    destination.mkdir(parents=True, exist_ok=False)
    rows = []
    for case in result['cases']:
        name = case['id']
        if name not in ('baseline', 'strategy'): raise ValueError('PUMP_REPLAY_CASE_INVALID')
        target = destination/name; target.mkdir()
        source = target/'network.inp'; source.write_bytes((bundle/name/'network.inp').read_bytes())
        paths = [target/('network.'+ext) for ext in ('inp', 'rpt', 'out')]
        if any(len(os.fsencode(p)) > 259 for p in paths): raise ValueError('PUMP_REPLAY_PATH_TOO_LONG')
        lib = C.CDLL(str(bundle/(name+'-engine.bin')))
        lib.swmm_open.argtypes = [C.c_char_p]*3
        lib.swmm_getIndex.argtypes = [C.c_int, C.c_char_p]
        lib.wl_networkAdvance.argtypes = [C.c_int, C.POINTER(C.c_double)]
        lib.wl_metricsBegin.argtypes = [C.c_double, C.c_double, C.POINTER(C.c_int), C.c_int]
        lib.wl_metricsRead.argtypes = [C.c_int, C.POINTER(C.c_double), C.c_int]
        def check(code):
            if code != 0: raise ValueError('PUMP_REPLAY_ENGINE_FAILED')
        pumps = case.get('pumpOperation', {}).get('pumps', [])
        opened = False
        try:
            opened = True
            check(lib.swmm_open(*(os.fsencode(p) for p in paths)))
            check(lib.swmm_start(1)); check(lib.wl_networkBegin())
            metrics = case['evaluationMetrics']; spec = metrics['specification']; ids = spec['networkOutfalls']
            indexes = (C.c_int*len(ids))(*(lib.swmm_getIndex(2, n.encode()) for n in ids))
            check(lib.wl_metricsBegin(spec['startMilliseconds']/1000, spec['endMilliseconds']/1000, indexes, len(ids)))
            curve_ids, section = [], ''
            for line in source.read_text().splitlines():
                tokens = line.split(';', 1)[0].strip().upper().split()
                if not tokens: continue
                if tokens[0].startswith('['): section = tokens[0]
                elif section == '[CURVES]' and tokens[0] not in curve_ids: curve_ids.append(tokens[0])
            if pumps:
                lib.wl_pumpsBegin.argtypes = [C.c_int, C.c_int, C.c_int]
                lib.wl_pumpsRead.argtypes = [C.c_int, C.POINTER(C.c_double), C.c_int]
                for p in pumps:
                    key = p['linkId'].upper()
                    check(lib.wl_pumpsBegin(lib.swmm_getIndex(3, key.encode()), curve_ids.index(key+'_P'), curve_ids.index(key+'_N')))
            elapsed = C.c_double()
            for _ in range(20_000_000):
                check(lib.wl_networkAdvance(0, C.byref(elapsed)))
                if elapsed.value == 0: break
            else: raise ValueError('PUMP_REPLAY_STEP_LIMIT')
            pump_equal = True
            for p in pumps:
                values = (C.c_double*len(FIELDS))()
                check(lib.wl_pumpsRead(lib.swmm_getIndex(3, p['linkId'].encode()), values, len(values)))
                pump_equal &= all(p[k] == v for k, v in zip(FIELDS, values))
            metric_keys = ('outwardVolumeM3', 'inwardVolumeM3', 'peakOutwardM3s', 'peakInwardM3s',
                'peakOutwardTimeSeconds', 'peakInwardTimeSeconds', 'coveredSeconds', 'nativeSteps')
            actual = []
            for i in range(len(ids)+1):
                values = (C.c_double*8)(); check(lib.wl_metricsRead(i, values, 8))
                actual.append(dict(zip(metric_keys, values)))
            metrics_equal = dict(zip(ids, actual[:-1])) == metrics['outfalls'] and actual[-1] == metrics['combined']
            check(lib.swmm_end()); check(lib.swmm_report())
        finally:
            if opened:
                if pumps: lib.wl_pumpsRelease()
                lib.wl_metricsRelease(); lib.wl_networkRelease(); lib.swmm_close()
        sha = hashlib.sha256(paths[2].read_bytes()).hexdigest()
        rows.append({'id': name, 'outSha256': sha, 'binaryEqual': sha == expected[name+'/network.out'],
                     'pumpLedgerEqual': pump_equal, 'outfallMetricsEqual': metrics_equal})
    (destination/'replay.json').write_text(json.dumps(rows, indent=2)+'\n')
    if not all(r['binaryEqual'] and r['pumpLedgerEqual'] and r['outfallMetricsEqual'] for r in rows):
        raise ValueError('PUMP_REPLAY_DIFFERENT')
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(replay(Path(__file__).parent, args.output)))
