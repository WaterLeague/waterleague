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
    @DecimalMin("0.01") @Digits(integer = 8, fraction = 2) BigDecimal tankAreaM2,
    @DecimalMin("0.001") @DecimalMax("100") @Digits(integer = 3, fraction = 3)
        BigDecimal tankDepthM,
    @Valid @JsonInclude(JsonInclude.Include.NON_NULL) CisternLayoutRequest tankLayout,
    @Valid @JsonInclude(JsonInclude.Include.NON_NULL) CisternEquipmentRequest equipment,
    @Pattern(regexp = "WEEKLY|HISTORICAL") @JsonInclude(JsonInclude.Include.NON_NULL) String mode) {
  public CisternPlanRequest {
    // 기존 주간 초안과 명시적 주간 요청의 입력 해시를 동일하게 유지한다.
    if ("WEEKLY".equals(mode)) mode = null;
  }

  public CisternPlanRequest(
      String districtId,
      String roofCellId,
      String groundCellId,
      String roofModelHash,
      String groundModelHash,
      BigDecimal captureAreaM2,
      BigDecimal tankAreaM2,
      BigDecimal tankDepthM,
      CisternLayoutRequest tankLayout,
      CisternEquipmentRequest equipment) {
    this(
        districtId,
        roofCellId,
        groundCellId,
        roofModelHash,
        groundModelHash,
        captureAreaM2,
        tankAreaM2,
        tankDepthM,
        tankLayout,
        equipment,
        null);
  }

  @AssertTrue(message = "공개 장비와 내부 단면 설계 중 하나만 선택해야 합니다")
  @com.fasterxml.jackson.annotation.JsonIgnore
  public boolean isDesignModeValid() {
    return equipment != null
        ? tankAreaM2 == null && tankDepthM == null && tankLayout == null
        : tankAreaM2 != null && tankDepthM != null;
  }

  public CisternPlanRequest(
      String districtId,
      String roofCellId,
      String groundCellId,
      String roofModelHash,
      String groundModelHash,
      BigDecimal captureAreaM2,
      BigDecimal tankAreaM2,
      BigDecimal tankDepthM,
      CisternLayoutRequest tankLayout) {
    this(
        districtId,
        roofCellId,
        groundCellId,
        roofModelHash,
        groundModelHash,
        captureAreaM2,
        tankAreaM2,
        tankDepthM,
        tankLayout,
        null);
  }

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
        null,
        null);
  }
}
