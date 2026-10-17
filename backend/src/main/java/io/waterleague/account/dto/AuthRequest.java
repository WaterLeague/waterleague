package io.waterleague.account.dto;

import jakarta.validation.constraints.*;

public record AuthRequest(
    @NotBlank @Pattern(regexp = "[a-z0-9_]{4,32}") String username,
    @NotNull @Size(min = 8, max = 128) String password,
    @Pattern(regexp = "[0-9]{6}") String otp) {}
