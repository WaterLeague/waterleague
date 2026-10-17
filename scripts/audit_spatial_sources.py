"""공식 성수 DEM·토지피복 원본 검사. 모델 입력·원본 수정 없음."""
import argparse
import hashlib
import json
import math
import os
import shutil
import stat
import subprocess
import tempfile
import unicodedata
import zipfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

import pyproj
import shapely
from pyproj.aoi import AreaOfInterest
from pyproj.transformer import TransformerGroup
from shapely.geometry import Polygon, box, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
BOUNDS = (127.0525, 37.5430, 127.0555, 37.5455)
EXPECTED = {
    'dem-2024': '1686afb246370b1a7b6ad9a5f510c75cabc73985324feb33c803838aea2d3000',
    'dem-2025': 'a99a82b4e98f5e26445f88801b95d87b823bfef154db804acbb60fc136683feb',
    'landcover-2024': '88456ce3a6ea11bd003ec9d9b0b7ebd67dd09d636a4dff572a083ebed18edf1f',
}


class SpatialDataError(ValueError):
    pass


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def extract_checked(path, destination, expected=None):
    if path.is_symlink() or path.stat().st_size > 64 * 1024**2:
        raise SpatialDataError('원본 링크 또는 크기 오류')
    checksum = digest(path)
    if expected is not None and checksum != expected:
        raise SpatialDataError('등록 원본 해시 불일치')
    destination.mkdir(mode=0o700)
    members, names = [], set()
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > 64 or sum(i.file_size for i in entries) > 128 * 1024**2:
            raise SpatialDataError('압축 구성 수 또는 해제 크기 초과')
        for item in entries:
            name = unicodedata.normalize('NFC', item.filename)
            parts = PurePosixPath(name)
            mode = stat.S_IFMT(item.external_attr >> 16)
            if (parts.is_absolute() or '..' in parts.parts or '\\' in name or ':' in name
                    or not parts.parts or name in names or item.flag_bits & 1
                    or mode not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise SpatialDataError('압축 경로·중복·링크·암호화 오류')
            names.add(name)
            target = destination.joinpath(*parts.parts)
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                data = archive.read(item)
            except zipfile.BadZipFile as exc:
                raise SpatialDataError('압축 파일 CRC 오류') from exc
            if len(data) != item.file_size:
                raise SpatialDataError('압축 파일 크기 불일치')
            with target.open('xb') as out:
                out.write(data)
            members.append({'name': name, 'bytes': len(data), 'sha256': digest(target)})
    return {'sha256': checksum, 'bytes': path.stat().st_size, 'crcVerified': True,
            'members': sorted(members, key=lambda x: x['name'])}


def command(*args):
    executable = shutil.which(args[0])
    if not executable:
        raise SpatialDataError('GDAL 도구 설치 필요: ' + args[0])
    result = subprocess.run([executable, *map(str, args[1:])], check=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
                            env={**os.environ, 'PROJ_NETWORK': 'OFF', 'GDAL_PAM_ENABLED': 'NO'})
    if len(result.stdout) > 80 * 1024**2:
        raise SpatialDataError('검사 도구 출력 크기 초과')
    return result.stdout.decode('utf-8')


def study_boundary(wkt):
    pyproj.network.set_network_enabled(False)
    crs = pyproj.CRS.from_wkt(wkt)
    if not crs.is_projected or any(a.unit_conversion_factor != 1 for a in crs.axis_info[:2]):
        raise SpatialDataError('미터 투영 좌표계 필요')
    group = TransformerGroup('EPSG:4326', crs, always_xy=True,
                             area_of_interest=AreaOfInterest(*BOUNDS), allow_ballpark=True)
    if not group.transformers:
        raise SpatialDataError('대상 지역 좌표 변환 없음')
    transformer = group.transformers[0]
    west, south, east, north = BOUNDS
    corners = [(west, south), (east, south), (east, north), (west, north)]
    points = []
    for start, end in zip(corners, corners[1:] + corners[:1]):
        for index in range(20):
            f = index / 20
            points.append(transformer.transform(start[0] + f * (end[0] - start[0]),
                                                start[1] + f * (end[1] - start[1]), errcheck=True))
    boundary = Polygon(points)
    if not boundary.is_valid or boundary.area <= 0:
        raise SpatialDataError('변환 경계 오류')
    return boundary, {'originalWkt': wkt, 'identifiedEpsg': crs.to_epsg(),
                      'bestOperationAvailable': group.best_available,
                      'operation': transformer.description, 'pipeline': transformer.definition,
                      'statedOperationAccuracyM': transformer.accuracy,
                      'usesBallpark': any(o.has_ballpark_transformation for o in transformer.operations),
                      'coordinateEpoch': None, 'axisOrder': 'x,y; input longitude,latitude',
                      'limitation': '변환 연산 정확도는 원본 측량 정확도 또는 시점 정합의 보증이 아님'}


def stats(values):
    return {'count': len(values), 'min': min(values) if values else None,
            'max': max(values) if values else None,
            'mean': math.fsum(values) / len(values) if values else None}


def dem(path):
    info = json.loads(command('gdalinfo', '-json', '-if', 'HFA', path))
    size, transform, bands = info['size'], info['geoTransform'], info['bands']
    if (len(bands) != 1 or bands[0]['type'] != 'Float32' or math.prod(size) > 1_000_000
            or transform[1] <= 0 or transform[5] >= 0 or transform[2] != 0 or transform[4] != 0):
        raise SpatialDataError('지원하지 않는 DEM 구조')
    boundary, crs = study_boundary(info['coordinateSystem']['wkt'])
    nodata = bands[0].get('noDataValue')
    rows = [tuple(map(float, line.split())) for line in command(
        'gdal_translate', '-q', '-of', 'XYZ', path, '/vsistdout/').splitlines()]
    if len(rows) != math.prod(size) or any(len(row) != 3 for row in rows):
        raise SpatialDataError('DEM 격자 수 오류')
    valid, selected, invalid = [], [], Counter()
    coverage = valid_coverage = 0.0
    half_x, half_y = transform[1] / 2, -transform[5] / 2
    for index, (x, y, value) in enumerate(rows):
        col, row = index % size[0], index // size[0]
        if abs(x - (transform[0] + (col + .5) * transform[1])) > 1e-6 or abs(
                y - (transform[3] + (row + .5) * transform[5])) > 1e-6:
            raise SpatialDataError('DEM 원본 셀 중심·순서 불일치')
        ok = math.isfinite(value) and value != nodata
        if ok:
            valid.append(value)
        else:
            invalid['nodata' if value == nodata else 'nonfinite'] += 1
        minx, miny, maxx, maxy = boundary.bounds
        if x + half_x <= minx or x - half_x >= maxx or y + half_y <= miny or y - half_y >= maxy:
            continue
        area = boundary.intersection(box(x-half_x, y-half_y, x+half_x, y+half_y)).area
        if area <= 0:
            continue
        coverage += area
        if ok:
            valid_coverage += area
        selected.append({'row': row, 'column': col, 'value': value if ok else None,
                         'intersectionAreaM2': area})
    report = {'driver': info['driverShortName'], 'size': size, 'geoTransform': transform,
              'noDataValue': nodata, 'bandUnit': bands[0].get('unit'),
              'verticalDatum': None, 'acquisitionDate': None, 'metadata': info.get('metadata', {}),
              'crs': crs, 'wholeTileRawValues': stats(valid), 'invalidCounts': dict(invalid),
              'study': {'boundaryAreaM2': boundary.area, 'intersectingCellCount': len(selected),
                        'coveredAreaM2': coverage, 'validAreaM2': valid_coverage,
                        'validFraction': valid_coverage / boundary.area,
                        'rawValues': stats([s['value'] for s in selected if s['value'] is not None]),
                        'cells': selected}}
    return report, rows


def landcover(path, work):
    wkt = path.with_suffix('.prj').read_text()
    boundary, crs = study_boundary(wkt)
    target = work / 'landcover-native.json'
    command('ogr2ogr', '-f', 'GeoJSON', '-oo', 'ENCODING=CP949', target, path)
    if target.stat().st_size > 80 * 1024**2:
        raise SpatialDataError('피복 변환 출력 크기 초과')
    features = json.loads(target.read_text())['features']
    return {**analyze_landcover(features, boundary), 'crs': crs,
            'dbfEncoding': 'CP949; XML eucKR declaration'}


def analyze_landcover(features, boundary):
    if len(features) > 100_000:
        raise SpatialDataError('피복 도형 수 초과')
    invalid, dates, classes = Counter(), Counter(), defaultdict(lambda: {'count': 0, 'areaM2': 0.0})
    clips, selected_dates, selected_ids, invalid_near = [], Counter(), [], []
    for index, feature in enumerate(features):
        geometry, props = shape(feature['geometry']), feature['properties']
        dates[str(props.get('IMG_DATE'))] += 1
        if not geometry.is_valid or geometry.is_empty:
            invalid[shapely.is_valid_reason(geometry)] += 1
            if not geometry.is_empty and box(*geometry.bounds).intersects(boundary):
                invalid_near.append({'featureIndex': index, 'reason': shapely.is_valid_reason(geometry),
                                     'classCode': props.get('L3_CODE')})
            continue
        if not geometry.intersects(boundary):
            continue
        clip = geometry.intersection(boundary)
        if clip.area <= 0:
            continue
        code, name = props.get('L3_CODE'), props.get('L3_NAME')
        if not code or not name or '\ufffd' in name:
            raise SpatialDataError('피복 분류 코드 또는 문자셋 오류')
        classes[code]['name'] = name
        classes[code]['count'] += 1
        classes[code]['areaM2'] += clip.area
        clips.append(clip)
        selected_ids.append(index)
        selected_dates[str(props.get('IMG_DATE'))] += 1
    union_area = unary_union(clips).area
    sum_area = math.fsum(g.area for g in clips)
    return {'featureCount': len(features), 'invalidGeometries': dict(invalid),
            'invalidStudyEnvelopeCandidates': invalid_near,
            'studyGeometryStatus': 'INCOMPLETE_INVALID_GEOMETRY' if invalid_near else 'VALID_GEOMETRY_INSPECTED',
            'imageDateCounts': dict(sorted(dates.items())),
            'study': {'validGeometriesOnly': True, 'featureCount': len(clips), 'featureIndexes': selected_ids,
                      'boundaryAreaM2': boundary.area, 'summedAreaM2': sum_area,
                      'unionAreaM2': union_area, 'overlapAreaM2': max(0, sum_area-union_area),
                      'uncoveredAreaM2': max(0, boundary.area-union_area),
                      'coveredFraction': union_area / boundary.area,
                      'classes': dict(sorted(classes.items())),
                      'imageDateCounts': dict(sorted(selected_dates.items()))}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sources', type=Path, default=ROOT/'data/private/seongsu-official-20261017')
    parser.add_argument('--output', type=Path, default=ROOT/'data/private/seongsu-official-20261017/audit.json')
    args = parser.parse_args()
    if args.output.exists():
        raise SpatialDataError('기존 검사 파일 덮어쓰기 금지; 새 출력 경로 지정')
    report = {'schemaVersion': 1, 'boundsWgs84': BOUNDS, 'calibrationEligible': False,
              'modelSha256': digest(ROOT/'data/models/seongsu-lab.json'),
              'codeSha256': digest(Path(__file__)), 'sources': {},
              'versions': {'gdal': command('gdalinfo', '--version').strip(),
                           'pyproj': pyproj.__version__, 'proj': pyproj.proj_version_str,
                           'shapely': shapely.__version__, 'geos': shapely.geos_version_string},
              'limitations': ['원본 CRS와 좌표 epoch·수직 기준·촬영 시점의 정합 미승인',
                              '90m DEM은 도로 턱·미세 경사·관망·침수 깊이를 나타내지 않음',
                              '피복 분류는 현장 불투수율·침투율·설치 가능성 측정이 아님',
                              'IMG_DATE는 제공 필드 값이며 실제 촬영일 확인과 별도',
                              '두 DEM 값 차이는 측량 오차·제작 차이를 포함할 수 있음']}
    with tempfile.TemporaryDirectory(prefix='waterleague-spatial-') as directory:
        work = Path(directory)
        for label, checksum in EXPECTED.items():
            report['sources'][label] = extract_checked(args.sources/(label+'.zip'), work/label, checksum)
        report['dem2024'], old = dem(work/'dem-2024/37705/37705.img')
        report['dem2025'], new = dem(work/'dem-2025/37705/37705.img')
        same = (report['dem2024']['size'] == report['dem2025']['size']
                and report['dem2024']['geoTransform'] == report['dem2025']['geoTransform'])
        report['demComparison'] = {'sameNumericGrid': same, 'sameOriginalWkt':
            report['dem2024']['crs']['originalWkt'] == report['dem2025']['crs']['originalWkt']}
        if same:
            delta = [b[2]-a[2] for a,b in zip(old,new) if math.isfinite(a[2]) and math.isfinite(b[2])
                     and a[2] != report['dem2024']['noDataValue'] and b[2] != report['dem2025']['noDataValue']]
            report['demComparison'].update(rawValueDifference2025Minus2024=stats(delta),
                                            changedCellCount=sum(v != 0 for v in delta))
        report['landcover2024'] = landcover(work/'landcover-2024/37705083.shp', work)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as output:
        json.dump(report, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write('\n')
    print(json.dumps({'demCells': report['dem2024']['study']['intersectingCellCount'],
                      'landcoverFeatures': report['landcover2024']['study']['featureCount'],
                      'report': str(args.output), 'calibrationEligible': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
