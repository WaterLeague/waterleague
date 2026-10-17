package io.waterleague.weekly.entity;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record WeeklyContribution(
    UUID playerId,
    String nickname,
    String districtId,
    BigDecimal scoreM3,
    long evaluatedMinutes,
    long expectedMinutes,
    Instant evaluatedThrough) {}
