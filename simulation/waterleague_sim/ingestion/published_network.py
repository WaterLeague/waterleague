"""공개 연구 INP의 출처·연결·미확인 입력을 보존하는 가져오기."""
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import shlex
import stat
from zipfile import ZipFile

from waterleague_sim.engine.flood_errors import require

MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_INPUT_BYTES = 2_000_000
_EXEC_SECTIONS = frozenset(('TITLE', 'OPTIONS', 'EVAPORATION', 'RAINGAGES',
    'SUBCATCHMENTS', 'SUBAREAS', 'INFILTRATION', 'LID_CONTROLS', 'LID_USAGE',
    'JUNCTIONS', 'OUTFALLS', 'CONDUITS', 'XSECTIONS', 'INFLOWS', 'TIMESERIES',
    'PATTERNS', 'REPORT', 'MAP', 'COORDINATES', 'POLYGONS', 'SYMBOLS', 'PROFILES', 'TAGS', 'VERTICES'))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _read(path, limit, expected=None):
    path = Path(path).absolute()
    require(path.resolve() == path and not path.is_symlink() and path.is_file(),
            'PUBLISHED_SOURCE_PATH_INVALID')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit and (expected is None or digest(raw) == expected),
            'PUBLISHED_SOURCE_HASH_OR_SIZE_INVALID')
    return raw


def records(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_INPUT_BYTES, 'PUBLISHED_INPUT_SIZE_INVALID')
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        require(False, 'PUBLISHED_INPUT_ENCODING_UNSUPPORTED')
    require('\0' not in text, 'PUBLISHED_INPUT_NUL')
    section, result = None, defaultdict(list)
    for number, line in enumerate(text.splitlines(), 1):
        lexer = shlex.shlex(line, posix=True)
        lexer.whitespace_split, lexer.commenters, lexer.escape = True, ';', ''
        try:
            tokens = list(lexer)
        except ValueError:
            require(False, 'PUBLISHED_INPUT_QUOTE_INVALID')
        if not tokens:
            continue
        if re.fullmatch(r'\[[A-Za-z_]+\]', tokens[0]):
            require(len(tokens) == 1, 'PUBLISHED_SECTION_INVALID')
            section = tokens[0][1:-1].upper()
            result.setdefault(section, [])
        else:
            require(section is not None, 'PUBLISHED_SECTION_REQUIRED')
            result[section].append({'line': number, 'text': line, 'tokens': tokens})
    return text, dict(result)


def _indexed(rows):
    result = {}
    for row in rows:
        identifier = row['tokens'][0].upper()
        require(identifier not in result, 'PUBLISHED_IDENTIFIER_DUPLICATED')
        result[identifier] = row
    return result


def _number(value):
    try:
        number = float(value)
    except ValueError:
        require(False, 'PUBLISHED_NUMBER_INVALID')
    require(math.isfinite(number), 'PUBLISHED_NUMBER_NONFINITE')
    return number


