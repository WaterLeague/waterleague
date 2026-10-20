"""원형 건물에서 축척별 배경 표시를 생성하며 선택·면적·계산에 사용하지 않는다."""
import argparse
import gzip
import json
import math
from pathlib import Path

import prepare_seoul_topography as source
import prepare_seoul_spatial as spatial

PUBLIC = source.ROOT / 'frontend/public/data'


def build(output):
    if output.exists() or output.is_symlink():
        raise ValueError('기존 축소도 묶음 덮어쓰기 금지')
    city_path = PUBLIC / 'seoul-native-v1/city.json'
    city_sha = spatial.file_sha256(city_path)
    city = json.loads(city_path.read_bytes())
    districts = [district['id'] for district in city['districts']]
    levels = {100: {}, 25: {}}
    count = 0
    for index, entry in enumerate(city['tiles']):
        stored = (PUBLIC / 'seoul-native-v1' / entry['file']).read_bytes()
        if source.digest(stored) != entry['storedSha256']:
            raise ValueError('건물 타일 해시 불일치')
        raw = gzip.decompress(stored)
        if source.digest(raw) != entry['sha256'] or len(raw) != entry['bytes']:
            raise ValueError('건물 원문 해시 불일치')
        for building in json.loads(raw)['buildings']:
            points = [point for polygon in building['polygons'] for point in polygon[0]]
            minx, maxx = min(p[0] for p in points), max(p[0] for p in points)
            miny, maxy = min(p[1] for p in points), max(p[1] for p in points)
            x, y = (minx + maxx) / 2, (miny + maxy) / 2
            record = [round(v, 2) for v in (x, y, maxx - minx, maxy - miny, building['heightM'])]
            record.extend([districts.index(building['districtId']), index])
            score = (building['areaM2'], building['id'])
            for spacing, cells in levels.items():
                key = (math.floor(x / spacing), math.floor(y / spacing))
                if key not in cells or score > cells[key][0]:
                    cells[key] = (score, record)
            count += 1
        if (index + 1) % 100 == 0:
            print(source.canonical(dict(tiles=index + 1, total=len(city['tiles']))), flush=True)
    output.mkdir()
    entries = []
    for spacing, cells in levels.items():
        records = [record for _, record in (cells[key] for key in sorted(cells))]
        raw = (source.canonical(dict(schemaVersion=1, spacingM=spacing, buildings=records)) + '\n').encode()
        name = str(spacing) + '.json.gz'
        stored = gzip.compress(raw, compresslevel=9, mtime=0)
        (output / name).write_bytes(stored)
        entries.append(dict(spacingM=spacing, file=name, bytes=len(raw), sha256=source.digest(raw), count=len(records),
            storedBytes=len(stored), storedSha256=source.digest(stored)))
    manifest = dict(schemaVersion=1, sourceCitySha256=city_sha, sourceBuildingCount=count,
        generatorSha256=spatial.file_sha256(__file__), districts=districts, tileIds=[entry['id'] for entry in city['tiles']],
        levels=entries, policy=dict(displayOnly=True, cellsSelectLargestSourceFootprint=True,
            axisAlignedBoundingBoxes=True, heightSourceUnchanged=True, selectionEnabled=False, hydraulicInputsChanged=False))
    (output / 'index.json').write_text(source.canonical(manifest) + '\n')
    if count != city['buildingCount'] or spatial.file_sha256(city_path) != city_sha:
        raise ValueError('축소도 생성 중 건물 원문 변경')
    print(source.canonical(dict(indexSha256=spatial.file_sha256(output / 'index.json'), levels=entries)), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=PUBLIC / 'seoul-overview-v1')
    build(parser.parse_args().output.absolute())
