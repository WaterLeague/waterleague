"""초기화 비교의 원 계산·코드·고정 엔진을 함께 보관하고 오프라인 재생."""
import argparse
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

FACILITIES = ('RAIN_GARDEN', 'PERMEABLE_PAVEMENT', 'GREEN_ROOF')


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(root):
    root = root.resolve()
    if any(p.is_symlink() for p in root.rglob('*')):
        raise ValueError('초기화 묶음의 심볼릭 링크 거부')
    manifest = json.loads((root / 'manifest.json').read_bytes())
    if not isinstance(manifest, dict) or not manifest:
        raise ValueError('초기화 묶음 매니페스트 오류')
    for name, expected in manifest.items():
        if not isinstance(name, str):
            raise ValueError('초기화 묶음 파일명 오류')
        path = root / name
        if (Path(name).is_absolute()
                or '..' in Path(name).parts or path.is_symlink()
                or not path.resolve().is_relative_to(root) or not path.is_file()
                or sha(path) != expected):
            raise ValueError('초기화 묶음 파일·해시 불일치')
    actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    if actual != set(manifest) | {'manifest.json'}:
        raise ValueError('초기화 묶음의 미등록 파일 존재')
    return manifest


def preserve_forcing(study, runtime):
    from waterleague_sim.forcing.antecedent_archive import read_antecedent

    raw = (study / 'extended-antecedent.json.gz').read_bytes()
    data = json.loads(gzip.decompress(raw))
    rain = data['rainfall']
    end = datetime.fromisoformat(rain['end']).astimezone(timezone(timedelta(hours=9)))
    name = f"seoul-{end:%Y%m%d}-{rain['stationId']}-{len(rain['depthsMm'])//1440}d-v1.json.gz"
    if not re.fullmatch(r'seoul-\d{8}-\d{1,5}-(7|14|28)d-v1.json.gz', name):
        raise ValueError('선행 자료 이름 오류')
    target = runtime / 'data/derived/surface-antecedent' / name
    target.parent.mkdir(parents=True)
    target.write_bytes(raw)
    reference = {'file': name, 'sha256': sha(target)}
    for kind in ('rainfall', 'evaporation'):
        for source in data[kind]['sourceRequests']:
            if (not re.fullmatch(r'data/raw/kma-disaster-pet-[a-f0-9]{24}.txt', source['rawFile'])
                    or not re.fullmatch('[a-f0-9]{64}', source['sha256'])):
                raise ValueError('선행 원문 참조 오류')
            original = study / ('s' + source['sha256'] + '.txt')
            if sha(original) != source['sha256']:
                raise ValueError('선행 원문 해시 불일치')
            target = runtime / source['rawFile']
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.read_bytes() != original.read_bytes():
                raise ValueError('선행 원문 경로 충돌')
            shutil.copyfile(original, target)
    _, _, _, summary = read_antecedent(reference, root=runtime)
    return reference, summary


