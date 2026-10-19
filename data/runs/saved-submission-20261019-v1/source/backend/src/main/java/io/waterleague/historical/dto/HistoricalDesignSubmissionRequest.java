package io.waterleague.historical.dto;

import jakarta.validation.constraints.*;
import java.util.UUID;

public record HistoricalDesignSubmissionRequest(
    @NotNull UUID requestKey,
    @Positive long revision,
    @NotBlank @Pattern(regexp = "[a-f0-9]{64}") String snapshotSha256) {}
