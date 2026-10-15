package io.waterleague.catalog.mapper;
import io.waterleague.catalog.entity.Dataset;
import io.waterleague.catalog.view.CatalogView.SourceView;
import org.springframework.stereotype.Component;
@Component
public class CatalogMapper {
    public SourceView toView(Dataset source) {
        return new SourceView(source.id(), source.title(), source.provider(), source.status(), source.url(), source.note());
    }
}
