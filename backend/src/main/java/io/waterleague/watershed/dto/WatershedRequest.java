package io.waterleague.watershed.dto;

import com.fasterxml.jackson.annotation.JsonIgnore;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.util.*;

public record WatershedRequest(
    @NotNull UUID requestKey,
    @NotBlank @Pattern(regexp = "[a-f0-9]{64}") String catalogHash,
    @NotNull @Size(max = 20) List<@NotNull @Valid Item> placements,
    @Pattern(regexp = "[a-f0-9]{64}") String costCatalogHash,
    @Valid StorageRequest storage,
    @Valid ConduitRequest conduits,
    @Pattern(regexp = "[a-f0-9]{64}") String cisternCostCatalogHash,
    @Valid PumpRequest pumps,
    @Valid CisternRequest cistern,
    @Pattern(regexp = "[a-f0-9]{64}") String georeferenceHash,
    @Pattern(regexp = "[a-f0-9]{64}") String surfaceProfileHash) {
  public WatershedRequest(
      UUID requestKey,
      String catalogHash,
      List<Item> placements,
      String costCatalogHash,
      StorageRequest storage,
      ConduitRequest conduits,
      String cisternCostCatalogHash,
      PumpRequest pumps,
      CisternRequest cistern,
      String georeferenceHash) {
    this(
        requestKey,
        catalogHash,
        placements,
        costCatalogHash,
        storage,
        conduits,
        cisternCostCatalogHash,
        pumps,
        cistern,
        georeferenceHash,
        null);
  }

  public WatershedRequest(
      UUID requestKey,
      String catalogHash,
      List<Item> placements,
      String costCatalogHash,
      StorageRequest storage,
      ConduitRequest conduits,
      String cisternCostCatalogHash,
      PumpRequest pumps,
      CisternRequest cistern) {
    this(
        requestKey,
        catalogHash,
        placements,
        costCatalogHash,
        storage,
        conduits,
        cisternCostCatalogHash,
        pumps,
        cistern,
        null);
  }

  public WatershedRequest(
      UUID requestKey,
      String catalogHash,
      List<Item> placements,
      String costCatalogHash,
      StorageRequest storage,
      ConduitRequest conduits,
      String cisternCostCatalogHash,
      PumpRequest pumps) {
    this(
        requestKey,
        catalogHash,
        placements,
        costCatalogHash,
        storage,
        conduits,
        cisternCostCatalogHash,
        pumps,
        null);
  }

  public record CisternRequest(
      @NotBlank @Pattern(regexp = "[a-f0-9]{64}") String catalogHash,
      @NotNull @Valid CisternItem placement) {}

  public record CisternItem(
      @NotBlank @Pattern(regexp = "[A-Za-z][A-Za-z0-9_-]{0,23}") String id,
      @NotBlank @Size(max = 40) String catchmentId,
      @NotNull @DecimalMin("0.01") @DecimalMax("1000000") @Digits(integer = 7, fraction = 2)
          BigDecimal captureAreaM2,
      @NotNull @DecimalMin("0.01") @DecimalMax("1000000") @Digits(integer = 7, fraction = 2)
          BigDecimal areaM2,
      @NotNull @DecimalMin("-1000") @DecimalMax("10000") @Digits(integer = 5, fraction = 3)
          BigDecimal invertM,
      @NotNull @DecimalMin("0.001") @DecimalMax("100") @Digits(integer = 3, fraction = 3)
          BigDecimal depthM,
      @NotNull @DecimalMin("0") @DecimalMax("100") @Digits(integer = 3, fraction = 3)
          BigDecimal initialDepthM,
      @Valid Port drain,
      @NotNull @Valid Port overflow,
      Boolean drainClosed,
      @Valid CisternPipe inletPipe,
      @Valid CisternPipe drainPipe,
      @Valid CisternPipe overflowPipe) {
    public CisternItem(
        String id,
        String catchmentId,
        BigDecimal captureAreaM2,
        BigDecimal areaM2,
        BigDecimal invertM,
        BigDecimal depthM,
        BigDecimal initialDepthM,
        Port drain,
        Port overflow,
        Boolean drainClosed,
        CisternPipe inletPipe) {
      this(
          id,
          catchmentId,
          captureAreaM2,
          areaM2,
          invertM,
          depthM,
          initialDepthM,
          drain,
          overflow,
          drainClosed,
          inletPipe,
          null,
          null);
    }

    public CisternItem(
        String id,
        String catchmentId,
        BigDecimal captureAreaM2,
        BigDecimal areaM2,
        BigDecimal invertM,
        BigDecimal depthM,
        BigDecimal initialDepthM,
        Port drain,
        Port overflow,
        Boolean drainClosed) {
      this(
          id,
          catchmentId,
          captureAreaM2,
          areaM2,
          invertM,
          depthM,
          initialDepthM,
          drain,
          overflow,
          drainClosed,
          null);
    }

    public CisternItem(
        String id,
        String catchmentId,
        BigDecimal captureAreaM2,
        BigDecimal areaM2,
        BigDecimal invertM,
        BigDecimal depthM,
        BigDecimal initialDepthM,
        Port drain,
        Port overflow) {
      this(
          id,
          catchmentId,
          captureAreaM2,
          areaM2,
          invertM,
          depthM,
          initialDepthM,
          drain,
          overflow,
          false);
    }

    @AssertTrue
    @JsonIgnore
    public boolean isDrainConfigurationValid() {
      return Boolean.TRUE.equals(drainClosed) ? drain == null && drainPipe == null : drain != null;
    }
  }

  public record CisternPipe(
      @NotNull @DecimalMin("0.001") @DecimalMax("10000") @Digits(integer = 5, fraction = 3)
          BigDecimal lengthM,
      @NotNull @DecimalMin("0.001") @DecimalMax("100") @Digits(integer = 3, fraction = 3)
          BigDecimal diameterM,
      @NotNull @DecimalMin("0.001") @DecimalMax("1") @Digits(integer = 1, fraction = 3)
          BigDecimal roughness,
      @NotNull @DecimalMin("-1000") @DecimalMax("10000") @Digits(integer = 5, fraction = 3)
          BigDecimal upstreamInvertM,
      @NotNull @DecimalMin("0.001") @DecimalMax("100") @Digits(integer = 3, fraction = 3)
          BigDecimal upstreamMaxDepthM,
      @NotNull @DecimalMin("-1000") @DecimalMax("10000") @Digits(integer = 5, fraction = 3)
          BigDecimal downstreamInvertM) {}

  public WatershedRequest(
      UUID requestKey,
      String catalogHash,
      List<Item> placements,
      String costCatalogHash,
      StorageRequest storage,
      ConduitRequest conduits,
      String cisternCostCatalogHash) {
    this(
        requestKey,
        catalogHash,
        placements,
        costCatalogHash,
        storage,
        conduits,
        cisternCostCatalogHash,
        null);
  }

  public WatershedRequest(UUID requestKey, String catalogHash, List<Item> placements) {
    this(requestKey, catalogHash, placements, null, null, null, null);
  }

  public WatershedRequest(
      UUID requestKey, String catalogHash, List<Item> placements, String costCatalogHash) {
    this(requestKey, catalogHash, placements, costCatalogHash, null, null, null);
  }

  public WatershedRequest(
      UUID requestKey,
      String catalogHash,
      List<Item> placements,
      String costCatalogHash,
      StorageRequest storage) {
    this(requestKey, catalogHash, placements, costCatalogHash, storage, null, null);
  }

  public WatershedRequest(
      UUID requestKey,
      String catalogHash,
      List<Item> placements,
      String costCatalogHash,
      StorageRequest storage,
      ConduitRequest conduits) {
    this(requestKey, catalogHash, placements, costCatalogHash, storage, conduits, null);
  }

  public record ConduitRequest(
      @NotBlank @Pattern(regexp = "[a-f0-9]{64}") String catalogHash,
      @NotNull @Size(min = 1, max = 20) List<@NotNull @Valid ConduitItem> placements) {}

  public record PumpRequest(
      @NotBlank @Pattern(regexp = "[a-f0-9]{64}") String catalogHash,
      @NotNull @Size(min = 1, max = 20) List<@NotNull @Valid PumpItem> placements) {}

  public record PumpItem(
      @NotBlank @Pattern(regexp = "[A-Za-z][A-Za-z0-9_-]{0,23}") String id,
      @NotBlank @Size(max = 40) String fromNode,
      @NotBlank @Size(max = 40) String toNode,
      @NotNull @DecimalMin("0.001") @DecimalMax("100") @Digits(integer = 3, fraction = 3)
          BigDecimal startDepthM,
      @NotNull @DecimalMin("0.001") @DecimalMax("100") @Digits(integer = 3, fraction = 3)
          BigDecimal stopDepthM,
      @NotBlank @Pattern(regexp = "ON|OFF") String initialStatus,
      @NotNull @Valid PumpDelivery delivery) {}

  public record PumpDelivery(
      @NotNull @DecimalMin("0.001") @DecimalMax("10000") @Digits(integer = 5, fraction = 3)
          BigDecimal lengthM,
      @NotNull @DecimalMin("0.001") @DecimalMax("20") @Digits(integer = 2, fraction = 3)
          BigDecimal diameterM,
      @NotNull @DecimalMin("0.001") @DecimalMax("100") @Digits(integer = 3, fraction = 3)
          BigDecimal roughnessMm,
      @NotNull @DecimalMin("0.001") @DecimalMax("1000") @Digits(integer = 4, fraction = 3)
          BigDecimal pressureHeadLimitM,
      @NotNull @DecimalMin("0") @DecimalMax("100") @Digits(integer = 3, fraction = 3)
          BigDecimal entranceLoss,
      @NotNull @DecimalMin("0") @DecimalMax("100") @Digits(integer = 3, fraction = 3)
          BigDecimal exitLoss,
      @NotNull @DecimalMin("0") @DecimalMax("100") @Digits(integer = 3, fraction = 3)
          BigDecimal averageLoss,
      @NotNull Boolean checkValve) {}

  public record ConduitItem(
      @NotBlank @Pattern(regexp = "[A-Za-z][A-Za-z0-9_-]{0,23}") String id,
      @NotBlank @Size(max = 40) String conduitId,
      @NotBlank @Pattern(regexp = "CIRCULAR|RECT_CLOSED") String shape,
      @NotNull @DecimalMin("0.01") @DecimalMax("100") @Digits(integer = 3, fraction = 3)
          BigDecimal fullDepthM,
      @DecimalMin("0.01") @DecimalMax("100") @Digits(integer = 3, fraction = 3) BigDecimal widthM,
      @NotNull @Min(1) @Max(20) Integer barrels,
      @NotNull @DecimalMin("0.001") @DecimalMax("1") @Digits(integer = 1, fraction = 4)
          BigDecimal roughness) {}

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
