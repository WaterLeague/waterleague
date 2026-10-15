package io.waterleague.analysis.dto;

import jakarta.validation.constraints.*;
import java.util.*;

public record PatternAnalysisRequest(
    @NotNull @Size(min = 1, max = 50) List<@NotNull UUID> jobIds, @Min(1) @Max(20) int topK) {}
