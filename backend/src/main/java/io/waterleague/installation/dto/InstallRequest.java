package io.waterleague.installation.dto;

import io.waterleague.strategy.entity.FacilityType;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;

public record InstallRequest(
    @NotBlank @Pattern(regexp = "[0-9]{7}") String districtId,
    @NotBlank @Pattern(regexp = "[RG][0-9]{1,3}") String cellId,
    @NotNull FacilityType facilityType,
    @NotNull @DecimalMin("0.01") @Digits(integer = 8, fraction = 2) BigDecimal areaM2) {}
