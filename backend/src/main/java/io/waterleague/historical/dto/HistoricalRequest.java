package io.waterleague.historical.dto;

import io.waterleague.strategy.entity.FacilityType;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;

public record HistoricalRequest(
    @NotNull UUID requestKey,
    @NotBlank @Pattern(regexp = "11[0-9]{3}") String districtId,
    @NotBlank @Pattern(regexp = "[a-f0-9]{64}") String modelHash,
    @NotNull @Size(min = 1, max = 50) List<@Valid Item> placements,
    @Pattern(regexp = "C[a-f0-9]{24}") String sensitivityCellId,
    @Pattern(regexp = "INSTALLATION_TIME_EXPERIMENT_V1") String temporalPolicy,
    UUID parentExperimentId,
    @Positive Long designRevision,
    @Pattern(regexp = "seoul-[0-9]{8}") String eventId,
    @Pattern(regexp = "C[a-f0-9]{24}") String pavementComparisonCellId) {
  public HistoricalRequest(
      UUID requestKey,
      String districtId,
      String modelHash,
      List<Item> placements,
      String sensitivityCellId,
      String temporalPolicy,
      UUID parentExperimentId,
      Long designRevision,
      String eventId) {
    this(
        requestKey,
        districtId,
        modelHash,
        placements,
        sensitivityCellId,
        temporalPolicy,
        parentExperimentId,
        designRevision,
        eventId,
        null);
  }

  public HistoricalRequest(
      UUID requestKey,
      String districtId,
      String modelHash,
      List<Item> placements,
      String sensitivityCellId,
      String temporalPolicy,
      UUID parentExperimentId) {
    this(
        requestKey,
        districtId,
        modelHash,
        placements,
        sensitivityCellId,
        temporalPolicy,
        parentExperimentId,
        null,
        null);
  }

  public HistoricalRequest(
      UUID requestKey,
      String districtId,
      String modelHash,
      List<Item> placements,
      String sensitivityCellId) {
    this(requestKey, districtId, modelHash, placements, sensitivityCellId, null, null);
  }

  public HistoricalRequest(
      UUID requestKey, String districtId, String modelHash, List<Item> placements) {
    this(requestKey, districtId, modelHash, placements, null);
  }

  public record Item(
      @NotBlank @Pattern(regexp = "C[a-f0-9]{24}") String cellId,
      @NotNull FacilityType facilityType,
      @NotNull @DecimalMin("0.01") @Digits(integer = 10, fraction = 2) BigDecimal areaM2,
      Instant installedAt,
      @Pattern(regexp = "[a-f0-9]{64}") String siteModelHash) {
    public Item(String cellId, FacilityType facilityType, BigDecimal areaM2, Instant installedAt) {
      this(cellId, facilityType, areaM2, installedAt, null);
    }

    public Item(String cellId, FacilityType facilityType, BigDecimal areaM2) {
      this(cellId, facilityType, areaM2, null);
    }
  }
}
