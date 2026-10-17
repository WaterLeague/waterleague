package io.waterleague.weekly.view;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

public record WeeklyView(
    Instant generatedAt,
    String ruleVersion,
    String validationLevel,
    Period current,
    Period previous) {
  public record Period(
      LocalDate weekStart,
      Instant startsAt,
      Instant endsAt,
      Instant evaluatedTarget,
      String status,
      long evaluatedMinutes,
      long expectedMinutes,
      List<District> districts,
      List<Player> players,
      long participantCount,
      Player own,
      List<String> winnerDistrictIds) {}

  public record District(
      String districtId,
      String districtName,
      Integer rank,
      BigDecimal scoreM3,
      long evaluatedMinutes,
      long expectedMinutes) {}

  public record Player(
      UUID playerId,
      String nickname,
      String districtId,
      Integer rank,
      BigDecimal scoreM3,
      long evaluatedMinutes,
      long expectedMinutes) {}
}
