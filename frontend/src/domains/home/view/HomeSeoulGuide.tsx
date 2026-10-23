import { useState } from 'react';
import { Moon, Sun } from 'lucide-react';
import { HomeGameImage } from './HomeGameImage';

export function HomeSeoulGuide() {
  const [night, setNight] = useState(false);
  return (
    <section className="home-seoul" id="home-seoul" aria-labelledby="home-seoul-title">
      <div className="home-section-heading">
        <span className="home-eyebrow">게임 속 서울</span>
        <h2 id="home-seoul-title">한강에서 골목까지, 서울을 입체로.</h2>
        <p>건물과 도로, 한강과 교량까지. 공개 지형자료로 만든 서울을 2D·3D 지도로 둘러보세요.</p>
      </div>
      <div className={`home-seoul-view${night ? ' is-night' : ''}`}>
        <div className="home-seoul-toolbar">
          <span>실제 게임 지도</span>
          <div className="home-daynight" role="group" aria-label="서울 지도 낮과 밤 선택">
            <button type="button" aria-pressed={!night} onClick={() => setNight(false)}>
              <Sun size={16} aria-hidden="true" /> 낮
            </button>
            <button type="button" aria-pressed={night} onClick={() => setNight(true)}>
              <Moon size={16} aria-hidden="true" /> 밤
            </button>
          </div>
        </div>
        <HomeGameImage
          src={`/home/game/seoul-hangang-${night ? 'night' : 'day'}.jpg`}
          alt={`한강대교와 노들섬, 강 양쪽의 서울 건물이 보이는 실제 게임 ${night ? '밤' : '낮'} 지도`}
          width={1600}
          height={900}
          caption={`한강과 서울의 ${night ? '밤' : '낮'} · 같은 위치에서 촬영한 게임 화면`}
        />
      </div>
      <div className="home-street-story">
        <HomeGameImage
          src="/home/game/seoul-street.jpg"
          alt="서울의 건물과 가로수 사이로 보행자와 차량이 표시된 실제 게임 거리"
          width={1600}
          height={900}
          caption="사람과 차량이 있는 서울 거리 · 게임 화면"
        />
        <div className="home-story-copy">
          <span className="home-eyebrow">서울의 일상도 함께</span>
          <h3>사람과 차가 오가는 거리</h3>
          <p>
            공개 생활인구와 주요 장소의 인구·평균 도로 속도를 참고해, 게임 속 사람과 차량의 표시량과
            움직임을 조절합니다.
          </p>
          <p className="home-story-note">개별 사람·차량의 실제 위치를 보여주는 것은 아닙니다.</p>
        </div>
      </div>
    </section>
  );
}
