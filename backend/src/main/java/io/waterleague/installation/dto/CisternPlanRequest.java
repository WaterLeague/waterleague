package io.waterleague.installation.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;

public record CisternPlanRequest(
    @NotBlank @Pattern(regexp = "11[0-9]{3}") String districtId,
    @NotBlank @Pattern(regexp = "C[a-f0-9]{24}") String roofCellId,
    @NotBlank @Pattern(regexp = "C[a-f0-9]{24}") String groundCellId,
    @NotBlank @Pattern(regexp = "[a-f0-9]{64}") String roofModelHash,
    @NotBlank @Pattern(regexp = "[a-f0-9]{64}") String groundModelHash,
    @NotNull @DecimalMin("0.01") @Digits(integer = 8, fraction = 2) BigDecimal captureAreaM2,
    @NotNull @DecimalMin("0.01") @Digits(integer = 8, fraction = 2) BigDecimal tankAreaM2,
    @NotNull @DecimalMin("0.001") @DecimalMax("100") @Digits(integer = 3, fraction = 3)
        BigDecimal tankDepthM,
    @Valid @JsonInclude(JsonInclude.Include.NON_NULL) CisternLayoutRequest tankLayout) {
  public CisternPlanRequest(
      String districtId,
      String roofCellId,
      String groundCellId,
      String roofModelHash,
      String groundModelHash,
      BigDecimal captureAreaM2,
      BigDecimal tankAreaM2,
      BigDecimal tankDepthM) {
    this(
        districtId,
        roofCellId,
        groundCellId,
        roofModelHash,
        groundModelHash,
        captureAreaM2,
        tankAreaM2,
        tankDepthM,
        null);
  }
}
