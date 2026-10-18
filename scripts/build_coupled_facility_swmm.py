"""시설 상태·교환·원 지표를 함께 읽는 별도 EPA 빌드. 기존 바이너리 보존."""
import hashlib
import json
import platform
import subprocess
import tarfile
from pathlib import Path
from urllib.request import urlopen

from build_live_swmm import ROOT, REVISION, ARCHIVE_HASH


def main():
    archive = ROOT / 'tmp/swmm/source.tar.gz'
    if not archive.exists():
        with urlopen(f'https://api.github.com/repos/USEPA/Stormwater-Management-Model/tarball/{REVISION}',
                     timeout=30) as response:
            raw = response.read(30_000_001)
        if len(raw) > 30_000_000 or hashlib.sha256(raw).hexdigest() != ARCHIVE_HASH:
            raise ValueError('EPA_SOURCE_HASH_MISMATCH')
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(raw)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_HASH:
        raise ValueError('EPA_SOURCE_HASH_MISMATCH')
    name = 'coupled-facility-swmm'
    source, build = ROOT / f'tmp/{name}-source', ROOT / f'tmp/{name}-build'
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
    observer = ROOT / 'simulation/native/network_snapshot.inc'
    solver = source / 'src/solver/swmm5.c'
    solver.write_bytes(solver.read_bytes() + b'\n' + observer.read_bytes())
    extension = ROOT / 'simulation/native/network_exchange.inc'
    metrics = ROOT / 'simulation/native/network_metrics.inc'
    extension_bytes = extension.read_bytes()
    original = b'do { error = wl_observedStep(&elapsedTime); } while (elapsedTime > 0.0 && !error);'
    if extension_bytes.count(original) != 1:
        raise ValueError('NETWORK_METRICS_HOOK_MISMATCH')
    extension_bytes = extension_bytes.replace(original, b'''do {
        double before = NewRoutingTime / 1000.0;
        error = wl_observedStep(&elapsedTime);
        if (!error) wl_metricsObserve(before);
    } while (elapsedTime > 0.0 && !error);''')
    solver.write_bytes(solver.read_bytes() + b'\n' + metrics.read_bytes() + b'\n' + extension_bytes)
    facility = ROOT / 'simulation/native/connected_lid_snapshot.inc'
    lid = source / 'src/solver/lid.c'
    lid.write_bytes(lid.read_bytes() + b'\n' + facility.read_bytes())
    options = ['-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_INSTALL_RPATH=$ORIGIN']
    if platform.system() == 'Darwin':
        omp = subprocess.check_output(['brew', '--prefix', 'libomp'], text=True).strip()
        options = ['-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_INSTALL_RPATH=@loader_path',
                   f'-DOpenMP_C_FLAGS=-Xpreprocessor -fopenmp -I{omp}/include',
                   '-DOpenMP_C_LIB_NAMES=omp', f'-DOpenMP_omp_LIBRARY={omp}/lib/libomp.dylib']
    subprocess.run(['cmake', '-S', str(source), '-B', str(build), *options], check=True)
    subprocess.run(['cmake', '--build', str(build), '-j', '4'], check=True)
    subprocess.run(['cmake', '--install', str(build)], check=True)
    library = build / 'install/bin' / ('libswmm5.dylib' if platform.system() == 'Darwin' else 'libswmm5.so')
    (library.parent / 'network-build.json').write_text(json.dumps({
        'schemaVersion': 1, 'engineVersion': '5.2.4', 'revision': REVISION,
        'sourceArchiveSha256': ARCHIVE_HASH,
        'observerSha256': hashlib.sha256(observer.read_bytes()).hexdigest(),
        'binarySha256': hashlib.sha256(library.read_bytes()).hexdigest(),
        'modification': 'READ_ONLY_LID_METRICS_AND_MILLISECOND_STRIDE_NO_SOLVER_EQUATION_CHANGES',
        'exchangeVersion': 1, 'exchangeSha256': hashlib.sha256(extension.read_bytes()).hexdigest(),
        'metricsVersion': 1, 'metricsSha256': hashlib.sha256(metrics.read_bytes()).hexdigest(),
        'facilityObserverVersion': 1, 'facilityObserverSha256': hashlib.sha256(facility.read_bytes()).hexdigest(),
        'builderSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }, indent=2) + '\n')


if __name__ == '__main__':
    main()
