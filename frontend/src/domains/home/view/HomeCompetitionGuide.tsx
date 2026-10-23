import { HomeGameImage } from './HomeGameImage';

export function HomeCompetitionGuide() {
  return (
    <section
      className="home-competitions"
      id="home-competitions"
      aria-labelledby="home-competitions-title"
    >
      <div className="home-section-heading">
        <span className="home-eyebrow">대회 개최와 분석</span>
        <h2 id="home-competitions-title">직접 여는 대회, 기록으로 살펴보는 결과.</h2>
        <p>
          소속 확인과 관리자 승인을 받은 정부·기관·기업 회원은 조직 명의로 대회를 개최할 수 있어요.
        </p>
      </div>
      <div className="home-story-copy">
        <h3>지역과 예산, 시설과 시상까지 직접 설정하세요.</h3>
        <p>
          실시간·재해 모드, 개최 지역과 기간, 설치 가능 시설을 정하고 1인당 기본 예산 또는 직접
          설정한 금액을 선택해요. 순위별 상 이름과 상금, 시상 안내도 등록할 수 있어요.
        </p>
      </div>
      <div className="home-competition-gallery">
        <HomeGameImage
          src="/home/game/competition-create.png"
          alt="실시간 모드와 1인당 예산, 서울 자치구 지도, 시설과 시상 조건을 설정하는 대회 개최 화면"
          width={2312}
          height={6496}
          caption="대회 개최 · 지역·시설·예산·시상 설정"
        />
        <HomeGameImage
          src="/home/game/competition-detail.png"
          alt="재해 모드 대회의 개최 기간과 서울 전체 지도, 예산, 허용 시설과 순위별 시상 안내 화면"
          width={2312}
          height={2760}
          caption="대회 상세 · 참가 조건과 시상 안내"
        />
      </div>
      <div className="home-competition-analysis home-shared-story">
        <div className="home-story-copy">
          <span className="home-eyebrow">주최 조직과 관리자를 위한 결과 분석</span>
          <h3>시각화로 비교하고, AI 요약으로 읽어보세요.</h3>
          <p>
            참여 현황과 시설별 구성, 구별 설치 분포, 일별 활동, 같은 평가 조건의 점수 분포를
            그래프로 살펴봐요. Upstage LLM이 계정 정보 없는 집계 통계를 바탕으로 대회 현황을
            요약·설명해요.
          </p>
          <p className="home-story-note">
            해당 대회의 승인된 주최 조직과 관리자만 분석을 볼 수 있어요. AI 설명은 계산 결과나
            순위를 변경하지 않아요.
          </p>
        </div>
        <HomeGameImage
          src="/home/game/competition-analysis.png"
          alt="대회 결과의 Upstage AI 요약과 참여 현황, 시설별 구성, 구별 설치 분포, 일별 설치 추이 그래프"
          width={2362}
          height={8330}
          caption="대회 결과 · AI 요약과 통계 시각화"
        />
      </div>
      <p className="home-caption">
        화면은 촬영 당시의 기록입니다. 현재 개최 조건과 결과는 각 대회에서 확인하세요.
      </p>
    </section>
  );
}
