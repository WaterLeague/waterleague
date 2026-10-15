package io.waterleague.simulation.exception;

import io.waterleague.common.exception.*;

public final class ResultQualityException extends DomainException {
  public ResultQualityException() {
    super(ErrorCode.RESULT_QUALITY_FAILED);
  }
}
