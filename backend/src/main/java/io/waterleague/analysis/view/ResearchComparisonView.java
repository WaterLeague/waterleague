package io.waterleague.analysis.view;

import io.waterleague.comparison.view.ComparisonView;
import java.time.Instant;
import java.util.*;

public record ResearchComparisonView(
    UUID id,
    UUID organizationId,
    UUID sourceJobId,
    String requestHash,
    Instant createdAt,
    Map<String, Object> sourceSimulation,
    ComparisonView comparison) {}
