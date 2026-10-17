"""고정된 EPA 교육 사례의 실행·단위·인쇄 참조 대조. 운영 모델 승격 없음."""
import ctypes as C
from decimal import Decimal
import hashlib
from io import BytesIO
import json
import math
import os
from pathlib import Path
import platform
import re
import struct
import subprocess
from urllib.request import Request, urlopen
from zipfile import ZipFile

from waterleague_sim.engine.swmm import ROOT, REVISION, library_path

MANIFEST = ROOT / 'data/benchmarks/epa-applications-example1.json'
CFS_TO_CMS = 0.3048 ** 3
ACRE_TO_M2 = 43560 * 0.3048 ** 2
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024


class ReferenceValidationError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise ReferenceValidationError(code)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_sources(cache, *, download=False):
    manifest = json.loads(MANIFEST.read_text())
    cache = Path(cache)
    require(not cache.is_symlink(), 'SOURCE_LINK_REJECTED')
    if not cache.exists():
        require(download, 'SOURCE_REQUIRED')
        request = Request(manifest['archiveUrl'], headers={'User-Agent': 'WaterLeague-reference-validation/1'})
        with urlopen(request, timeout=30) as response:
            require(response.url.startswith('https://www.epa.gov/'), 'SOURCE_REDIRECT_REJECTED')
            data = response.read(MAX_ARCHIVE_BYTES + 1)
        require(len(data) == manifest['archiveBytes'] and digest(data) == manifest['archiveSha256'], 'SOURCE_HASH_MISMATCH')
        cache.parent.mkdir(parents=True, exist_ok=True)
        with cache.open('xb') as target:
            target.write(data)
    require(cache.is_file() and cache.stat().st_size == manifest['archiveBytes'], 'SOURCE_SIZE_MISMATCH')
    data = cache.read_bytes()
    require(digest(data) == manifest['archiveSha256'], 'SOURCE_HASH_MISMATCH')
    with ZipFile(BytesIO(data)) as outer:
        nested = outer.read(manifest['nestedArchive']['member'])
        manual = outer.read(manifest['manual']['member'])
    require(digest(nested) == manifest['nestedArchive']['sha256'] and digest(manual) == manifest['manual']['sha256'], 'MEMBER_HASH_MISMATCH')
    with ZipFile(BytesIO(nested)) as archive:
        inputs = {name: archive.read(name) for name in manifest['inputs']}
    for name, value in inputs.items():
        expected = manifest['inputs'][name]
        require(len(value) == expected['bytes'] and digest(value) == expected['sha256'], 'INPUT_HASH_MISMATCH')
    return manifest, inputs


def transform_input(source, storm, *, metric=False, engine_area=False):
    require(not engine_area or metric, 'UNIT_TRANSFORM_INVALID')
    require(storm in ('2-yr', '10-yr', '100-yr'), 'STORM_UNSUPPORTED')
    manifest = json.loads(MANIFEST.read_text())
    require(digest(source) in {value['sha256'] for value in manifest['inputs'].values()}, 'INPUT_UNREGISTERED')
    section = ''
    lines = []
    gages = 0
    for line in source.decode('cp1252').splitlines():
        stripped = line.strip()
        if stripped.startswith('['):
            section = stripped.upper()
        elif stripped and not stripped.startswith(';'):
            values = stripped.split()
            changed = False
            if section == '[RAINGAGES]':
                require(values[:5] == ['RainGage', 'INTENSITY', '0:05', '1.0', 'TIMESERIES'], 'GAGE_UNSUPPORTED')
                values[5] = storm
                gages += 1
                changed = True
            if metric:
                conversions = {}
                if section == '[OPTIONS]' and values[0] == 'FLOW_UNITS':
                    require(values[1] == 'CFS', 'UNITS_UNSUPPORTED')
                    values[1] = 'CMS'
                    changed = True
                elif section == '[EVAPORATION]':
                    require(values[0] == 'CONSTANT', 'EVAPORATION_UNSUPPORTED')
                    conversions = {1: '25.4'}
                elif section == '[SUBCATCHMENTS]':
                    area_factor = str(Decimal('0.92903e-5') / Decimal('2.2956e-5')) if engine_area else '0.40468564224'
                    conversions = {3: area_factor, 5: '0.3048', 7: '0.3048'}
                elif section == '[SUBAREAS]':
                    conversions = {3: '25.4', 4: '25.4'}
                elif section == '[INFILTRATION]':
                    conversions = {1: '25.4', 2: '25.4', 5: '25.4'}
                elif section == '[OUTFALLS]':
                    conversions = {1: '0.3048'}
                elif section == '[TIMESERIES]':
                    require(len(values) == 3 and values[0] in ('2-yr', '10-yr', '100-yr'), 'TIMESERIES_UNSUPPORTED')
                    conversions = {2: '25.4'}
                for index, factor in conversions.items():
                    values[index] = format(Decimal(values[index]) * Decimal(factor), 'f')
                    changed = True
            if changed:
                line = ' '.join(values)
        lines.append(line)
    require(gages == 1, 'GAGE_COUNT_MISMATCH')
    return '\n'.join(lines) + '\n'


