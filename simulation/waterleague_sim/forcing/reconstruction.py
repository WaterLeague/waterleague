"""원문 재계산에서 libm의 마지막 자리 차이만 허용하는 비교."""
import math


def equivalent(left, right):
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(equivalent(left[k], right[k]) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(equivalent(a, b) for a, b in zip(left, right))
    if type(left) in (int, float) and type(right) in (int, float):
        if not math.isfinite(left) or not math.isfinite(right):
            return False
        if type(left) is int and type(right) is int:
            return left == right
        # 삼각함수·뺄셈의 플랫폼 차이만 허용하며 원문·파일 해시는 별도로 엄격히 검사한다.
        tolerance = 64 * max(math.ulp(left), math.ulp(right), math.ulp(1.0))
        return abs(left - right) <= tolerance
    return type(left) is type(right) and left == right
