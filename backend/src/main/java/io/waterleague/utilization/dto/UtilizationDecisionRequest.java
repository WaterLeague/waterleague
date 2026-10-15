package io.waterleague.utilization.dto;

import jakarta.validation.constraints.*;

public record UtilizationDecisionRequest(
    @Min(1) int expectedRevision,
    @NotBlank @Pattern(regexp = "[a-f0-9]{64}") String termsHash,
    @NotBlank @Pattern(regexp = "GRANT|DECLINE|REVOKE") String decision) {}
