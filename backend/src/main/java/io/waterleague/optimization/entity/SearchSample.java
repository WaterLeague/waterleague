package io.waterleague.optimization.entity;

import java.math.BigDecimal;
import java.util.UUID;

public record SearchSample(
    UUID jobId,
    UUID versionId,
    String inputHash,
    String placementsSource,
    BigDecimal score,
    BigDecimal costKrw) {}
