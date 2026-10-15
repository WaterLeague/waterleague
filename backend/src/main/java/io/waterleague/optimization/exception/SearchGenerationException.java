package io.waterleague.optimization.exception;

import io.waterleague.common.exception.*;

public class SearchGenerationException extends DomainException {
  public SearchGenerationException(ErrorCode code) {
    super(code);
  }
}
