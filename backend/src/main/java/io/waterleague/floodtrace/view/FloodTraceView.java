package io.waterleague.floodtrace.view;

import io.waterleague.floodtrace.entity.FloodTraceCatalog;

public record FloodTraceView(String sha256, FloodTraceCatalog catalog) {}
