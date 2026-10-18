package io.waterleague.historical.view;

import java.time.Instant;
import tools.jackson.databind.JsonNode;

public record HistoricalDesignView(
    String eventId, long revision, String snapshotSha256, Instant createdAt, JsonNode snapshot) {}
