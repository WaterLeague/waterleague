package io.waterleague.analysis.dto;

import jakarta.validation.constraints.*;
import java.util.*;

public record CreateResearchComparisonRequest(
    @NotNull UUID sourceJobId,
    @NotNull @Size(min = 2, max = 3)
        List<@NotBlank @Pattern(regexp = "[a-f0-9]{64}") String> modelHashes,
    @NotNull UUID requestKey) {}
