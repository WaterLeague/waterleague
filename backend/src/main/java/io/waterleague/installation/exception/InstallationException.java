package io.waterleague.installation.exception;

import io.waterleague.common.exception.*;

public class InstallationException extends DomainException {
  public InstallationException(ErrorCode code) {
    super(code);
  }
}
