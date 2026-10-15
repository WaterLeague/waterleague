package io.waterleague.utilization.view;

import java.util.List;
import java.util.UUID;

public record CursorPage<T>(List<T> items, UUID nextCursor) {}