def report_depths(report, units):
    require(report.count('Runoff Quantity Continuity') == 1, 'REPORT_SECTION_MISSING')
    part = report.split('Runoff Quantity Continuity', 1)[1].split('Continuity Error (%)', 1)[0]
    require(('inches' if units == 'CFS' else 'mm') in part, 'REPORT_UNITS_MISMATCH')
    fields = {'precipitationIn': 'Total Precipitation', 'runoffIn': 'Surface Runoff', 'infiltrationIn': 'Infiltration Loss'}
    values = {}
    for key, label in fields.items():
        matches = re.findall(r'^\s*' + re.escape(label) + r'\s*\.+\s+([-\d.]+)\s+([-\d.]+)\s*$', part, re.M)
        require(len(matches) == 1, 'REPORT_FIELD_MISSING')
        number = float(matches[0][1])
        require(math.isfinite(number) and number >= 0, 'REPORT_VALUE_INVALID')
        values[key] = number if units == 'CFS' else number / 25.4
    return values


def execute_case(inp, directory, units):
    require(units in ('CFS', 'CMS'), 'UNITS_UNSUPPORTED')
    # 고정 엔진의 상대경로 변환 버퍼와 파일명 한도를 호출 전에 처리한다.
    directory = Path(directory).resolve()
    require(all(len(os.fsencode(directory/name)) <= 259 for name in ('input.inp', 'api.rpt', 'api.out', 'cli.rpt', 'cli.out')), 'ENGINE_PATH_TOO_LONG')
    directory.mkdir()
    path = directory / 'input.inp'
    path.write_text(inp)
    rpt, out = directory / 'api.rpt', directory / 'api.out'
    libpath = library_path().resolve()
    lib = C.CDLL(str(libpath))
    lib.swmm_open.argtypes = [C.c_char_p, C.c_char_p, C.c_char_p]
    lib.swmm_getValue.argtypes = [C.c_int, C.c_int]
    lib.swmm_getValue.restype = C.c_double
    lib.swmm_getSavedValue.argtypes = [C.c_int, C.c_int, C.c_int]
    lib.swmm_getSavedValue.restype = C.c_double
    lib.swmm_getIndex.argtypes = [C.c_int, C.c_char_p]
    lib.swmm_step.argtypes = [C.POINTER(C.c_double)]
    lib.swmm_getMassBalErr.argtypes = [C.POINTER(C.c_float)] * 3
    require(lib.swmm_getVersion() == 52004, 'ENGINE_VERSION_MISMATCH')

    def check(code):
        require(code == 0, 'ENGINE_ERROR_' + str(code))

    try:
        check(lib.swmm_open(os.fsencode(path), os.fsencode(rpt), os.fsencode(out)))
        require(lib.swmm_getValue(8, 0) == (0 if units == 'CFS' else 3), 'ENGINE_UNITS_MISMATCH')
        count = lib.swmm_getCount(1)
        require(count in (1, 7), 'SUBCATCHMENT_COUNT_MISMATCH')
        area = sum(lib.swmm_getValue(200, i) for i in range(count)) * (ACRE_TO_M2 if units == 'CFS' else 10000)
        check(lib.swmm_start(1))
        elapsed = C.c_double()
        for _ in range(100000):
            check(lib.swmm_step(C.byref(elapsed)))
            if elapsed.value == 0:
                break
        else:
            raise ReferenceValidationError('STEP_LIMIT_EXCEEDED')
        check(lib.swmm_end())
        check(lib.swmm_report())
        errors = [C.c_float() for _ in range(3)]
        check(lib.swmm_getMassBalErr(*(C.byref(value) for value in errors)))
        series = [sum(lib.swmm_getSavedValue(205, i, period) for i in range(count)) * (CFS_TO_CMS if units == 'CFS' else 1) for period in range(1, 721)]
        require(all(math.isfinite(value) and value >= 0 for value in series), 'SERIES_VALUE_INVALID')
        outlet = lib.swmm_getIndex(2, b'O1')
        require(outlet >= 0, 'OUTLET_MISSING')
        outlet_series = [lib.swmm_getSavedValue(307, outlet, period) * (CFS_TO_CMS if units == 'CFS' else 1) for period in range(1, 721)]
        require(all(math.isfinite(value) and value >= 0 for value in outlet_series), 'OUTLET_VALUE_INVALID')
        outlet_mismatches = [{'period': i, 'subcatchmentSumM3s': total, 'outletInflowM3s': value} for i, (value, total) in enumerate(zip(outlet_series, series), 1) if not math.isclose(value, total, rel_tol=1e-6, abs_tol=1e-8)]
        if outlet_mismatches:
            (directory/'outlet-mismatch.json').write_text(json.dumps(outlet_mismatches, allow_nan=False, indent=2)+'\n')
        require(lib.swmm_getWarnings() == 0 and abs(errors[0].value) <= 1, 'NUMERICAL_QUALITY_FAILED')
    finally:
        lib.swmm_close()
    raw = out.read_bytes()
    require(len(raw) >= 24, 'OUTPUT_TRUNCATED')
    footer = struct.unpack('<6i', raw[-24:])
    require(footer[3] == 720 and footer[4] == 0 and footer[5] == 516114522, 'OUTPUT_PERIOD_MISMATCH')
    depths = report_depths(rpt.read_text(), units)
    cli = libpath.parent / 'runswmm'
    require(cli.is_file(), 'CLI_REQUIRED')
    subprocess.run([str(cli), str(path.resolve()), str((directory/'cli.rpt').resolve()), str((directory/'cli.out').resolve())], check=True, capture_output=True, timeout=60)
    require(out.read_bytes() == (directory/'cli.out').read_bytes(), 'API_CLI_BINARY_MISMATCH')
    require(depths == report_depths((directory/'cli.rpt').read_text(), units), 'API_CLI_REPORT_MISMATCH')
    result = {
        'units': units, 'areaM2': area, 'depthsIn': depths,
        'runoffM3': depths['runoffIn'] * 25.4 * area / 1000,
        'infiltrationM3': depths['infiltrationIn'] * 25.4 * area / 1000,
        'peakM3s': max(series), 'seriesM3s': series,
        'runoffContinuityPercent': errors[0].value,
        'reportCount': 720, 'reportIntervalSeconds': 60,
        'apiCliBinaryEqual': True, 'apiCliReportEqual': True,
        'outletComparison': {
            'status': 'DIFFERENT_SERIES' if outlet_mismatches else 'WITHIN_PRECISION',
            'differingPeriods': len(outlet_mismatches),
            'relativeTolerance': 1e-6, 'absoluteToleranceM3s': 1e-8,
            'maxDifferenceM3s': max(abs(a-b) for a,b in zip(series, outlet_series)),
            'outletPeakM3s': max(outlet_series),
            'subcatchmentPeakPeriod': series.index(max(series))+1,
            'outletPeakPeriod': outlet_series.index(max(outlet_series))+1,
        },
        'outletSeriesM3s': outlet_series,
    }
    (directory/'metrics.json').write_text(json.dumps(result, allow_nan=False, indent=2) + '\n')
    result['files'] = {p.name: digest(p.read_bytes()) for p in sorted(directory.iterdir())}
    return result


