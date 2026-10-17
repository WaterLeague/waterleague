package io.waterleague.strategy.exception;

import io.waterleague.common.exception.*;

public final class PlacementException extends DomainException {
  public PlacementException(ErrorCode code) {
    super(code);
  }
}
