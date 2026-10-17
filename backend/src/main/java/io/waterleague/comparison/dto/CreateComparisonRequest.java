package io.waterleague.comparison.dto;

import jakarta.validation.constraints.*;
import java.util.List;
import java.util.UUID;

public record CreateComparisonRequest(
    @NotNull UUID sourceVersionId,
    @NotNull @Size(min = 2, max = 3)
        List<@NotBlank @Pattern(regexp = "[a-f0-9]{64}") String> modelHashes,
    @NotNull UUID requestKey) {}
