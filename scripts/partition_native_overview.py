"""기존 축소도 원문을 구별로 나눠 대회 외 구의 전송을 제외한다."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode()


def partition(output):
    index_path = output / 'index.json'
    original = index_path.read_bytes()
    index = json.loads(original)
    entries = []
    for level in index['levels']:
        raw = gzip.decompress((output / level['file']).read_bytes())
        if digest(raw) != level['sha256'] or len(raw) != level['bytes']:
            raise ValueError('축소도 원문 해시 불일치')
        source = json.loads(raw)
        if len(source['buildings']) != level['count']:
            raise ValueError('축소도 건물 개수 불일치')
        count = 0
        for number, district in enumerate(index['districts']):
            rows = [row for row in source['buildings'] if row[5] == number]
            count += len(rows)
            payload = canonical(dict(schemaVersion=1, spacingM=level['spacingM'], buildings=rows))
            stored = gzip.compress(payload, compresslevel=9, mtime=0)
            name = f"districts/{district}/{level['spacingM']}.json.gz"
            path = output / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(stored)
            entries.append(dict(districtId=district, spacingM=level['spacingM'], file=name,
                bytes=len(payload), sha256=digest(payload), count=len(rows),
                storedBytes=len(stored), storedSha256=digest(stored)))
        if count != level['count']:
            raise ValueError('구별 분할 건물 개수 불일치')
    index['districtLevels'] = entries
    index['partition'] = dict(sourceIndexSha256=index.get('partition', {}).get('sourceIndexSha256', digest(original)),
        generatorSha256=digest(Path(__file__).read_bytes()), originalRecordsUnchanged=True)
    index_path.write_bytes(canonical(index))
    print(digest(index_path.read_bytes()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'frontend/public/data/seoul-overview-v1')
    partition(parser.parse_args().output)
