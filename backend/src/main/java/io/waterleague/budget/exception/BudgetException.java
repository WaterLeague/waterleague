package io.waterleague.budget.exception;

import io.waterleague.common.exception.DomainException;
import io.waterleague.common.exception.ErrorCode;

public class BudgetException extends DomainException {
  public BudgetException(ErrorCode code) {
    super(code);
  }
}
