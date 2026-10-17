package io.waterleague.account.dto;

import jakarta.validation.constraints.*;

public record DistrictSelectionRequest(
    @NotBlank @Pattern(regexp = "[0-9]{7}") String districtId,
    @NotNull @Pattern(regexp = "RESIDENT|AFFILIATED") String affiliationType) {}
