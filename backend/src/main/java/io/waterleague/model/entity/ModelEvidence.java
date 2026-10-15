package io.waterleague.model.entity;

import java.util.Objects;
import java.util.Set;

public record ModelEvidence(ValidationLevel level, boolean revoked, String reportHash,
                            Set<String> approvedRainfallHashes, boolean peakValidated) {
    public ModelEvidence {
        Objects.requireNonNull(level);
        approvedRainfallHashes = Set.copyOf(approvedRainfallHashes);
    }
}
