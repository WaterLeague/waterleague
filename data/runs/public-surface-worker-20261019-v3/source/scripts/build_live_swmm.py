"""고정 EPA 원본에 읽기 전용 상태 관측 함수만 추가한 별도 빌드."""
import hashlib
import json
import platform
import subprocess
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVISION = '7952ca837988b1c32f791812eccc9fd64547e093'
ARCHIVE_HASH = '3f76a199573088ce47ff02491c529afb73d9953ee9d948dfc89dcd4981b4c0c0'


def main():
    archive = ROOT/'tmp/swmm/source.tar.gz'
    if not archive.exists():
        archive.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(
                f'https://api.github.com/repos/USEPA/Stormwater-Management-Model/tarball/{REVISION}',
                timeout=60) as response:
            raw = response.read(30_000_001)
        if len(raw) > 30_000_000 or hashlib.sha256(raw).hexdigest() != ARCHIVE_HASH:
            raise ValueError('EPA_SOURCE_HASH_MISMATCH')
        archive.write_bytes(raw)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_HASH:
        raise ValueError('EPA_SOURCE_HASH_MISMATCH')
    source = ROOT/'tmp/live-swmm-source'
    source.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as bundle:
        prefix = bundle.getmembers()[0].name.split('/')[0]
        for item in bundle.getmembers():
            relative = Path(item.name).relative_to(prefix)
            if '..' in relative.parts or item.issym() or item.islnk():
                raise ValueError('EPA_ARCHIVE_INVALID')
            target = source/relative
            if item.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif item.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(bundle.extractfile(item).read())
    observer = ROOT/'simulation/native/lid_snapshot.inc'
    lid = source/'src/solver/lid.c'
    lid.write_bytes(lid.read_bytes()+b'\n'+observer.read_bytes())
    build = ROOT/'tmp/live-swmm-build'
    options = ['-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_INSTALL_RPATH=$ORIGIN']
    if platform.system() == 'Darwin':
        omp = subprocess.check_output(['brew', '--prefix', 'libomp'], text=True).strip()
        options = ['-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_INSTALL_RPATH=@loader_path',
                   f'-DOpenMP_C_FLAGS=-Xpreprocessor -fopenmp -I{omp}/include',
                   '-DOpenMP_C_LIB_NAMES=omp', f'-DOpenMP_omp_LIBRARY={omp}/lib/libomp.dylib']
    subprocess.run(['cmake', '-S', str(source), '-B', str(build), *options], check=True)
    subprocess.run(['cmake', '--build', str(build), '-j', '4'], check=True)
    subprocess.run(['cmake', '--install', str(build)], check=True)
    library = build/'install/bin'/('libswmm5.dylib' if platform.system() == 'Darwin' else 'libswmm5.so')
    (library.parent/'live-build.json').write_text(json.dumps({
        'schemaVersion': 1, 'engineVersion': '5.2.4', 'revision': REVISION,
        'sourceArchiveSha256': ARCHIVE_HASH, 'observerSha256': hashlib.sha256(observer.read_bytes()).hexdigest(),
        'binarySha256': hashlib.sha256(library.read_bytes()).hexdigest(),
        'modification': 'READ_ONLY_OBSERVER_NO_SOLVER_CHANGES'}, indent=2)+'\n')


if __name__ == '__main__':
    main()
