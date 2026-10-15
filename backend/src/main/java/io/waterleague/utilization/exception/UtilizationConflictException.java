package io.waterleague.utilization.exception;

import io.waterleague.common.exception.*;

public class UtilizationConflictException extends DomainException {
  public UtilizationConflictException() {
    super(ErrorCode.UTILIZATION_CONFLICT);
  }
}
