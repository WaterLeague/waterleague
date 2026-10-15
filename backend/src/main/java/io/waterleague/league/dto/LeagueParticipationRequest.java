package io.waterleague.league.dto;

import io.waterleague.league.entity.LeagueParticipationRules.*;
import jakarta.validation.constraints.*;

public record LeagueParticipationRequest(
    @NotNull Access access,
    @NotNull Admission admission,
    @NotNull EntryMode entryMode,
    @Min(2) @Max(10) Integer teamSizeLimit) {}
