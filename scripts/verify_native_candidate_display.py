"""표시 후보 전체의 원형·허용 시설·타일 해시를 불변 게임 DB와 대조한다."""
import argparse
from contextlib import closing
import gzip
import json
from pathlib import Path
import sqlite3
import time
from functools import lru_cache

import shapely
from shapely.affinity import translate
from shapely.geometry import shape, box, MultiPolygon

import prepare_seoul_topography as source
import prepare_seoul_spatial as spatial
from prepare_native_candidate_display import CATALOG_SHA
from prepare_native_features import parts as geometry_parts
from prepare_topography_scene import ORIGIN


def verify():
    start = time.monotonic()
    root = source.ROOT / 'frontend/public/data/seoul-candidates-v1'
    index = json.loads((root / 'index.json').read_bytes())
    database = source.ROOT / 'data/private/vworld-seoul-topography-20260307/play-v2-parking/play.sqlite'
    assert index['sourceCatalogSha256'] == CATALOG_SHA == spatial.file_sha256(database)
    assert index['generatorSha256'] == spatial.file_sha256(source.ROOT / 'scripts/prepare_native_candidate_display.py')
    seen = set()
    parts = 0
    with closing(sqlite3.connect('file:' + str(database) + '?mode=ro&immutable=1', uri=True)) as db:
        db.execute('PRAGMA trusted_schema=OFF')
        @lru_cache(maxsize=16000)
        def original(identifier):
            district, mask, body = db.execute(
                "SELECT district_id,allowed_mask,body FROM sites WHERE id=? AND kind='GROUND'", (identifier,)
            ).fetchone()
            return district, mask, translate(shape(json.loads(body)['geometry']), -ORIGIN[0], -ORIGIN[1])
        expected_ids = {r[0] for r in db.execute("SELECT id FROM sites WHERE kind='GROUND' AND allowed_mask<>0")}
        for entry in index['tiles']:
            raw = (root / entry['file']).read_bytes()
            assert len(raw) == entry['storedBytes'] and source.digest(raw) == entry['storedSha256']
            raw = gzip.decompress(raw)
            assert len(raw) == entry['bytes'] and source.digest(raw) == entry['sha256']
            rows = json.loads(raw)
            assert len(rows) == entry['count'] == len({r[0] for r in rows})
            cell = box(*entry['bounds'])
            for identifier, district, mask, polygons in rows:
                source_district, source_mask, source_shape = original(identifier)
                assert district == source_district and mask == source_mask and mask != 0
                displayed = shapely.union_all(MultiPolygon([(p[0], p[1:]) for p in polygons]))
                expected = shapely.union_all(geometry_parts(source_shape.intersection(cell), 'Polygon'))
                assert displayed.hausdorff_distance(expected) < 1e-7, (entry['id'], identifier, displayed.geom_type, expected.geom_type, displayed.hausdorff_distance(expected), displayed.area, expected.area)
                assert abs(displayed.area - expected.area) < max(1e-6, expected.area * 1e-10)
                seen.add(identifier)
                parts += 1
        assert seen == expected_ids and len(seen) == index['count']
    return dict(schemaVersion=1, status='PASS', candidates=len(seen), parts=parts, tiles=len(index['tiles']),
        allSourceGeometriesAndAllowedTypesChecked=True, allTileHashesChecked=True,
        sourceCatalogSha256=CATALOG_SHA, indexSha256=spatial.file_sha256(root/'index.json'),
        hydraulicInputsChanged=False, elapsedSeconds=round(time.monotonic()-start, 3))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise ValueError('기존 검증 결과 덮어쓰기 금지')
    report = verify()
    args.report.write_text(source.canonical(report) + '\n')
    print(source.canonical(report), flush=True)
