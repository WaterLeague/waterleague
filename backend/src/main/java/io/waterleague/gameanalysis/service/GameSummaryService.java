package io.waterleague.gameanalysis.service;

import io.waterleague.common.exception.*;
import io.waterleague.common.repository.ExternalRequestStore;
import io.waterleague.common.service.JsonService;
import io.waterleague.gameanalysis.view.GameAnalysisView;
import java.time.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;

@Service
public class GameSummaryService {
  public static final String MODEL = "solar-pro4-260806";
  private static final String PROMPT =
      """
      서울 빗물 전략 게임 운영 기록을 한국어로 요약한다. 제공한 JSON 집계값만 근거로 사용한다.
      점수 보유 기록 수는 최종 평가 완료를 뜻하지 않는다. 대기·보류 수는 전체 기록에서 점수 보유 기록을 뺀 수다.
      평가 그룹은 같은 계산 조건의 개인별 합계 또는 개인 최고 제출이다. 다른 그룹을 합산하거나 그룹 사이의 우열을 정하지 않는다.
      미계산·보류는 0점으로 해석하지 않는다. 음수는 평가체적 증가이고 양수는 감소다. 0은 차이가 없음이다.
      가상 관측·추정 점수·인과관계·침수 피해 저감·시공 권고·개별 회원 평가를 만들지 않는다.
      overview는 핵심 현황 2~3문장, findings는 근거별 관찰 2~4개다. 같은 내용을 반복하지 않는다.
      evidence는 participation, facilities, districts, activity, scores 중 해당 근거다. 입력에 없는 설명·주소·사용자 정보를 만들지 않는다.
      기록의 명칭은 입력의 게임 유형과 통계 설명을 따른다. 시설명은 제공한 한글 이름을 그대로 사용한다.
      내부 필드 이름·영문 코드·그룹 해시를 출력하지 않는다. 선택한 모드와 무관한 주의 문구를 넣지 않는다.
      """;
  private final String key;
  private final JsonService json;
  private final ExternalRequestStore store;
  private final UpstageClient client;

  public record Finding(String text, String evidence) {}

  public record Summary(
      String model,
      Instant generatedAt,
      String snapshotHash,
      String overview,
      List<Finding> findings,
      List<String> cautions) {}

  public GameSummaryService(
      @Value("${waterleague.upstage-key:}") String key,
      JsonService json,
      ExternalRequestStore store,
      UpstageClient client) {
    this.key = key.strip();
    this.json = json;
    this.store = store;
    this.client = client;
  }

  public boolean available() {
    return key.matches("[A-Za-z0-9_.-]{16,512}");
  }

  public Summary summarize(GameAnalysisView snapshot, String expectedHash) {
    if (!snapshot.snapshotHash().equals(expectedHash))
      throw new DomainException(ErrorCode.CONFLICT);
    if (!available()) throw new DomainException(ErrorCode.GAME_SUMMARY_UNAVAILABLE);
    if (snapshot.facts().records() == 0) throw new DomainException(ErrorCode.GAME_SUMMARY_EMPTY);
    var policy = ExternalRequestStore.policy("upstage-game-summary", key, 100, 6_553_600);
    String payload = payload(snapshot);
    if (payload.length() > 32000) throw new DomainException(ErrorCode.REQUEST_TOO_LARGE);
    try {
      var cached =
          store.acquire(
              policy,
              "game-summary-v3\n" + MODEL + "\n" + snapshot.snapshotHash(),
              Duration.ofDays(30),
              UpstageClient.MAXIMUM_RESPONSE,
              () -> {
                try {
                  String raw = client.complete(key, payload);
                  parse(raw);
                  return raw;
                } catch (UpstageClient.Unavailable e) {
                  store.block(policy, e.status, 300);
                  throw e;
                }
              });
      var result = parse(cached.body());
      return new Summary(
          MODEL,
          cached.fetchedAt(),
          snapshot.snapshotHash(),
          result.overview(),
          result.findings(),
          cautions(snapshot));
    } catch (RuntimeException e) {
      throw new DomainException(ErrorCode.GAME_SUMMARY_UNAVAILABLE);
    }
  }

