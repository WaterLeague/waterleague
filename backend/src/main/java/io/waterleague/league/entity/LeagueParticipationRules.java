package io.waterleague.league.entity;

public record LeagueParticipationRules(
    Access access, Admission admission, EntryMode entryMode, Integer teamSizeLimit) {
  public enum Access {
    PUBLIC,
    INVITE
  }

  public enum Admission {
    OPEN,
    APPROVAL
  }

  public enum EntryMode {
    INDIVIDUAL,
    TEAM
  }

  public boolean team() {
    return entryMode == EntryMode.TEAM;
  }
}
