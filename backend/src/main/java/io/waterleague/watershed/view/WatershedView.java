package io.waterleague.watershed.view;

import java.time.Instant;
import java.util.UUID;
import tools.jackson.databind.JsonNode;

public record WatershedView(
    UUID id,
    String catalogHash,
    String state,
    Instant createdAt,
    JsonNode design,
    JsonNode result,
    String message) {}
