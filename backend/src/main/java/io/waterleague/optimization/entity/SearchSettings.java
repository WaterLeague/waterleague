package io.waterleague.optimization.entity;

import java.math.BigDecimal;

public record SearchSettings(int topK, BigDecimal budgetKrw, long seed, int candidatesPerArm) {}