def compare_units(us, si, *, diagnostic=False):
    require(us['reportCount'] == si['reportCount'] == 720, 'SERIES_LENGTH_MISMATCH')
    require(len(us['seriesM3s']) == len(si['seriesM3s']) == 720, 'SERIES_LENGTH_MISMATCH')
    area = us['areaM2']
    require(math.isclose(area, si['areaM2'], rel_tol=0.0002), 'AREA_UNIT_MISMATCH')
    mismatches = []
    for period, (left, right) in enumerate(zip(us['seriesM3s'], si['seriesM3s']), 1):
        require(math.isfinite(left) and math.isfinite(right), 'FLOW_VALUE_INVALID')
        if not math.isclose(left, right, rel_tol=0.0002, abs_tol=1e-7):
            mismatches.append({'period': period, 'cfsAsM3s': left, 'cmsM3s': right, 'differenceM3s': right-left})
    require(diagnostic or not mismatches, 'FLOW_UNIT_MISMATCH')
    # 양쪽 보고서의 깊이 반올림 폭을 체적으로 환산한다.
    volume_tolerance = (0.0005 * 25.4 + 0.0005) * area / 1000
    for key in ('runoffM3', 'infiltrationM3'):
        require(math.isclose(us[key], si[key], rel_tol=0.0002, abs_tol=volume_tolerance), 'VOLUME_UNIT_MISMATCH')
    return {'status': 'REVIEW_REQUIRED' if mismatches else 'PASS', 'flowMismatches': mismatches,
            'flowRelativeTolerance': 0.0002, 'flowAbsoluteToleranceM3s': 1e-7, 'reportRoundingToleranceM3': volume_tolerance,
            'maxFlowAbsoluteDifferenceM3s': max(abs(a-b) for a,b in zip(us['seriesM3s'], si['seriesM3s']))}


