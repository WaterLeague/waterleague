"""워커가 발급한 로컬 작업 디렉터리에서만 실행하는 자식 프로세스."""
from pathlib import Path
import os
import resource
import sys
from .result_cache import decoded, execute
from .engine.swmm import ROOT


def main():
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CPU, (75, 75))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
    if sys.platform.startswith('linux'):
        resource.setrlimit(resource.RLIMIT_AS, (1536 * 1024 * 1024, 1536 * 1024 * 1024))
    path = Path(sys.argv[1])
    source = (path / 'model-source.json').read_bytes()
    request = decoded((path / 'request.json').read_bytes())
    cache = None if os.environ.get('SIMULATION_CACHE_ENABLED', 'true').lower() == 'false' else Path(
        os.environ.get('SIMULATION_CACHE_PATH', ROOT / 'data/private/simulation-cache'))
    execute(source, request, path, cache)


if __name__ == '__main__':
    main()
