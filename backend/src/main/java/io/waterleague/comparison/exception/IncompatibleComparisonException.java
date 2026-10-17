package io.waterleague.comparison.exception;

import io.waterleague.common.exception.DomainException;
import io.waterleague.common.exception.ErrorCode;

public class IncompatibleComparisonException extends DomainException {
  public IncompatibleComparisonException() {
    super(ErrorCode.COMPARISON_INCOMPATIBLE);
  }
}
