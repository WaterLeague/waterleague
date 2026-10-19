"""효과·귀속 계산의 외부에 노출 가능한 오류 코드."""
import re


class EvaluationError(ValueError):
    def __init__(self, code):
        if not re.fullmatch(r'[A-Z][A-Z0-9_]{1,79}', code):
            code = 'EVALUATION_FAILED'
        self.code = code
        super().__init__(code)


def require(condition, code):
    if not condition:
        raise EvaluationError(code)
