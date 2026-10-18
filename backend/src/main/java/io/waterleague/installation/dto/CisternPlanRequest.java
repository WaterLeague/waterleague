package io.waterleague.installation.dto;

import jakarta.validation.constraints.*;
import java.math.BigDecimal;

public record CisternPlanRequest(
    @NotBlank @Pattern(regexp = "[0-9]{7}") String districtId,
    @NotBlank @Pattern(regexp = "R[A-Z0-9-]{1,19}") String roofCellId,
    @NotBlank @Pattern(regexp = "G[A-Z0-9-]{1,19}") String groundCellId,
    @NotBlank @Pattern(regexp = "[a-f0-9]{64}") String roofModelHash,
    @NotBlank @Pattern(regexp = "[a-f0-9]{64}") String groundModelHash,
    @NotNull @DecimalMin("0.01") @Digits(integer = 8, fraction = 2) BigDecimal captureAreaM2,
    @NotNull @DecimalMin("0.01") @Digits(integer = 8, fraction = 2) BigDecimal tankAreaM2,
    @NotNull @DecimalMin("0.001") @DecimalMax("100") @Digits(integer = 3, fraction = 3)
        BigDecimal tankDepthM) {}
