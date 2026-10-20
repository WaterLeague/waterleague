package io.waterleague.historical.dto;

import io.waterleague.strategy.entity.FacilityType;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;

public record HistoricalDesignRequest(
    @NotNull UUID requestKey,
    @PositiveOrZero long baseRevision,
    @PositiveOrZero int elapsedSeconds,
    @NotNull @Size(max = 50) List<@NotNull @Valid Item> placements) {
  public record Item(
      @NotNull UUID id,
      @NotBlank @Pattern(regexp = "11[0-9]{3}") String districtId,
      @NotBlank @Pattern(regexp = "C[a-f0-9]{24}") String cellId,
      @NotNull FacilityType facilityType,
      @NotNull @DecimalMin("0.01") @Digits(integer = 10, fraction = 2) BigDecimal areaM2,
      @NotNull Instant installedAt) {}
}
