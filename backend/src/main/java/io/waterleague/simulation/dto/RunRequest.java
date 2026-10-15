package io.waterleague.simulation.dto;

import jakarta.validation.constraints.NotNull;
import java.util.UUID;

public record RunRequest(@NotNull UUID versionId, @NotNull UUID requestKey) {}
