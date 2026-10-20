package io.waterleague.installation.dto;

import io.waterleague.strategy.entity.FacilityType;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;

public record InstallRequest(
    @NotBlank @Pattern(regexp = "11[0-9]{3}") String districtId,
    @NotBlank @Pattern(regexp = "C[a-f0-9]{24}") String cellId,
    @NotNull FacilityType facilityType,
    @NotNull @DecimalMin("0.01") @Digits(integer = 8, fraction = 2) BigDecimal areaM2) {}
