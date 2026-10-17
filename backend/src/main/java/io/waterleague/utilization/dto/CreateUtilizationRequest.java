package io.waterleague.utilization.dto;

import jakarta.validation.constraints.*;
import java.util.UUID;

public record CreateUtilizationRequest(
    @NotNull UUID jobId,
    @NotNull UUID requestKey,
    @NotBlank @Size(min = 2, max = 100) String title,
    @NotBlank @Size(min = 10, max = 2000) String purpose) {}
