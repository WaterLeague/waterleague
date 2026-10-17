package io.waterleague.historical.view;

import java.time.Instant;
import java.util.UUID;
import tools.jackson.databind.JsonNode;

public record HistoricalView(
    UUID id,
    String districtId,
    String modelHash,
    String state,
    Instant createdAt,
    JsonNode placements,
    JsonNode result,
    String message) {}
