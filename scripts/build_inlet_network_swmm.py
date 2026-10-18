"""기존 엔진을 보존하는 EPA 빗물받이 포착·역류 관측 빌드."""
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import tarfile

from build_live_swmm import ROOT, REVISION, ARCHIVE_HASH


def main():
    archive = ROOT / 'tmp/swmm/source.tar.gz'
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_HASH:
        raise ValueError('EPA_SOURCE_HASH_MISMATCH')
    source = ROOT / 'tmp/inlet-network-swmm-source'
    build = ROOT / 'tmp/inlet-network-swmm-build'
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
    observers = {'observerSha256': ('network_snapshot.inc', 'swmm5.c'),
                 'facilityObserverSha256': ('connected_lid_snapshot.inc', 'lid.c')}
    hashes = {}
    for key, (filename, solver) in observers.items():
        raw = (ROOT / 'simulation/native' / filename).read_bytes()
        path = source / 'src/solver' / solver
        if filename == 'network_snapshot.inc':
            metrics = (ROOT / 'simulation/native/network_metrics.inc').read_bytes()
            hook = b'    return 0;\n}\n\nWL_NETWORK_EXPORT int wl_networkAdvance'
            if raw.count(hook) != 1:
                raise ValueError('FACILITY_METRICS_HOOK_MISMATCH')
            observed = raw.replace(hook,
                b'    wl_metricsObserve(before / 1000.0);\n' + hook)
            flooding = b'else if (Node[j].newVolume <= Node[j].fullVolume)'
            if observed.count(flooding) != 1:
                raise ValueError('INLET_FLOOD_LEDGER_HOOK_MISMATCH')
            # EPA는 포착 절점의 월류를 외부 손실에서 제외하고 다음 단계에 지표로 반환한다.
            observed = observed.replace(flooding,
                b'else if (Node[j].inlet != CAPTURE && Node[j].newVolume <= Node[j].fullVolume)')
            path.write_bytes(path.read_bytes() + b'\nstatic void wl_metricsObserve(double before);\n'
                             + observed + b'\n' + metrics)
            hashes['metricsSha256'] = hashlib.sha256(metrics).hexdigest()
        else:
            path.write_bytes(path.read_bytes() + b'\n' + raw)
        hashes[key] = hashlib.sha256(raw).hexdigest()
    inlets = (ROOT/'simulation/native/inlet_snapshot.inc').read_bytes()
    inlet_source = source/'src/solver/inlet.c'
    raw = inlet_source.read_bytes()
    hook = b'    // --- make second pass through each inlet'
    # 포착량 제한과 지표·관망 유입 적용이 끝난 같은 단계의 값을 관측한다.
    start = raw.index(hook)
    end = raw.index(b'\n}\n', start)
    raw = raw[:end]+b'\n    wl_inletObserve(tStep);'+raw[end:]
    declarations = b'static void wl_inletObserve(double dt);\n'
    begin = raw.index(b'void inlet_findCapturedFlows(double tStep)')
    raw = raw[:begin]+declarations+raw[begin:]
    inlet_source.write_bytes(raw+b'\n'+inlets)
    hashes['inletObserverSha256'] = hashlib.sha256(inlets).hexdigest()
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
        'sourceArchiveSha256': ARCHIVE_HASH, **hashes, 'facilityObserverVersion': 1, 'metricsVersion': 1, 'inletObserverVersion': 1,
        'builderSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'binarySha256': hashlib.sha256(library.read_bytes()).hexdigest(),
        'modification': 'READ_ONLY_INLET_LID_AND_OUTFALL_METRICS_NO_SOLVER_CHANGES',
        'nodeFloodingMethod': 'EPA_EXTERNAL_FLOODING_EXCLUDING_CAPTURE_RETURNS'
    }, indent=2) + '\n')


if __name__ == '__main__':
    main()
