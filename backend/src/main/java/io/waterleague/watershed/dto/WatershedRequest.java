package io.waterleague.watershed.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.util.*;

public record WatershedRequest(
    @NotNull UUID requestKey,
    @NotBlank @Pattern(regexp = "[a-f0-9]{64}") String catalogHash,
    @NotNull @Size(min = 1, max = 20) List<@NotNull @Valid Item> placements,
    @Pattern(regexp = "[a-f0-9]{64}") String costCatalogHash) {
  public WatershedRequest(UUID requestKey, String catalogHash, List<Item> placements) {
    this(requestKey, catalogHash, placements, null);
  }

  public record Item(
      @NotBlank @Pattern(regexp = "[A-Za-z][A-Za-z0-9_-]{0,23}") String id,
      @NotBlank @Size(max = 20) String catchmentId,
      @NotBlank @Size(max = 40) String facilityType,
      @NotNull @DecimalMin("0.01") @DecimalMax("1000000") @Digits(integer = 7, fraction = 2)
          BigDecimal areaM2,
      @NotNull @DecimalMin("0") @DecimalMax("1000000") @Digits(integer = 7, fraction = 2)
          BigDecimal treatedImperviousM2) {}
}
