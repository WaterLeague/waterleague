"""원형 게임 후보의 허용 시설·도형을 표시 타일로 분리한다."""
import argparse
from collections import defaultdict
from contextlib import closing
import gzip
import json
from pathlib import Path
import sqlite3

import shapely
from shapely.affinity import translate
from shapely.geometry import shape, mapping

from prepare_native_features import clipped_parts
from prepare_topography_scene import ORIGIN
import prepare_seoul_topography as source
import prepare_seoul_spatial as spatial

CATALOG_SHA = 'd2d9ea2a888ee01d59f253b3848c3c30fdf4b6b3f03662b1202dc9b7a48b88b9'


def build(output):
    if output.exists():
        raise ValueError('기존 후보 표시 묶음 덮어쓰기 금지')
    database = source.ROOT / 'data/private/vworld-seoul-topography-20260307/play-v2-parking/play.sqlite'
    if spatial.file_sha256(database) != CATALOG_SHA:
        raise ValueError('게임 후보 원본 해시 불일치')
    tiles = defaultdict(list)
    count = 0
    with closing(sqlite3.connect('file:' + str(database) + '?mode=ro&immutable=1', uri=True)) as db:
        db.execute('PRAGMA trusted_schema=OFF')
        for identifier, district, mask, body in db.execute(
            "SELECT id,district_id,allowed_mask,body FROM sites WHERE kind='GROUND' AND allowed_mask<>0 ORDER BY id"
        ):
            original = json.loads(body)
            geometry = translate(shape(original['geometry']), -ORIGIN[0], -ORIGIN[1])
            for tile, kind, polygons in clipped_parts(geometry):
                if kind != 'Polygon':
                    raise ValueError('후보 면 도형 오류')
                tiles[tile].append([identifier, district, mask, [mapping(p)['coordinates'] for p in polygons]])
            count += 1
    output.mkdir()
    (output / 'tiles').mkdir()
    entries = []
    for tile, rows in sorted(tiles.items()):
        raw = (source.canonical(rows) + '\n').encode()
        stored = gzip.compress(raw, compresslevel=6, mtime=0)
        name = 'tiles/' + tile + '.json.gz'
        (output / name).write_bytes(stored)
        x, y = map(int, tile.split('_'))
        entries.append(dict(id=tile, file=name, bounds=[x*1000,y*1000,(x+1)*1000,(y+1)*1000],
            count=len(rows), bytes=len(raw), sha256=source.digest(raw),
            storedBytes=len(stored), storedSha256=source.digest(stored)))
    index = dict(schemaVersion=1, sourceCatalogSha256=CATALOG_SHA, count=count, tiles=entries,
        generatorSha256=spatial.file_sha256(__file__), sourceVertexPrecisionReduced=False,
        displayOnly=True, hydraulicInputsChanged=False, shapelyVersion=shapely.__version__)
    (output / 'index.json').write_text(source.canonical(index) + '\n')
    print(source.canonical(dict(count=count, tiles=len(entries), storedBytes=sum(e['storedBytes'] for e in entries),
        indexSha256=spatial.file_sha256(output / 'index.json'))), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=source.ROOT/'frontend/public/data/seoul-candidates-v1')
    build(parser.parse_args().output.absolute())
