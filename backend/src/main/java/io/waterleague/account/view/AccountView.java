package io.waterleague.account.view;
import java.util.UUID;
public record AccountView(UUID id,String username,String displayName,String role,UUID organizationId) {}
