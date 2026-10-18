package io.waterleague.historical.view;

import java.time.Instant;
import java.util.UUID;
import tools.jackson.databind.JsonNode;

public record HistoricalSubmissionView(
    UUID id,
    String state,
    Instant createdAt,
    int placementCount,
    JsonNode result,
    String message) {}
