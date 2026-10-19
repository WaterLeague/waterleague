"""표시 반올림과 분리한 10진 원값·해시·유리수 연산."""
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import hashlib
import json
import re

from .exception import EvaluationError, require


def canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                          separators=(',', ':')).encode()
    except (TypeError, ValueError, OverflowError):
        raise EvaluationError('EVALUATION_JSON_INVALID') from None


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def is_hash(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def number(value):
    require(type(value) in (str, int, float) and len(str(value)) <= 100, 'EVALUATION_NUMBER_INVALID')
    try:
        parsed = Decimal(str(value))
    except InvalidOperation:
        require(False, 'EVALUATION_NUMBER_INVALID')
    require(parsed.is_finite() and len(parsed.as_tuple().digits) <= 40
            and -40 <= parsed.as_tuple().exponent <= 40 and abs(parsed) <= Decimal('1e30'),
            'EVALUATION_NUMBER_INVALID')
    return Fraction(parsed)


def encoded(value):
    return {'exact': str(value.numerator) + '/' + str(value.denominator), 'value': float(value)}
