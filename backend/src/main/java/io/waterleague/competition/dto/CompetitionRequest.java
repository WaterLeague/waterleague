package io.waterleague.competition.dto;

import io.waterleague.strategy.entity.FacilityType;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.time.Instant;
import java.util.*;

public record CompetitionRequest(
    @NotNull UUID requestKey,
    @NotBlank @Size(max = 100) String title,
    @NotBlank @Size(max = 4000) String description,
    @NotNull @Pattern(regexp = "REALTIME|DISASTER") String mode,
    @Size(max = 32) String eventId,
    @NotEmpty @Size(max = 25) Set<@NotBlank String> districtIds,
    @NotEmpty @Size(max = 7) Set<@NotNull FacilityType> allowedTypes,
    @NotNull Instant opensAt,
    @NotNull Instant closesAt,
    @NotNull @Size(max = 20) List<@NotNull @Valid Award> awards,
    @NotNull @Size(max = 2000) String awardNotice,
    @Pattern(regexp = "DEFAULT|CUSTOM") String budgetMode,
    @DecimalMin("1") @DecimalMax("1000000000000") @Digits(integer = 13, fraction = 0)
        java.math.BigDecimal personalBudgetKrw) {
  public record Award(
      @NotBlank @Size(max = 80) String title,
      @Min(1) @Max(1000) int rankFrom,
      @Min(1) @Max(1000) int rankTo,
      @Min(0) @Max(1000000000) long prizeKrw) {}
}
