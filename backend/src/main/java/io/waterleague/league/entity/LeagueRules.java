package io.waterleague.league.entity;

import com.fasterxml.jackson.annotation.JsonInclude;
import io.waterleague.strategy.entity.FacilityType;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record LeagueRules(
    int schemaVersion,
    String modelHash,
    String engineRevision,
    String generatorSha256,
    String scoreRule,
    String currency,
    long budget,
    List<FacilityType> allowedTypes,
    int submissionLimit,
    Instant opensAt,
    Instant closesAt,
    String validationLevel,
    boolean official,
    @JsonInclude(JsonInclude.Include.NON_NULL) Integer placementLimit,
    @JsonInclude(JsonInclude.Include.NON_NULL) BigDecimal areaLimitM2,
    @JsonInclude(JsonInclude.Include.NON_NULL) LeagueAward award,
    @JsonInclude(JsonInclude.Include.NON_NULL) LeagueParticipationRules participation) {}
