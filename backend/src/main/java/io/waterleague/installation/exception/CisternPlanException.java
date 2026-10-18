package io.waterleague.installation.exception;

import io.waterleague.common.exception.DomainException;
import io.waterleague.common.exception.ErrorCode;

public class CisternPlanException extends DomainException {
  public CisternPlanException(ErrorCode code) {
    super(code);
  }
}
