"""EPA 침투식 원본과 배치 인터페이스를 OpenMP 없이 별도 빌드."""
import hashlib
import json
import platform
import subprocess
import tarfile
from pathlib import Path

from build_live_swmm import ROOT, REVISION, ARCHIVE_HASH


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    archive = ROOT / 'tmp/swmm/source.tar.gz'
    if sha(archive) != ARCHIVE_HASH:
        raise ValueError('EPA_SOURCE_HASH_MISMATCH')
    source = ROOT / 'tmp/surface-infiltration-source'
    build = ROOT / 'tmp/surface-infiltration-build'
    source.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as bundle:
        prefix = bundle.getmembers()[0].name.split('/')[0]
        for item in bundle.getmembers():
            relative = Path(item.name).relative_to(prefix)
            if '..' in relative.parts or item.issym() or item.islnk():
                raise ValueError('EPA_ARCHIVE_INVALID')
            target = source / relative
            if item.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif item.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(bundle.extractfile(item).read())
    native = ROOT / 'simulation/native/surface_infiltration.inc'
    original = source / 'src/solver/infil.c'
    original_hash = sha(original)
    original.write_bytes(original.read_bytes() + b'\n' + native.read_bytes())
    cmake = source / 'src/solver/CMakeLists.txt'
    original_cmake_hash = sha(cmake)
    link = '$<$<BOOL:OpenMP_C_FOUND>:OpenMP::OpenMP_C>'
    if cmake.read_text().count(link) != 1:
        raise ValueError('EPA_CMAKE_LINK_MISMATCH')
    # 원본 조건식의 변수명 리터럴 때문에 비활성화 후에도 생기는 OpenMP 링크를 제거한다.
    cmake.write_text(cmake.read_text().replace(link, ''))
    subprocess.run(['cmake', '-S', str(source), '-B', str(build), '-DCMAKE_BUILD_TYPE=Release',
                    '-DCMAKE_DISABLE_FIND_PACKAGE_OpenMP=TRUE'], check=True)
    subprocess.run(['cmake', '--build', str(build), '--target', 'swmm5', '-j', '4'], check=True)
    library = build / 'src/solver' / ('libswmm5.dylib' if platform.system() == 'Darwin' else 'libswmm5.so')
    (library.parent / 'soil-build.json').write_text(json.dumps({
        'schemaVersion': 1, 'engineVersion': '5.2.4', 'revision': REVISION,
        'sourceArchiveSha256': ARCHIVE_HASH, 'originalInfiltrationSha256': original_hash,
        'originalSolverCMakeSha256': original_cmake_hash,
        'extensionSha256': sha(native), 'builderSha256': sha(Path(__file__)),
        'binarySha256': sha(library), 'openMP': False,
        'modification': 'BATCH_INTERFACE_NO_EPA_EQUATION_CHANGES',
    }, indent=2) + '\n')


if __name__ == '__main__':
    main()
