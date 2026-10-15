package io.waterleague.strategy.dto;

import io.waterleague.strategy.entity.Placement;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.List;

public record SaveStrategyRequest(
    @NotBlank @Size(max = 80) String title,
    @NotBlank @Pattern(regexp = "[a-f0-9]{64}") String modelHash,
    @NotNull @Size(max = 50) List<@Valid Placement> placements,
    @NotNull @Size(max = 2000) String designNote,
    @Min(0) int baseRevision) {}
