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
    tools.jackson.databind.JsonNode scorePolicy,
    Period current,
    Period previous) {
  public record Period(
      LocalDate weekStart,
      Instant startsAt,
      Instant endsAt,
      Instant evaluatedTarget,
      String status,
      String comparisonStatus,
      String comparisonReason,
      String comparisonGroupHash,
      long evaluatedSeconds,
      long expectedSeconds,
      List<District> districts,
      List<Player> players,
      long participantCount,
      Player own,
      List<String> winnerDistrictIds) {
    @com.fasterxml.jackson.annotation.JsonProperty
    public long evaluatedMinutes() {
      return (evaluatedSeconds + 59) / 60;
    }

    @com.fasterxml.jackson.annotation.JsonProperty
    public long expectedMinutes() {
      return (expectedSeconds + 59) / 60;
    }
  }

  public record District(
      String districtId,
      String districtName,
      Integer rank,
      BigDecimal scoreM3,
      long evaluatedSeconds,
      long expectedSeconds) {
    @com.fasterxml.jackson.annotation.JsonProperty
    public String scoreM3Exact() {
      return scoreM3 == null ? null : scoreM3.toPlainString();
    }

    @com.fasterxml.jackson.annotation.JsonProperty
    public long evaluatedMinutes() {
      return (evaluatedSeconds + 59) / 60;
    }

    @com.fasterxml.jackson.annotation.JsonProperty
    public long expectedMinutes() {
      return (expectedSeconds + 59) / 60;
    }
  }

  public record Player(
      UUID playerId,
      String nickname,
      String districtId,
      Integer rank,
      BigDecimal scoreM3,
      long evaluatedSeconds,
      long expectedSeconds) {
    @com.fasterxml.jackson.annotation.JsonProperty
    public String scoreM3Exact() {
      return scoreM3 == null ? null : scoreM3.toPlainString();
    }

    @com.fasterxml.jackson.annotation.JsonProperty
    public long evaluatedMinutes() {
      return (evaluatedSeconds + 59) / 60;
    }

    @com.fasterxml.jackson.annotation.JsonProperty
    public long expectedMinutes() {
      return (expectedSeconds + 59) / 60;
    }
  }
}
