package io.waterleague.league.exception;

import io.waterleague.common.exception.*;

public class LeagueException extends DomainException {
  public LeagueException(ErrorCode code) {
    super(code);
  }
}