def compare_published(case, result):
    actual = result['depthsIn'] | {'peakCfs': result['outletComparison']['outletPeakM3s'] / CFS_TO_CMS}
    comparisons = []
    for field, printed in case['published'].items():
        number = Decimal(printed)
        print_half_unit = Decimal(10) ** number.as_tuple().exponent / 2
        report_half_unit = Decimal('0.0005') if field != 'peakCfs' else Decimal(0)
        tolerance = float(print_half_unit + report_half_unit)
        difference = actual[field] - float(number)
        require(math.isfinite(actual[field]) and math.isfinite(difference), 'REFERENCE_VALUE_INVALID')
        conflict = case.get('sourceConflicts', {}).get(field)
        status = 'SOURCE_CONFLICT' if conflict else 'WITHIN_PRINT_PRECISION' if abs(difference) <= tolerance + 1e-12 else 'REFERENCE_DIFFERENCE'
        comparisons.append({'field': field, 'quantity': 'O1_NODE_TOTAL_INFLOW_PEAK' if field == 'peakCfs' else 'RUNOFF_CONTINUITY_DEPTH', 'printed': printed, 'actual': actual[field], 'difference': difference,
                            'absoluteTolerance': tolerance, 'status': status, 'conflictingSource': conflict})
    return comparisons


def summarize_reference(report):
    summary = {key: report[key] for key in ('schemaVersion', 'kind', 'official', 'modelPromotionAllowed', 'executionStatus', 'internationalUnitStatus', 'engineUnitStatus', 'referenceStatus', 'summary', 'engine', 'provenance', 'limitations')}
    summary['cases'] = []
    for case in report['cases']:
        summary['cases'].append({
            'id': case['id'], 'manualPage': case['manualPage'], 'manualTable': case['manualTable'],
            'cfs': {key: case['cfs'][key] for key in ('areaM2', 'depthsIn', 'runoffM3', 'infiltrationM3', 'peakM3s', 'runoffContinuityPercent', 'reportCount', 'apiCliBinaryEqual', 'outletComparison')},
            'internationalUnitCheck': case['internationalUnitCheck'], 'engineUnitCheck': case['engineUnitCheck'],
            'publishedComparison': case['publishedComparison'],
        })
    return summary


def validate_reference(cache, output, *, download=False):
    manifest, sources = read_sources(cache, download=download)
    output = Path(output)
    require(not output.exists() and not output.is_symlink(), 'OUTPUT_EXISTS')
    output.mkdir(parents=True)
    cases = []
    for case in manifest['cases']:
        source = sources[case['input']]
        us = execute_case(transform_input(source, case['storm']), output/(case['id']+'-cfs'), 'CFS')
        si = execute_case(transform_input(source, case['storm'], metric=True), output/(case['id']+'-cms'), 'CMS')
        unit_check = compare_units(us, si, diagnostic=True)
        engine_si = execute_case(transform_input(source, case['storm'], metric=True, engine_area=True), output/(case['id']+'-cms-engine-area'), 'CMS')
        engine_unit_check = compare_units(us, engine_si)
        comparisons = compare_published(case, us)
        cases.append({'id': case['id'], 'manualPage': case['manualPage'], 'manualTable': case['manualTable'],
                      'cfs': us, 'cms': si, 'cmsEngineArea': engine_si,
                      'internationalUnitCheck': unit_check, 'engineUnitCheck': engine_unit_check, 'publishedComparison': comparisons})
    all_checks = [item for case in cases for item in case['publishedComparison']]
    report = {
        'schemaVersion': 1, 'kind': manifest['kind'], 'official': False, 'modelPromotionAllowed': False,
        'executionStatus': 'PASS',
        'internationalUnitStatus': 'REVIEW_REQUIRED' if any(c['internationalUnitCheck']['status'] != 'PASS' for c in cases) else 'PASS',
        'engineUnitStatus': 'PASS',
        'referenceStatus': 'REVIEW_REQUIRED' if any(c['status'] != 'WITHIN_PRINT_PRECISION' for c in all_checks) else 'WITHIN_PRINT_PRECISION',
        'summary': {status: sum(c['status'] == status for c in all_checks) for status in ['WITHIN_PRINT_PRECISION', 'REFERENCE_DIFFERENCE', 'SOURCE_CONFLICT']},
        'engine': {'version': '5.2.4', 'revision': REVISION, 'binarySha256': digest(library_path().read_bytes()), 'cliSha256': digest((library_path().resolve().parent/'runswmm').read_bytes()), 'platform': platform.platform()},
        'provenance': {'sourceUrl': manifest['archiveUrl'], 'sourceSha256': manifest['archiveSha256'], 'contractSha256': digest(MANIFEST.read_bytes()), 'verificationCodeSha256': digest(Path(__file__).read_bytes())},
        'limitations': manifest['limitations'], 'cases': cases,
    }
    (output/'report.json').write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2)+'\n')
    (output/'summary.json').write_text(json.dumps(summarize_reference(report), ensure_ascii=False, allow_nan=False, indent=2)+'\n')
    return report
