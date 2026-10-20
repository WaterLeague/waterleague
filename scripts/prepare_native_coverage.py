"""원 도곽과 서울 경계의 차집합을 지도 미지원 표시로 생성."""
import argparse
import json
from pathlib import Path

import shapely
from shapely.affinity import translate
from shapely.geometry import shape, mapping

import audit_topography_seams as audit
import prepare_seoul_spatial as spatial
import prepare_seoul_topography as source
from topography_catalog import SpatialCatalog


def build(output):
    if output.exists():
        raise ValueError('기존 피복 표시 덮어쓰기 금지')
    catalog = SpatialCatalog(audit.SOURCE_DIRECTORY,
        json.loads((audit.SOURCE_DIRECTORY / 'summary.json').read_bytes()))
    boundaries = json.loads(audit.BOUNDARIES.read_bytes())
    frames, coverage = audit.frame_coverage(catalog, boundaries)
    evidence = json.loads((source.ROOT / 'data/manifests/seoul-topography-coverage-v1.json').read_bytes())
    assert coverage == evidence['coverage']
    by_scale = {scale: shapely.union_all([f['geometry'] for f in frames.values() if f['scale'] == scale])
        for scale in (1000, 5000)}
    city = shape(boundaries['boundary'])
    regions = {
        'UNSUPPORTED': city.difference(shapely.union_all(list(by_scale.values()))),
        'COARSE_ONLY': city.intersection(by_scale[5000].difference(by_scale[1000])),
    }
    areas = []
    for status, geometry in regions.items():
        for part in sorted(shapely.get_parts(geometry), key=lambda p: (*p.bounds, p.area)):
            if part.area <= 1e-6:
                continue
            local = translate(part, -198128, -551989)
            center = local.representative_point()
            areas.append(dict(id=f'{status}-{len(areas)}', status=status,
                areaM2=part.area, polygons=[mapping(local)['coordinates']],
                center=[center.x, center.y], bounds=list(local.bounds)))
    assert abs(sum(a['areaM2'] for a in areas if a['status'] == 'UNSUPPORTED') - coverage['uncoveredM2']) < 1e-4
    body = dict(schemaVersion=1, sourceSpatialSha256=catalog.summary['spatialSha256'],
        sourceCoverageSha256=spatial.file_sha256(source.ROOT / 'data/manifests/seoul-topography-coverage-v1.json'),
        generatorSha256=spatial.file_sha256(__file__), coverage=coverage, areas=areas,
        policy=dict(sourceSheetExtentOnly=True, geometryInferred=False, hydraulicInputsChanged=False,
            omittedNumericalFragmentAreaM2=1e-6))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(source.canonical(body) + '\n')
    print(source.canonical(dict(sha256=spatial.file_sha256(output), areas=len(areas),
        unsupportedAreaM2=coverage['uncoveredM2'], coarseOnlyAreaM2=coverage['additional5000M2'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output.absolute())
