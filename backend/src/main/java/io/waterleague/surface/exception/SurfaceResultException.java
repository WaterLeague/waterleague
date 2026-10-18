package io.waterleague.surface.exception;

import io.waterleague.common.exception.DomainException;
import io.waterleague.common.exception.ErrorCode;

public class SurfaceResultException extends DomainException {
  public SurfaceResultException() {
    super(ErrorCode.SIMULATION_UNAVAILABLE);
  }
}
