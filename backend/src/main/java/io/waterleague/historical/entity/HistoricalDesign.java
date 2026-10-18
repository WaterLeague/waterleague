package io.waterleague.historical.entity;

import java.time.Instant;
import java.util.UUID;

public record HistoricalDesign(
    UUID ownerId,
    String eventId,
    long revision,
    UUID requestKey,
    String requestRaw,
    String snapshotRaw,
    String snapshotSha256,
    Instant createdAt) {}
