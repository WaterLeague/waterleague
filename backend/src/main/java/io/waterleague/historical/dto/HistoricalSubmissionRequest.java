package io.waterleague.historical.dto;

import io.waterleague.strategy.entity.FacilityType;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;

public record HistoricalSubmissionRequest(
    @NotNull UUID requestKey,
    @NotBlank @Pattern(regexp = "seoul-[0-9]{8}") String eventId,
    @NotNull @Size(min = 1, max = 50) List<@Valid Item> placements) {
  public record Item(
      @NotBlank @Pattern(regexp = "[0-9]{7}") String districtId,
      @NotBlank @Size(max = 20) String cellId,
      @NotNull FacilityType facilityType,
      @NotNull @DecimalMin("0.01") @Digits(integer = 10, fraction = 2) BigDecimal areaM2,
      @NotNull Instant installedAt,
      UUID experimentId) {}
}
