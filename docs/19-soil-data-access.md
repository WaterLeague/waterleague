# 성수 토양 자료 접근 점검

2026-10-16. 기존 `.env.local`의 브이월드 키로 공식 WFS GetCapabilities의 188개 레이어를 확인한 뒤, 공개된 2D 데이터 API 2.0의 토양 관련 레이어를 고정 성수 bbox에서 조회. 추가 인증키 발급·권한 신청 없이 성공.

| 공식 레이어 | 제공 항목 | 고정 성수 영역 조회 |
| --- | --- | --- |
| `LT_C_ASITSOILDRA` | 배수등급 코드·설명·도형 | MultiPolygon 2개 / 전체 2개 |
| `LT_C_ASITSOILDEP` | 유효토심 코드·설명·도형 | MultiPolygon 1개 / 전체 1개 |
| `LT_C_ASITDEEPSOIL` | 심토토성 코드·설명·도형 | MultiPolygon 2개 / 전체 2개 |
| `LT_C_GIMSSCS` | 별도 토양도 레이어 | 해당 bbox `NOT_FOUND`, 0개 |

bbox `[127.0525,37.5430,127.0555,37.5455]`, EPSG:4326. 토양도 한 레이어의 미반환을 해당 지역 토양 자료 전체 부재로 해석하지 않음. API 검색 영역의 교차 도형 수이며 토양 관측점·현장 조사 건수가 아님.

## 이용·모델 편입 경계

공식 배수등급 레퍼런스는 제공처 국립농업과학원, 페이지 갱신일 2022-07-10을 표시. 실제 토양 조사일·변경 이력·축척·2024년 시점의 부지 상태는 이 표시로 확정되지 않음. 배수등급·토성·유효토심은 포화수리전도도나 SWMM 침투 매개변수의 실측값이 아니며, 등급을 임의 계수로 치환하지 않음.

공식 이용약관 19조의 사전 승낙 없는 복사·가공·제공·저장 제한 확인. 이번 점검은 메모리에서 검사 후 건수·필드명·형상 유형·접근 시각만 보존. 인증 URL·키·도형 좌표·속성값 원본 미보관. 공개 코드나 연구 ZIP에 원자료 포함 없음. 연구 모델도 변경하지 않음.

필요한 다음 근거: 원본 제공·재현 묶음 포함 이용허락, 조사일·CRS·축척·범례, 후보 셀/실제 유역과 도형의 정합, 도시 포장·다짐·성토·지하수 및 현장 침투 측정. 흙토람 원본 분양 또는 제공기관 확인 절차와 함께 처리. 관련 기관에 신청·문의 발송은 별도 사용자 지시 필요.

## 재점검

```sh
simulation/.venv/bin/python scripts/probe_vworld_soil.py
```

결과 `data/manifests/vworld-soil-access-audit.json`: 공간 원본 스냅샷이 아닌 접근 점검 기록. 실시간 API 결과는 변할 수 있으므로 이 파일의 건수만으로 후속 모델 재현을 보장하지 않음.

출처: [배수등급 레퍼런스](https://www.vworld.kr/dev/v4dv_2ddataguide2_s002.do?svcIde=asitsoildra&apiVer=2), [유효토심](https://www.vworld.kr/dev/v4dv_2ddataguide2_s002.do?svcIde=asitsoildep&apiVer=2), [심토토성](https://www.vworld.kr/dev/v4dv_2ddataguide2_s002.do?svcIde=asitdeepsoil&apiVer=2), [브이월드 이용약관](https://www.vworld.kr/v4po_prcint_a001.do).
