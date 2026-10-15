package io.waterleague.league.entity;

import java.time.Instant;
import java.util.UUID;

public record LeagueTeam(UUID id, UUID leagueId, UUID captainId, String name, Instant frozenAt) {}
