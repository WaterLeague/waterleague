package io.waterleague.installation.dto;

import jakarta.validation.constraints.*;
import java.math.BigDecimal;

public record CisternLayoutRequest(
    @NotNull @DecimalMin("0.01") @DecimalMax("10000") @Digits(integer = 5, fraction = 2)
        BigDecimal widthM,
    @NotNull @DecimalMin("0.001") @DecimalMax("10") @Digits(integer = 2, fraction = 3)
        BigDecimal wallThicknessM,
    @NotNull @DecimalMin("-100000") @DecimalMax("100000") @Digits(integer = 6, fraction = 3)
        BigDecimal offsetXM,
    @NotNull @DecimalMin("-100000") @DecimalMax("100000") @Digits(integer = 6, fraction = 3)
        BigDecimal offsetYM,
    @NotNull
        @DecimalMin("0")
        @DecimalMax(value = "360", inclusive = false)
        @Digits(integer = 3, fraction = 2)
        BigDecimal rotationDeg) {}