def inspect_input(raw):
    _, sections = records(raw)
    nodes = _indexed(sections.get('JUNCTIONS', []) + sections.get('OUTFALLS', []))
    links = _indexed(sections.get('CONDUITS', []))
    catchments = _indexed(sections.get('SUBCATCHMENTS', []))
    coordinates = _indexed(sections.get('COORDINATES', []))
    shapes = _indexed(sections.get('XSECTIONS', []))
    options = {name: row['tokens'][1] for name, row in _indexed(sections.get('OPTIONS', [])).items()
               if len(row['tokens']) == 2}
    missing, nonfinite, external = [], [], []
    for section, rows in sections.items():
        for row in rows:
            for index, token in enumerate(row['tokens']):
                try:
                    invalid_number = not math.isfinite(float(token))
                except ValueError:
                    invalid_number = False
                if invalid_number:
                    nonfinite.append({'section': section, 'line': row['line'], 'tokenIndex': index, 'value': token})
            if section in ('FILES', 'TEMPERATURE', 'EVENTS') or (
                    section in ('RAINGAGES', 'TIMESERIES', 'EVAPORATION', 'REPORT')
                    and 'FILE' in [token.upper() for token in row['tokens']]):
                external.append({'section': section, 'line': row['line'], 'tokens': row['tokens']})
    network_nodes, network_links, areas = [], [], []
    outfalls = {r['tokens'][0].upper() for r in sections.get('OUTFALLS', [])}
    for name, row in nodes.items():
        tokens = row['tokens']
        require(len(tokens) >= 3, 'PUBLISHED_NODE_INVALID')
        coordinate = coordinates.get(name)
        if coordinate is None:
            missing.append({'kind': 'COORDINATE', 'id': name})
        network_nodes.append({'id': tokens[0], 'kind': 'OUTFALL' if name in outfalls else 'JUNCTION',
            'invertDeclared': _number(tokens[1]), 'parameters': tokens[2:],
            'coordinateDeclared': [_number(v) for v in coordinate['tokens'][1:]] if coordinate else None,
            'sourceLine': row['line']})
    for name, row in links.items():
        tokens = row['tokens']
        require(len(tokens) >= 5, 'PUBLISHED_CONDUIT_INVALID')
        for node in tokens[1:3]:
            if node.upper() not in nodes:
                missing.append({'kind': 'NODE', 'id': node, 'from': name})
        if name not in shapes:
            missing.append({'kind': 'XSECTION', 'id': name})
        network_links.append({'id': tokens[0], 'fromNode': tokens[1], 'toNode': tokens[2],
            'lengthDeclared': _number(tokens[3]), 'roughness': _number(tokens[4]),
            'parameters': tokens[5:], 'crossSection': shapes[name]['tokens'][1:] if name in shapes else None,
            'sourceLine': row['line']})
    for name, row in catchments.items():
        tokens = row['tokens']
        require(len(tokens) >= 8, 'PUBLISHED_CATCHMENT_INVALID')
        if tokens[2].upper() not in nodes and tokens[2].upper() not in catchments:
            missing.append({'kind': 'OUTLET', 'id': tokens[2], 'from': name})
        areas.append({'id': tokens[0], 'gage': tokens[1], 'outlet': tokens[2],
            'areaDeclared': _number(tokens[3]), 'imperviousPercent': _number(tokens[4]),
            'widthDeclared': _number(tokens[5]), 'slopePercent': _number(tokens[6]),
            'curbLengthRaw': tokens[7], 'sourceLine': row['line']})
    # 방향을 바꾸거나 끊긴 관망을 임의 방류구에 연결하지 않는다.
    upstream = defaultdict(set)
    for link in network_links:
        upstream[link['toNode'].upper()].add(link['fromNode'].upper())
    reached, pending = set(outfalls), list(outfalls)
    while pending:
        for node in upstream[pending.pop()] - reached:
            reached.add(node)
            pending.append(node)
    coordinate_values = [node['coordinateDeclared'] for node in network_nodes if node['coordinateDeclared']]
    bbox = ([min(v[0] for v in coordinate_values), min(v[1] for v in coordinate_values),
             max(v[0] for v in coordinate_values), max(v[1] for v in coordinate_values)]
            if coordinate_values and all(len(v) == 2 for v in coordinate_values) else None)
    return {'schemaVersion': 1, 'sourceSha256': digest(raw),
        'classification': 'PUBLISHED_RESEARCH_MODEL_NOT_OFFICIAL_ASSET_INVENTORY',
        'rankingEligible': False, 'fieldValidated': False,
        'horizontalCrs': None, 'verticalDatum': None, 'assetValidityPeriod': None,
        'coordinateBoundsDeclared': bbox, 'options': options,
        'counts': {section: len(rows) for section, rows in sections.items()},
        'areaHa': sum(row['areaDeclared'] for row in areas) if options.get('FLOW_UNITS') == 'CMS' else None,
        'nodes': network_nodes, 'conduits': network_links, 'catchments': areas,
        'topology': {'missingReferences': missing, 'nodesWithoutDirectedOutfallPath': sorted(set(nodes) - reached)},
        'nonfiniteTokens': nonfinite, 'externalFileReferences': external,
        'sourceRecords': sections,
        'limitations': ['좌표계·수직 기준·자산 유효 기간 미명시',
            '내장 강우·외부 유입 계보 미확인', '연구 입력의 균일 단면·조도·초기 상태와 추정값 보존',
            '원 관망의 월류 손실은 지표 침수 수심/확산 결과가 아님']}


