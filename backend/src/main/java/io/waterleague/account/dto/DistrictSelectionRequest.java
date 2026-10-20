package io.waterleague.account.dto;

import jakarta.validation.constraints.*;

public record DistrictSelectionRequest(
    @NotBlank @Pattern(regexp = "11[0-9]{3}") String districtId,
    @NotNull @Pattern(regexp = "RESIDENT|AFFILIATED") String affiliationType) {}
