package io.waterleague.optimization.dto;

import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.util.*;

public record CreateSearchRequest(
    @NotNull @Size(min = 2, max = 50) List<@NotNull UUID> jobIds,
    @Min(2) @Max(20) int topK,
    @NotNull @DecimalMin("1") @Digits(integer = 12, fraction = 2) BigDecimal budgetKrw,
    @NotNull @Min(0) @Max(2147483647L) Long seed,
    @Min(1) @Max(4) Integer candidatesPerArm,
    @NotNull UUID requestKey) {
  public CreateSearchRequest {
    if (candidatesPerArm == null) candidatesPerArm = 3;
  }
}
