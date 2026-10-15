package io.waterleague.catalog.repository;

import io.waterleague.catalog.entity.Dataset;
import org.springframework.stereotype.Repository;
import java.util.List;

@Repository
public class SourceCatalogRepository implements CatalogRepository {
    @Override
    public List<Dataset> findSources() {
        return List.of(
            new Dataset("buildings", "GIS 건물통합정보", "국토교통부", "NOT_ACQUIRED", "https://www.data.go.kr/data/15123970/openapi.do", "원본·이용조건·형상 확인 필요"),
            new Dataset("land-cover", "토지피복 원자료", "환경공간정보서비스", "NOT_ACQUIRED", "https://egisapp.me.go.kr/", "제작 연도·불투수면·원자료 확인 필요"),
            new Dataset("rainfall", "ASOS 관측 강우", "기상청", "NOT_ACQUIRED", "https://data.kma.go.kr/data/grnd/selectAsosRltmList.do?pgmNo=36&tabNo=2", "분자료·품질·관측소 대표성 확인 필요"),
            new Dataset("elevation", "수치표고모델", "국토지리정보원", "NOT_ACQUIRED", "https://www.ngii.go.kr/nlsc/nsoutput/ouputintro3", "표고·경사·수직 기준 확인 필요"));
    }
}
