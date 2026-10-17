package io.waterleague.sharedresearch.dto;

import jakarta.validation.constraints.NotNull;

public record SharedConsentRequest(@NotNull Boolean granted) {}
