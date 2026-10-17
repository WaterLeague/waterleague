package io.waterleague.administration.dto;

import jakarta.validation.constraints.*;
import java.util.UUID;

public record ReviewRequest(
    @NotNull @Pattern(regexp = "APPROVE|REJECT|SUSPEND") String decision,
    @NotNull @Pattern(regexp = "PENDING|APPROVED|REJECTED|SUSPENDED") String expectedStatus,
    @NotBlank @Size(max = 1000) String reason,
    UUID organizationId) {}
