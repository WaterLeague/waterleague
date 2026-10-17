package io.waterleague.analysis.exception;

import io.waterleague.common.exception.*;

public class IncompatibleAnalysisException extends DomainException {
  public IncompatibleAnalysisException() {
    super(ErrorCode.ANALYSIS_INCOMPATIBLE);
  }
}
