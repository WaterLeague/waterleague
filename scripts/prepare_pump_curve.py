"""보관 제조사 PDF의 벡터 곡선을 단위와 판독 오차를 보존해 추출."""
from bisect import bisect_right
import hashlib
import json
from pathlib import Path

from pypdf import PdfReader
from pypdf.generic import ContentStream

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'data/private/facility-reference-20261018/ksb-amacan-p-50hz-1580-5-13.pdf'
SHA = '359a742139ec004925f7190fcce8f7e0914206443e97fb05bf1cd07e8864a647'
TARGET = ROOT/'data/derived/pump-curves/ksb-pa4-500-270-1450-17-v1.json'


def interpolate(rows, x):
    i = max(1, min(len(rows)-1, bisect_right([p[0] for p in rows], x)))
    a, b = rows[i-1:i+1]
    assert a[0] <= x <= b[0]
    return a[1]+(b[1]-a[1])*(x-a[0])/(b[0]-a[0])


def main():
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == SHA
    reader = PdfReader(SOURCE)
    form = reader.pages[13]['/Resources']['/XObject']['/XO2'].get_object()
    paths, current, width = [], [], None
    for args, op in ContentStream(form, reader).operations:
        if op == b'w': width = float(args[0])
        if op in (b'm', b'l'): current.append([float(v) for v in args])
        if op in (b'S', b's', b'n', b'f', b'F', b'f*'):
            if len(current) > 700:
                assert width == 70
                paths.append(current)
            current = []
    assert len(paths) == 24
    # 23·21·19·17·15·13·11·9° 순서의 양정·NPSHr·축동력 3개 곡선.
    selected = paths[9:12]
    assert [len(p) for p in selected] == [800, 753, 800]
    assert selected[0][0] == [7432, 6702] and selected[0][-1] == [13710, 12598]
    xaxis = [[4531, 400], [7458, 600], [10384, 800], [13310, 1000], [16237, 1200]]
    axes = [[[6000, 6], [8659, 4], [11318, 2], [13312, .5]],
            [[14612, 12], [15339, 10], [17158, 5], [18612, 1]],
            [[19112, 19], [20846, 15], [23014, 10], [25182, 5], [26049, 3]]]
    converted = [[[interpolate(xaxis, x), interpolate(axis, y)] for x, y in path]
                 for path, axis in zip(selected, axes)]
    # 세 곡선이 함께 공개된 구간 안에서만 사용하며 끝점 외삽을 허용하지 않는다.
    flows = list(range(700, 1001, 10))
    rows = [{'flowM3h': q, 'headM': round(interpolate(converted[0], q), 6),
             'npshRequiredM': round(interpolate(converted[1], q), 6),
             'shaftPowerKw': round(interpolate(converted[2], q), 6)} for q in flows]
    errors = {}
    for name, points in zip(('headM', 'npshRequiredM', 'shaftPowerKw'), converted):
        sampled = [[r['flowM3h'], r[name]] for r in rows]
        errors[name] = max(abs(y-interpolate(sampled, x)) for x, y in points if 700 <= x <= 1000)
    value = {'schemaVersion': 1, 'id': 'KSB_PA4_500_270_1450_17_V1',
        'classification': 'MANUFACTURER_GRAPH_DIGITIZATION_NOT_SITE_MEASURED',
        'model': 'Amacan PA4 500-270', 'frequencyHz': 50, 'speedRpm': 1450, 'bladeAngleDeg': 17,
        'fluidDensityKgM3': 1000, 'maximumKinematicViscosityMm2S': 20,
        'source': {'author': 'KSB SE & Co. KGaA', 'document': '1580.5/13-EN',
            'publishedDate': '2024-04-16', 'page': 14, 'figure': 'K4200358s/2',
            'url': 'https://www.lenntech.com/Data-sheets/KSB-AmaCan-P-50-Hz-EN-L.pdf',
            'manufacturerUrl': 'https://www.ksb.com/en-gb/lc/products/pump/submersible-pump-in-discharge-tube/amacan-p/a28a',
            'localPath': str(SOURCE.relative_to(ROOT)), 'sha256': SHA,
            'fullDocumentRedistribution': False},
        'extraction': {'method': 'PDF_VECTOR_PATH_LINEAR_AXIS_CONVERSION', 'form': '/XO2',
            'pathIndices': [9, 10, 11], 'flowAxis': xaxis, 'valueAxes': axes,
            'sourceStrokeWidth': 70, 'flowStepM3h': 10, 'maximumInterpolationDifference': errors,
            'halfStrokeApproximation': {'flowM3h': 2.393, 'headM': .0264,
                                        'npshRequiredM': .097, 'shaftPowerKw': .081},
            'generatorSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        'points': rows, 'extrapolationAllowed': False, 'rankingEligible': False,
        'headReference': 'REFERENCE_PLANE_0_5_M_ABOVE_MOTOR_INCLUDES_RISER_TO_PLANE',
        'limitations': ['제조사 그래프의 판독값이며 개별 펌프 시험 성적이나 서울 기존 펌프 제원이 아님',
            '50Hz·1450rpm·날개각 17° 고정; 60Hz 또는 다른 회전수로 임의 환산하지 않음',
            '700~1000m³/h는 세 공개 곡선의 공통 판독 구간 중 선택 범위이며 제품 전체 운전 범위가 아님',
            '선 두께와 표본 보간 오차는 제조사 제작 공차·현장 성능 불확실성과 별개',
            '흡입조 형상·최소 잠김·NPSHa·모터 효율·현장 손실·시공 가격 추가 확인 필요',
            '축동력은 전기 입력 전력·전기요금과 구분']}
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode()
    if TARGET.exists() and TARGET.read_bytes() != raw:
        raise ValueError('PUMP_CURVE_EXISTING_VERSION_CHANGED')
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_bytes(raw)
    print(json.dumps({'path': str(TARGET.relative_to(ROOT)), 'sha256': hashlib.sha256(raw).hexdigest(),
                      'errors': errors, 'bounds': [rows[0], rows[-1]]}))


if __name__ == '__main__': main()
