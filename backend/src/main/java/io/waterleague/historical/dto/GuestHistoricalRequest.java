package io.waterleague.historical.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.*;

public record GuestHistoricalRequest(
    @NotNull UUID requestKey,
    @NotBlank @Pattern(regexp = "seoul-[0-9]{8}") String eventId,
    @NotBlank @Pattern(regexp = "[0-9]{7}") String districtId,
    @NotNull @Size(min = 1, max = 50) List<@NotNull @Valid Item> placements) {
  public record Item(
      @NotBlank @Pattern(regexp = "[0-9]{7}") String districtId,
      @NotNull @Valid HistoricalRequest.Item placement) {}
}