def execution_input(raw):
    """물리값은 그대로 두고 연구 원본의 LID 상세 출력 파일만 비활성화."""
    text, sections = records(raw)
    audit = inspect_input(raw)
    require(set(sections) <= _EXEC_SECTIONS, 'PUBLISHED_EXECUTION_SECTION_UNSUPPORTED')
    require(audit['options'].get('FLOW_UNITS') == 'CMS'
            and audit['options'].get('FLOW_ROUTING') == 'DYNWAVE', 'PUBLISHED_EXECUTION_OPTIONS_UNSUPPORTED')
    require(not audit['topology']['missingReferences'] and not audit['externalFileReferences'],
            'PUBLISHED_EXECUTION_DEPENDENCY_UNRESOLVED')
    # 원본의 사용되지 않는 CurbLen NaN은 진단 실행에만 보존한다. 다른 비유한 입력은 거부한다.
    require(all(row['section'] == 'SUBCATCHMENTS' and row['tokenIndex'] == 7
                and row['value'].lower() == 'nan' for row in audit['nonfiniteTokens']),
            'PUBLISHED_EXECUTION_NONFINITE_PHYSICS')
    lines, changes = text.splitlines(keepends=True), []
    for row in sections.get('LID_USAGE', []):
        tokens = row['tokens']
        if len(tokens) < 9 or tokens[8] == '*':
            continue
        matches = list(re.finditer(r'"[^"\r\n]*"|[^\s;]+', lines[row['line'] - 1]))
        require(len(matches) >= 9, 'PUBLISHED_REPORT_PATH_INVALID')
        old = lines[row['line'] - 1]
        span = matches[8].span()
        lines[row['line'] - 1] = old[:span[0]] + '*' + old[span[1]:]
        changes.append({'line': row['line'], 'section': 'LID_USAGE', 'tokenIndex': 8,
                        'before': tokens[8], 'after': '*', 'reason': 'DISABLE_DETAIL_REPORT_FILE_ONLY'})
    prepared = ''.join(lines)
    # 출력 토큰 외의 인자·주석·개행 보존. 디코딩 BOM 제거도 해시에 드러낸다.
    return prepared, {'schemaVersion': 1, 'originalSha256': digest(raw),
        'executionSha256': digest(prepared.encode()), 'changes': changes,
        'bomRemoved': raw.startswith(b'\xef\xbb\xbf'), 'physicsValuesChanged': False,
        'diagnosticOnly': True, 'rankingEligible': False,
        'preservedNonfiniteUnusedTokens': audit['nonfiniteTokens']}


def load_archive(root, manifest_path):
    root = Path(root).resolve()
    manifest_raw = _read(manifest_path, 2_000_000)
    manifest = json.loads(manifest_raw)
    require(manifest.get('schemaVersion') == 1 and manifest.get('rankingEligible') is False,
            'PUBLISHED_MANIFEST_INVALID')
    for name, expected_hash in manifest.get('metadataFiles', {}).items():
        metadata_path = root / name
        require(metadata_path.resolve().is_relative_to(root), 'PUBLISHED_METADATA_PATH_INVALID')
        _read(metadata_path, 2_000_000, expected_hash)
    archive_record = manifest['archive']
    archive_path = root / archive_record['file']
    require(archive_path.resolve().is_relative_to(root), 'PUBLISHED_ARCHIVE_PATH_INVALID')
    _read(archive_path, MAX_ARCHIVE_BYTES, archive_record['sha256'])
    expected = {row['member']: row for row in manifest['members']}
    require(len(expected) == len(manifest['members']), 'PUBLISHED_MANIFEST_DUPLICATE')
    inputs = []
    with ZipFile(archive_path) as archive:
        infos = archive.infolist()
        require(len(infos) <= 1000 and sum(row.file_size for row in infos) <= MAX_EXPANDED_BYTES,
                'PUBLISHED_ARCHIVE_LIMIT_EXCEEDED')
        require(len({row.filename for row in infos}) == len(infos), 'PUBLISHED_ARCHIVE_DUPLICATE')
        files = [row for row in infos if not row.is_dir()]
        require({row.filename for row in files} == set(expected), 'PUBLISHED_ARCHIVE_MEMBER_MISMATCH')
        for info in infos:
            path = PurePosixPath(info.filename)
            require(not path.is_absolute() and not any(p in ('..', '.') for p in path.parts)
                    and '\\' not in info.filename and not stat.S_ISLNK(info.external_attr >> 16)
                    and not (info.flag_bits & 1), 'PUBLISHED_ARCHIVE_MEMBER_UNSAFE')
            if info.is_dir():
                continue
            require(info.file_size == expected[info.filename]['bytes'], 'PUBLISHED_ARCHIVE_MEMBER_SIZE')
            raw = archive.read(info)
            require(digest(raw) == expected[info.filename]['sha256'], 'PUBLISHED_ARCHIVE_MEMBER_HASH')
            if path.suffix.lower() == '.inp':
                require(len(raw) <= MAX_INPUT_BYTES, 'PUBLISHED_INPUT_SIZE_INVALID')
                inputs.append({'member': info.filename, 'raw': raw, 'audit': inspect_input(raw)})
    require(inputs, 'PUBLISHED_ARCHIVE_INPUT_REQUIRED')
    return manifest, digest(manifest_raw), sorted(inputs, key=lambda row: row['member'])
