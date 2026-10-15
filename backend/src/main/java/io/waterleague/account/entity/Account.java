package io.waterleague.account.entity;

import java.util.UUID;

public record Account(
    UUID id,
    String username,
    String displayName,
    String passwordHash,
    String role,
    UUID organizationId,
    boolean enabled) {}
