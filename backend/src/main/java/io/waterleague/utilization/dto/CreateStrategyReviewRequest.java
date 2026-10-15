package io.waterleague.utilization.dto;

import jakarta.validation.constraints.*;

public record CreateStrategyReviewRequest(
    @NotBlank @Pattern(regexp = "CANDIDATE|NEEDS_EVIDENCE|NOT_SELECTED") String state,
    @NotBlank @Size(max = 2000) String reason,
    @NotBlank @Size(max = 2000) String limitations) {}
