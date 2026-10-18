package io.waterleague.cost.exception;

import io.waterleague.common.exception.DomainException;
import io.waterleague.common.exception.ErrorCode;

public class CostException extends DomainException {
  public CostException() {
    super(ErrorCode.COST_DATA_INVALID);
  }
}
