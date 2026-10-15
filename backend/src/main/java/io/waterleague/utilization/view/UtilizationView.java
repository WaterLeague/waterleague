package io.waterleague.utilization.view;

import java.time.Instant;
import java.util.*;

public record UtilizationView(
    UUID id,
    UUID jobId,
    UUID versionId,
    String modelHash,
    UUID organizationId,
    String organizationName,
    String title,
    String purpose,
    String policyVersion,
    String termsHash,
    String state,
    int revision,
    Instant createdAt,
    Instant updatedAt) {}
