package io.waterleague.administration.view;

import java.time.Instant;
import java.util.UUID;

public record MemberApplicationView(
    UUID id,
    String username,
    String displayName,
    String memberType,
    String approvalStatus,
    boolean enabled,
    UUID organizationId,
    String organizationName,
    String purpose,
    Instant createdAt) {}
