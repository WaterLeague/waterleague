package io.waterleague.rainfall.exception;

import io.waterleague.common.exception.*;

public class RainfallException extends DomainException {
  public RainfallException(ErrorCode code) {
    super(code);
  }
}
