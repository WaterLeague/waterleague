package io.waterleague.league.dto;

import jakarta.validation.constraints.*;
import java.util.UUID;

public final class LeagueParticipationCommands {
  private LeagueParticipationCommands() {}

  public record Code(@NotNull @Pattern(regexp = "[A-Za-z0-9_-]{43}") String code) {}

  public record Join(
      @NotNull @Pattern(regexp = "[a-f0-9]{64}") String rulesHash,
      @Pattern(regexp = "[A-Za-z0-9_-]{43}") String code) {}

  public record Revision(@Min(1) int revision) {}

  public record Decision(
      @Min(1) int revision,
      @NotNull @Pattern(regexp = "APPROVED|REJECTED") String state,
      @NotBlank @Size(max = 500) String reason) {}

  public record Team(@NotBlank @Size(max = 60) String name) {}

  public record TeamJoin(
      @NotNull @Pattern(regexp = "[A-Za-z0-9_-]{43}") String code,
      @NotNull UUID teamId,
      @NotNull @Pattern(regexp = "[a-f0-9]{64}") String rulesHash) {}
}
