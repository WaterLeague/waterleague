package io.waterleague.comparison.view;

import java.time.Instant;
import java.util.*;

public record ComparisonView(
    UUID id,
    String title,
    UUID sourceVersionId,
    Instant createdAt,
    Map<String, Object> sourceVersion,
    List<Map<String, Object>> jobs) {}
