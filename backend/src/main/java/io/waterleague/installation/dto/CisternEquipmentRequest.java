package io.waterleague.installation.dto;

import jakarta.validation.constraints.*;
import java.math.BigDecimal;

public record CisternEquipmentRequest(
    @NotBlank @Pattern(regexp = "[A-Z0-9_]{1,80}") String specificationId,
    @NotBlank @Pattern(regexp = "[a-f0-9]{64}") String catalogSha256,
    @NotNull @DecimalMin("-100000") @DecimalMax("100000") @Digits(integer = 6, fraction = 3)
        BigDecimal offsetXM,
    @NotNull @DecimalMin("-100000") @DecimalMax("100000") @Digits(integer = 6, fraction = 3)
        BigDecimal offsetYM,
    @NotNull
        @DecimalMin("0")
        @DecimalMax(value = "360", inclusive = false)
        @Digits(integer = 3, fraction = 2)
        BigDecimal rotationDeg) {}
