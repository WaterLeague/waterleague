package io.waterleague.account.entity;

import java.util.UUID;

public record Account(
    UUID id,
    String username,
    String displayName,
    String passwordHash,
    String role,
    String memberType,
    String approvalStatus,
    UUID organizationId,
    String organizationName,
    String applicationPurpose,
    boolean enabled) {
  public boolean usable() {
    return enabled && approvalStatus.equals("APPROVED");
  }

  public boolean organizationMember() {
    return role.equals("MEMBER")
        && java.util.Set.of("BUSINESS", "INSTITUTION", "GOVERNMENT").contains(memberType);
  }

  public boolean requiresMfa() {
    return role.equals("ADMIN") || organizationMember();
  }
}
