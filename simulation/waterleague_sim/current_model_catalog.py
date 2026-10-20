"""현재 연구 서비스의 수치지형도 모델만 등록. 보관 수치 입력 목록과 분리."""
import hashlib
import json
import stat

from .model_catalog import read_catalog

CATALOG_SHA256 = '0835043218ada24eb9a58f6fb0ac9b7382d8394499f8176fbe289896ab4d506b'


def read_current_catalog(directory):
    root = directory / 'current'
    path = root / 'catalog.json'
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError('CURRENT_MODEL_CATALOG_INVALID')
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= 128 * 1024:
        raise ValueError('CURRENT_MODEL_CATALOG_INVALID')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CATALOG_SHA256:
        raise ValueError('CURRENT_MODEL_CATALOG_INVALID')
    models = read_catalog(root)
    after = path.stat()
    if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
            or any(json.loads(source).get('mapId') != 'seongsu-ngii-2025-v2' for source in models.values())):
        raise ValueError('CURRENT_MODEL_CATALOG_INVALID')
    return models
