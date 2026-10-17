"""컨테이너 DB 비밀 파일 읽기. 환경값·파일 동시 지정 거부."""
import os
import stat


def database_url():
    value, path = os.environ.get('DATABASE_URL'), os.environ.get('DATABASE_URL_FILE')
    if value and path:
        raise ValueError('DB_CONFIGURATION_AMBIGUOUS')
    if path:
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as source:
                info = os.fstat(source.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > 8192:
                    raise ValueError()
                raw = source.read(8193)
                if len(raw) > 8192:
                    raise ValueError()
            value = raw.decode('utf-8').strip()
        except (OSError, ValueError):
            raise ValueError('DB_SECRET_FILE_INVALID') from None
    if not value:
        raise ValueError('DB_CONFIGURATION_MISSING')
    return value
