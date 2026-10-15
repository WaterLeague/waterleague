package io.waterleague.analysis.entity;

import io.waterleague.strategy.entity.Placement;
import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

public record PatternSample(
    UUID jobId, String inputHash, BigDecimal score, BigDecimal cost, List<Placement> placements) {}