def package(study, output):
    sys.path.insert(0, str(ROOT / 'simulation'))
    from waterleague_sim.engine import continuous, facilities

    study, output = study.resolve(), output.resolve()
    if output.exists() or output.is_relative_to(study) or study.is_relative_to(output):
        raise ValueError('새 독립 출력 경로 필요')
    verify(study)
    summary = json.loads((study / 'summary.json').read_bytes())
    reports = summary['reports']
    identity = continuous.engine_identity()
    if ({r['facilityType'] for r in reports} != set(FACILITIES)
            or len(reports) != len(FACILITIES) or any(r['engine'] != identity for r in reports)):
        raise ValueError('계산 당시 엔진과 현재 고정 엔진 불일치')
    # 계산이 끝난 뒤 바뀐 코드를 당시 코드로 포장하지 않는다.
    for facility in FACILITIES:
        for name in ('continuous.py', 'swmm.py', 'initialization.py',
                     'initialization_sensitivity.py', 'facilities.py'):
            if (study / facility / name).read_bytes() != (ROOT / 'simulation/waterleague_sim/engine' / name).read_bytes():
                raise ValueError('계산 당시 코드와 현재 코드 불일치')
        if (study / facility / 'facility-designs.json').read_bytes() != facilities.CATALOG_PATH.read_bytes():
            raise ValueError('계산 당시 시설 제원과 현재 제원 불일치')
    if (study / 'analyze_initialization_sensitivity.py').read_bytes() != (ROOT / 'scripts/analyze_initialization_sensitivity.py').read_bytes():
        raise ValueError('계산 당시 실행 도구와 현재 코드 불일치')
    if sha(ROOT / 'tmp/swmm/source.tar.gz') != identity['sourceArchiveSha256']:
        raise ValueError('고정 EPA 원본 소스 해시 불일치')
    shutil.copytree(study, output)
    shutil.copyfile(output / 'manifest.json', output / 'calculation-manifest.json')
    paths = list((ROOT / 'simulation/waterleague_sim').rglob('*.py'))
    paths += list((ROOT / 'simulation/native').glob('*.inc'))
    paths += list((ROOT / 'scripts').glob('*.py'))
    paths += list((ROOT / 'backend/src/main/resources/facilities').glob('*.json'))
    paths += [ROOT / 'simulation/pyproject.toml', ROOT / 'simulation/uv.lock',
              ROOT / 'scripts/build_swmm.sh', ROOT / 'tmp/swmm/source.tar.gz']
    for path in paths:
        target = output / 'runtime' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    library = continuous.library_path()
    native = output / 'runtime/tmp/live-swmm-build/install/bin'
    native.mkdir(parents=True)
    shutil.copyfile(library, native / library.name)
    shutil.copyfile(library.parent / 'live-build.json', native / 'live-build.json')
    reference, forcing = preserve_forcing(study, output / 'runtime')
    (output / 'antecedent-verification.json').write_bytes(encoded(forcing))
    (output / 'runtime-environment.json').write_bytes(encoded({
        'schemaVersion': 1, 'python': platform.python_version(),
        'system': platform.system(), 'machine': platform.machine(), 'engine': identity,
        'calculationManifestSha256': sha(output / 'calculation-manifest.json'),
        'antecedentReference': reference,
        'replayUsesArchivedCode': True, 'networkRequiredForReplay': False,
        'limitations': ['고정 바이너리와 같은 운영체제·CPU 환경의 재현',
                        '다른 플랫폼은 보관 소스로 빌드 후 별도 수치 비교 필요'],
    }))
    (output / 'manifest.json').write_bytes(encoded({str(p.relative_to(output)): sha(p)
        for p in sorted(output.rglob('*')) if p.is_file() and p != output / 'manifest.json'}))
    print('재현 묶음', len(verify(output)), '파일 해시 일치', flush=True)


def replay(root, facility):
    root = root.resolve()
    print('재현 묶음', len(verify(root)), '파일 해시 일치', flush=True)
    environment = os.environ.copy()
    environment.pop('LIVE_SWMM_LIBRARY', None)
    environment.pop('SWMM_LIBRARY', None)
    environment['PYTHONPATH'] = str(root / 'runtime/simulation')
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    subprocess.run([sys.executable, '-B', str(root / 'runtime/scripts/package_initialization_study.py'),
                    '--verify', str(root), '--forcing-only'], env=environment, check=True, cwd=root)
    for name in FACILITIES if facility == 'ALL' else (facility,):
        subprocess.run([sys.executable, '-B',
                        str(root / 'runtime/scripts/analyze_initialization_sensitivity.py'),
                        '--replay', str(root / name)], env=environment, check=True, cwd=root)
    verify(root)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--study', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify', type=Path)
    parser.add_argument('--replay', choices=(*FACILITIES, 'ALL'))
    parser.add_argument('--forcing-only', action='store_true')
    args = parser.parse_args()
    if args.verify:
        if args.study or args.output or (args.forcing_only and args.replay):
            parser.error('검증과 포장 인자 혼용 불가')
        if args.forcing_only:
            verify(args.verify)
            sys.path.insert(0, str(ROOT / 'simulation'))
            from waterleague_sim.forcing.antecedent_archive import read_antecedent
            metadata = json.loads((args.verify / 'runtime-environment.json').read_bytes())
            _, _, _, actual = read_antecedent(metadata['antecedentReference'], root=args.verify / 'runtime')
            expected = json.loads((args.verify / 'antecedent-verification.json').read_bytes())
            if actual != expected:
                raise ValueError('보관 코드의 선행 원문 재산정 불일치')
            print('보관 코드·원문으로 선행 강우·기상 재산정 일치', flush=True)
        elif args.replay:
            replay(args.verify, args.replay)
        else:
            print('재현 묶음', len(verify(args.verify)), '파일 해시 일치')
    elif args.study and args.output and not args.replay and not args.forcing_only:
        package(args.study, args.output)
    else:
        parser.error('--study/--output 또는 --verify 필요')


if __name__ == '__main__':
    main()
