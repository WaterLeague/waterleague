package io.waterleague.model.exception;

import io.waterleague.common.exception.*;

public final class ModelNotEligibleException extends DomainException {
  public ModelNotEligibleException() {
    super(ErrorCode.MODEL_NOT_ELIGIBLE);
  }
}
