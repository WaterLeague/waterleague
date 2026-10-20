"""부호가 바뀌는 체적 원장의 작은 증분 보존."""


class CompensatedSum:
    def __init__(self):
        self.total = 0.
        self.correction = 0.

    def add(self, value):
        updated = self.total + value
        # 큰 누적량과 작은 증분의 덧셈에서 소실된 하위 비트를 별도 누적한다.
        self.correction += ((self.total-updated)+value if abs(self.total) >= abs(value)
                            else (value-updated)+self.total)
        self.total = updated

    @property
    def value(self):
        return self.total + self.correction
