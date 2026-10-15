package io.waterleague.account.dto;

import io.waterleague.account.entity.MemberType;
import jakarta.validation.constraints.*;

public record RegistrationRequest(
    @NotBlank @Pattern(regexp = "[a-z0-9_]{4,32}") String username,
    @NotNull @Size(min = 12, max = 128) String password,
    @NotNull MemberType memberType,
    @NotNull @Size(max = 100) String organizationName,
    @NotNull @Size(max = 2000) String purpose) {}
