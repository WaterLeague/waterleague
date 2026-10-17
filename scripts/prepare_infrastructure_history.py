"""광진구 공개 설비 행과 검토한 위치 식별자의 이력 연결."""
import csv
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'equipment-history-20261018-v1'
LINKS = {'자양빗물펌프장': 'OA-21179:6832', '구의빗물펌프장': 'OA-21179:6827',
         '중곡빗물펌프장': 'OA-21179:7082', '자양4빗물펌프장': 'OA-21179:7140',
         '광장빗물펌프장': 'OA-21179:7103'}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def build():
    manifest_path = ROOT / 'data/manifests/gwangjin-pumps-20261018.json'
    manifest = json.loads(manifest_path.read_bytes())
    raw = (ROOT / manifest['path']).read_bytes()
    assert digest(raw) == manifest['sha256'] and len(raw) == manifest['bytes']
    locations = ROOT / 'backend/src/main/resources/infrastructure/seoul-public-20261018-v1.json'
    catalog = json.loads(locations.read_bytes())
    assets = {a['id']: a for a in catalog['assets']}
    rows = list(csv.DictReader(io.StringIO(raw.decode(manifest['encoding']))))
    assert len(rows) == 9 and set(r['펌프장명'] for r in rows) == set(LINKS)
    records = []
    for index, row in enumerate(rows, 1):
        asset_id = LINKS[row['펌프장명']]
        asset = assets[asset_id]
        assert asset['districtId'] == '2419945' and asset['displayStatus'] == 'REFERENCE'
        assert asset['name'].replace(' ', '') == row['펌프장명']
        assert row['주소'].startswith('서울특별시 광진구 ')
        installed = int(row['설치연도'])
        expanded = int(row['증설연도']) if row['증설연도'] else None
        assert 1900 <= installed <= 2022 and (expanded is None or installed <= expanded <= 2022)
        records.append({'id': f'15021421:row-{index}', 'assetId': asset_id, 'sourceRow': index,
            'name': row['펌프장명'], 'address': row['주소'], 'installedYear': installed,
            'expandedYear': expanded, 'referenceDate': row['데이터기준일'],
            'motorSizeRaw': row['모터펌프규모(kW(HP))'], 'motorCount': int(row['모터펌프수량']),
            'engineSizeRaw': row['엔진펌프규모(kW(HP))'], 'engineCount': int(row['엔진펌프수량']),
            'sizeUnitRaw': 'kW(HP)', 'linkBasis': 'REVIEWED_DISTRICT_AND_NAME_CROSSWALK'})
    return {'version': VERSION, 'usage': 'REFERENCE_HISTORY_ONLY',
        'source': {'id': manifest['datasetId'], 'title': '광진구 빗물펌프장 설비 이력',
            'publisher': '서울특별시 광진구', 'url': manifest['sourceUrl'],
            'sha256': manifest['sha256'], 'license': manifest['license']},
        'locationCatalogSha256': digest(locations.read_bytes()),
        'records': records}, manifest_path


def main():
    data, manifest = build()
    raw = (json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
    target = ROOT / f'backend/src/main/resources/infrastructure/{VERSION}.json'
    meta = {'version': VERSION, 'path': str(target.relative_to(ROOT)), 'sha256': digest(raw),
        'generatorSha256': digest(Path(__file__).read_bytes()),
        'sourceManifestSha256': digest(manifest.read_bytes()), 'recordCount': len(data['records'])}
    for path, content in ((target, raw), (ROOT / f'data/manifests/{VERSION}.json',
            (json.dumps(meta, ensure_ascii=False, indent=2) + '\n').encode())):
        if path.exists() and path.read_bytes() != content:
            raise ValueError('불변 이력 자료 변경')
        path.write_bytes(content)
    print(json.dumps(meta, ensure_ascii=False))


if __name__ == '__main__':
    main()
