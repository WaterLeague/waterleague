package io.waterleague.watershed.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.util.*;

public record WatershedRequest(
    @NotNull UUID requestKey,
    @NotBlank @Pattern(regexp = "[a-f0-9]{64}") String catalogHash,
    @NotNull @Size(max = 20) List<@NotNull @Valid Item> placements,
    @Pattern(regexp = "[a-f0-9]{64}") String costCatalogHash,
    @Valid StorageRequest storage) {
  public WatershedRequest(UUID requestKey, String catalogHash, List<Item> placements) {
    this(requestKey, catalogHash, placements, null, null);
  }

  public WatershedRequest(
      UUID requestKey, String catalogHash, List<Item> placements, String costCatalogHash) {
    this(requestKey, catalogHash, placements, costCatalogHash, null);
  }

  public record StorageRequest(
      @NotBlank @Pattern(regexp = "[a-f0-9]{64}") String catalogHash,
      @NotNull @Size(min = 1, max = 20) List<@NotNull @Valid StorageItem> placements) {}

  public record StorageItem(
      @NotBlank @Pattern(regexp = "[A-Za-z][A-Za-z0-9_-]{0,23}") String id,
      @NotBlank @Size(max = 40) String connectionId,
      @NotNull @DecimalMin("0.01") @DecimalMax("1000000") @Digits(integer = 7, fraction = 2)
          BigDecimal areaM2,
      @NotNull @DecimalMin("-1000") @DecimalMax("10000") @Digits(integer = 5, fraction = 3)
          BigDecimal invertM,
      @NotNull @DecimalMin("0.001") @DecimalMax("100") @Digits(integer = 3, fraction = 3)
          BigDecimal depthM,
      @NotNull @DecimalMin("0") @DecimalMax("100") @Digits(integer = 3, fraction = 3)
          BigDecimal initialDepthM,
      @NotNull @Valid Port inlet,
      @NotNull @Valid Port drain,
      @NotNull @Valid Port overflow) {}

  public record Port(
      @NotNull @DecimalMin("-1000") @DecimalMax("10000") @Digits(integer = 5, fraction = 3)
          BigDecimal crestM,
      @NotNull @DecimalMin("0.001") @DecimalMax("100") @Digits(integer = 3, fraction = 3)
          BigDecimal diameterM,
      @NotNull @DecimalMin("0.001") @DecimalMax("1") @Digits(integer = 1, fraction = 3)
          BigDecimal dischargeCoefficient,
      @NotNull Boolean flapGate) {}

  public record Item(
      @NotBlank @Pattern(regexp = "[A-Za-z][A-Za-z0-9_-]{0,23}") String id,
      @NotBlank @Size(max = 20) String catchmentId,
      @NotBlank @Size(max = 40) String facilityType,
      @NotNull @DecimalMin("0.01") @DecimalMax("1000000") @Digits(integer = 7, fraction = 2)
          BigDecimal areaM2,
      @NotNull @DecimalMin("0") @DecimalMax("1000000") @Digits(integer = 7, fraction = 2)
          BigDecimal treatedImperviousM2) {}
}
