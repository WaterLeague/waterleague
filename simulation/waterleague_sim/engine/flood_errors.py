"""관망·지표 계산의 공개 가능한 실패 코드."""


class FloodModelError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise FloodModelError(code)
