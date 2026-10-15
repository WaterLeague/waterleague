package io.waterleague.catalog.view;
import java.util.List;
public record CatalogView(String phase, boolean officialEvaluationAvailable, List<SourceView> sources) {
    public record SourceView(String id, String title, String provider, String status, String url, String note) { }
}
