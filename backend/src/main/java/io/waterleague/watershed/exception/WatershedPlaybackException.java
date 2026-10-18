package io.waterleague.watershed.exception;

import io.waterleague.common.exception.DomainException;
import io.waterleague.common.exception.ErrorCode;

public class WatershedPlaybackException extends DomainException {
  public WatershedPlaybackException() {
    super(ErrorCode.SIMULATION_UNAVAILABLE);
  }
}
