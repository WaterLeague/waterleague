package io.waterleague.league.dto;

import jakarta.validation.constraints.*;

public record LeagueAwardRequest(
    @Min(0) @Max(1000000000) long prizeKrw,
    @Min(0) @Max(1000) int winnerCount,
    @NotNull @Size(max = 2000) String notice) {}