  private Map<String, Object> summaryInput(GameAnalysisView snapshot) {
    var f = snapshot.facts();
    boolean disaster = f.mode().equals("DISASTER");
    var names =
        Map.of(
            "RAIN_GARDEN",
            "빗물정원",
            "GREEN_ROOF",
            "녹화지붕",
            "PERMEABLE_PAVEMENT",
            "투수포장",
            "BIORETENTION",
            "생물저류시설",
            "VEGETATIVE_SWALE",
            "식생수로",
            "INFILTRATION_TRENCH",
            "침투 트렌치",
            "RAINWATER_CISTERN",
            "빗물이용조");
    var input = new LinkedHashMap<String, Object>();
    input.put("게임 유형", disaster ? "재해 모드" : f.mode().equals("WEEKLY") ? "주간 서울 대항전" : "실시간 개최 대회");
    input.put(
        "집계 상태",
        Map.of(
                "IN_PROGRESS",
                "진행 중",
                "PROVISIONAL",
                "최종 계산 중",
                "WITHHELD",
                "비교 보류",
                "FINAL",
                "최종 결과",
                "EMPTY",
                "기록 없음",
                "RECORDED",
                "제출 기록",
                "UPCOMING",
                "개최 예정",
                "CANCELLED",
                "취소")
            .getOrDefault(f.status(), "기록 조회"));
    input.put("참여 플레이어 수", f.participants());
    input.put(disaster ? "전체 제출 건수" : "전체 설치 건수", f.records());
    input.put("점수 보유 기록 수", f.scoredRecords());
    input.put("점수 대기 또는 보류 수", f.records() - f.scoredRecords());
    input.put("시설 통계 설명", disaster ? "모든 제출 설계에 포함된 시설. 같은 시설의 재제출 포함" : "시즌 또는 대회에서 설치한 시설");
    input.put(
        "시설별 구성",
        f.facilities().stream()
            .map(
                m ->
                    Map.of(
                        "시설명",
                        names.getOrDefault(m.key(), m.label()),
                        "시설 수",
                        m.count(),
                        "면적 m²",
                        m.areaM2()))
            .toList());
    input.put(
        "자치구별 시설",
        f.districts().stream()
            .map(m -> Map.of("자치구", m.label(), "시설 수", m.count(), "면적 m²", m.areaM2()))
            .toList());
    input.put(
        "한국 날짜별 활동",
        f.activity().stream().map(m -> Map.of("날짜", m.day(), "건수", m.count())).toList());
    var groups = new ArrayList<Object>();
    for (int i = 0; i < f.scoreGroups().size(); i++) {
      var g = f.scoreGroups().get(i);
      groups.add(
          Map.of(
              "평가 그룹",
              i + 1,
              "플레이어 수",
              g.count(),
              "합계 m³",
              g.totalM3(),
              "최소 m³",
              g.minimumM3(),
              "최대 m³",
              g.maximumM3(),
              "음수 플레이어 수",
              g.negative(),
              "0 플레이어 수",
              g.zero(),
              "양수 플레이어 수",
              g.positive()));
    }
    input.put("같은 평가 조건의 개인 점수 분포", groups);
    return input;
  }

  private String payload(GameAnalysisView snapshot) {
    var text = Map.of("type", "string");
    var finding =
        Map.of(
            "type",
            "object",
            "additionalProperties",
            false,
            "required",
            List.of("text", "evidence"),
            "properties",
            Map.of(
                "text",
                text,
                "evidence",
                Map.of(
                    "type",
                    "string",
                    "enum",
                    List.of("participation", "facilities", "districts", "activity", "scores"))));
    var schema =
        Map.of(
            "type",
            "object",
            "additionalProperties",
            false,
            "required",
            List.of("overview", "findings"),
            "properties",
            Map.of("overview", text, "findings", Map.of("type", "array", "items", finding)));
    return json.write(
        Map.of(
            "model",
            MODEL,
            "messages",
            List.of(
                Map.of("role", "system", "content", PROMPT),
                Map.of("role", "user", "content", json.write(summaryInput(snapshot)))),
            "temperature",
            0.2,
            "max_tokens",
            1600,
            "stream",
            false,
            "response_format",
            Map.of(
                "type",
                "json_schema",
                "json_schema",
                Map.of("name", "game_analysis", "strict", true, "schema", schema))));
  }

  private Summary parse(String raw) {
    if (raw.contains(key)) throw new UpstageClient.Unavailable(0);
    JsonNode root = json.tree(raw);
    if (json.write(root).contains(key)) throw new UpstageClient.Unavailable(0);
    var choice = root.path("choices").path(0);
    if (!root.path("model").asString().equals(MODEL)
        || !choice.path("finish_reason").asString().equals("stop"))
      throw new UpstageClient.Unavailable(0);
    var content = json.tree(choice.path("message").path("content").asString());
    String overview = text(content.path("overview"), 1800);
    if (!content.path("findings").isArray()
        || content.path("findings").size() > 5
        || content.path("findings").size() < 1) throw new UpstageClient.Unavailable(0);
    var findings = new ArrayList<Finding>();
    for (var f : content.path("findings")) {
      String evidence = f.path("evidence").asString();
      if (!Set.of("participation", "facilities", "districts", "activity", "scores")
          .contains(evidence)) throw new UpstageClient.Unavailable(0);
      findings.add(new Finding(text(f.path("text"), 800), evidence));
    }
    return new Summary(MODEL, Instant.EPOCH, "", overview, List.copyOf(findings), List.of());
  }

  private List<String> cautions(GameAnalysisView snapshot) {
    var result = new ArrayList<String>();
    result.add(
        snapshot.facts().mode().equals("DISASTER")
            ? "시설 통계는 재제출을 포함한 모든 제출 설계의 합이며, 점수 분포는 같은 조건의 개인 최고 기록입니다."
            : "점수 기록이 있어도 최신 관측까지 계산이 끝났다는 뜻은 아닙니다. 대기·보류 기록을 0점으로 해석하지 마세요.");
    result.add("점수는 설치 전후 평가체적 차이며 실제 지역 침수 피해 저감량을 뜻하지 않습니다.");
    if (snapshot.facts().scoreGroups().size() > 1)
      result.add("다른 평가 조건의 점수를 합산하거나 그룹 간 순위를 비교하지 않습니다.");
    return List.copyOf(result);
  }

  private String text(JsonNode node, int maximum) {
    if (!node.isString()) throw new UpstageClient.Unavailable(0);
    String value = node.asString().strip();
    if (value.isEmpty()
        || value.length() > maximum
        || value.chars().anyMatch(c -> Character.isISOControl(c) && c != '\n' && c != '\t'))
      throw new UpstageClient.Unavailable(0);
    return value;
  }
}
