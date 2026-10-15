package io.waterleague.league.dto;

import io.waterleague.strategy.entity.FacilityType;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Set;

public record LeagueDraftRequest(
    @NotBlank @Pattern(regexp = "[a-f0-9]{64}") String modelHash,
    @Min(0) int baseRevision,
    @NotBlank @Size(max = 100) String title,
    @NotBlank @Size(max = 2000) String question,
    @NotNull Instant opensAt,
    @NotNull Instant closesAt,
    @NotNull @Min(1) @Max(300000000) Long budget,
    @NotEmpty @Size(max = 3) Set<@NotNull FacilityType> allowedTypes,
    @Min(1) @Max(100) int submissionLimit,
    @Min(1) @Max(1000) Integer placementLimit,
    @DecimalMin("0.01") @DecimalMax("1000000") @Digits(integer = 7, fraction = 2)
        BigDecimal areaLimitM2,
    @Valid LeagueAwardRequest award,
    @Valid LeagueParticipationRequest participation) {}
