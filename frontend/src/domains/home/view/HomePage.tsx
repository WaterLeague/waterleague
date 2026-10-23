import { Fragment, useState, type ReactNode } from 'react';
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  Compass,
  Database,
  Flag,
  Layers3,
  Trophy,
} from 'lucide-react';
import { followLink } from '../../../shared/controller/useAppLocation';
import { facilities } from '../../game/service/gameService';
import { facilityIcons } from '../../facility/view/facilityIcons';
import { homeFacilities, homeModes } from '../service/homeContent';
import { HomePreview } from './HomePreview';
import { DataSection } from '../../catalog/view/DataSection';
import { useHomeMotion } from '../controller/useHomeMotion';
import { GameStartDialog } from './GameStartDialog';
import { HomeScoreGuide } from './HomeScoreGuide';
import { HomeMapGuide } from './HomeMapGuide';
import { HomeSeoulGuide } from './HomeSeoulGuide';
import { HomeGameImage } from './HomeGameImage';
import { HomeCompetitionGuide } from './HomeCompetitionGuide';
import './home.css';

function HomeLink({
  href,
  children,
  className = '',
  ariaLabel,
}: {
  href: string;
  children: ReactNode;
  className?: string;
  ariaLabel?: string;
}) {
  return (
    <a
      className={className}
      href={href}
      aria-label={ariaLabel}
      onClick={(event) => followLink(event, href)}
    >
      {children}
    </a>
  );
}

export function HomePage({ accountId = null }: { accountId?: string | null }) {
  const motion = useHomeMotion();
  const [facilityIndex, setFacilityIndex] = useState(0);
  const [choosingMode, setChoosingMode] = useState(false);
  const selected = homeFacilities[facilityIndex];
  return (
    <main className="home-page site-content" ref={motion}>
      <section className="home-hero" aria-labelledby="home-title">
        <div className="home-hero-copy">
          <span className="home-eyebrow">서울에서 시작하는 빗물 전략 게임</span>
          <h1 id="home-title">
            서울에 내리는 비,
            <br />
            내 설계로
            <br />
            <em>다르게 흐르다.</em>
          </h1>
          <p>
            서울 지도에 빗물 시설을 배치하고,
            <br />
            실제 관측된 강우로 효과를 비교하는 전략 게임.
            <br />
            여울이·가람이와 함께 시작하세요.
          </p>
          <div className="home-actions">
            <button
              type="button"
              className="home-button primary"
              aria-haspopup="dialog"
              onClick={() => setChoosingMode(true)}
            >
              게임 시작하기 <ArrowUpRight size={18} />
            </button>
            <a href="#home-seoul" className="home-button secondary">
              게임 알아보기 <ArrowRight size={16} />
            </a>
          </div>
          <span className="home-hero-note">서울 25개 구 · 두 가지 게임 모드 · 7종의 시설</span>
        </div>
        <figure className="home-hero-art">
          <img
            src="/brand/seoul-hero.png"
            alt="한강과 남산을 배경으로 수달 여울이와 물총새 가람이가 함께하는 WATER LEAGUE"
            width="1650"
            height="953"
            fetchPriority="high"
          />
        </figure>
      </section>

      <section className="home-guides" aria-labelledby="home-guide-title">
        <div className="home-section-heading">
          <span className="home-eyebrow">게임 소개</span>
          <h2 id="home-guide-title">배치하고, 비를 재생하고, 비교하세요.</h2>
          <p>예산 안에서 시설의 종류와 위치를 고르는 것이 이 게임의 시작입니다.</p>
        </div>
        <div className="home-guide-grid">
          <article className="home-guide otter">
            <img
              src="/brand/otter.png"
              width="300"
              height="299"
              loading="lazy"
              alt="물방울 지팡이를 든 수달 여울이"
            />
            <div>
              <span className="home-guide-name">수달 여울이</span>
              <h3>어디에 시설을 놓을까?</h3>
              <p>
                지붕과 도로, 식재 공간을 찾아 시설을 놓아보세요. 예산 안에서 종류와 면적을 고르고,
                설치 전후 빗물의 변화를 비교하는 게임이에요.
              </p>
            </div>
          </article>
          <article className="home-guide kingfisher">
            <img
              src="/brand/kingfisher.png"
              width="1383"
              height="1137"
              loading="lazy"
              alt="바위 위의 파란 물총새 가람이"
            />
            <div>
              <span className="home-guide-name">물총새 가람이</span>
              <h3>얼마나 달라졌을까?</h3>
              <p>
                지도를 살펴보고, 시간을 돌려 보고, 다른 기록과 비교해 보세요. 실제 공개 지도와 관측
                강우를 바탕으로 나만의 배치를 찾아갈 수 있어요.
              </p>
            </div>
          </article>
        </div>
      </section>

      <HomeSeoulGuide />

      <section className="home-modes" id="home-modes" aria-labelledby="home-modes-title">
        <div className="home-section-heading">
          <span className="home-eyebrow">게임 모드</span>
          <h2 id="home-modes-title">함께 겨루거나, 혼자 실험하거나.</h2>
          <p>우리 구와 한 주를 함께하거나, 과거의 호우에 새로운 설계로 도전하세요.</p>
        </div>
        <div className="home-mode-grid">
          {homeModes.map((mode) => (
            <Fragment key={mode.id}>
              <article className={`home-mode home-mode-${mode.id}`}>
                <HomeGameImage {...mode.image} />
                <div className="home-mode-copy">
                  <span className="home-eyebrow">
                    {mode.number} / {mode.tag}
                  </span>
                  <div className="home-mode-heading">
                    <h3>{mode.title}</h3>
                    <HomeLink
                      href={mode.href}
                      className="home-button primary home-mode-play"
                      ariaLabel={`${mode.title} 플레이`}
                    >
                      플레이 <ArrowUpRight size={16} aria-hidden="true" />
                    </HomeLink>
                  </div>
                  <p>{mode.intro}</p>
                  <ul>
                    {mode.rules.map((rule) => (
                      <li key={rule}>
                        <Check size={15} />
                        {rule}
                      </li>
                    ))}
                  </ul>
                </div>
              </article>
              {mode.id === 'weekly' && (
                <article className="home-shared-story">
                  <div className="home-story-copy">
                    <span className="home-eyebrow">같은 지도에서 함께</span>
                    <h3>다른 사람이 설치한 시설도 보여요.</h3>
                    <p>
                      내 시설뿐 아니라 다른 플레이어가 설치한 시설도 지도에서 확인할 수 있어요. 누가
                      어디에 어떤 시설을 놓았는지, 그 시설의 누적 점수까지 함께 살펴보세요.
                    </p>
                  </div>
                  <HomeGameImage
                    src="/home/game/shared-installations.png"
                    alt="여러 플레이어의 닉네임과 시설별 누적 점수가 함께 표시된 도봉구 설치 지도"
                    width={2148}
                    height={1294}
                    caption="다른 플레이어의 설치 시설과 누적 점수 · 게임 화면"
                  />
                </article>
              )}
            </Fragment>
          ))}
        </div>
        <p className="home-caption">
          이미지는 실제 게임의 촬영 화면입니다. 현재 순위와 점수는 게임에서 확인하세요.
        </p>
      </section>

      <section className="home-facilities" aria-labelledby="home-facilities-title">
        <div className="home-section-heading">
          <span className="home-eyebrow">시설 안내</span>
          <h2 id="home-facilities-title">빗물을 다루는 7가지 방법</h2>
          <p>시설을 골라 3D로 돌려 보고, 어디에서 어떤 역할을 하는지 알아보세요.</p>
        </div>
        <div className="home-facility-picker" role="group" aria-label="소개할 시설 선택">
          {homeFacilities.map((item, index) => {
            const Icon = facilityIcons[item.type];
            return (
              <button
                type="button"
                key={item.type}
                aria-pressed={index === facilityIndex}
                aria-controls="home-facility-detail"
                onClick={() => setFacilityIndex(index)}
              >
                <Icon size={18} />
                {facilities[item.type].name}
              </button>
            );
          })}
        </div>
        <div className="home-facility-detail" id="home-facility-detail">
          <HomePreview facility={selected.type} label={facilities[selected.type].name} />
          <div className="home-facility-copy" aria-live="polite">
            <div className="home-facility-description" key={selected.type}>
              <span className="home-eyebrow">
                시설 {String(facilityIndex + 1).padStart(2, '0')} / 07
              </span>
              <h3>{facilities[selected.type].name}</h3>
              <p>{selected.action}</p>
              <div className="home-placement">
                <Compass size={18} />
                <div>
                  <span>설치 위치</span>
                  <strong>{selected.place}</strong>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <HomeMapGuide />
      <HomeScoreGuide />

      <section className="home-features" aria-labelledby="home-features-title">
        <div className="home-section-heading">
          <span className="home-eyebrow">주요 기능</span>
          <h2 id="home-features-title">지도부터 대회까지</h2>
        </div>
        <div className="home-feature-grid">
          {[
            {
              Icon: Layers3,
              title: '서울 2D·3D 지도',
              text: '2D·3D 지도, 현재 위치 이동, 공개 시설과 강우 정보를 함께 살펴봐요.',
              href: '/weekly',
              link: '서울 지도 열기',
            },
            {
              Icon: Trophy,
              title: '주간·재해 랭킹',
              text: '주간 우리 구 순위와 과거 재해의 제출 기록을 같은 조건끼리 비교해요.',
              href: '/rankings',
              link: '랭킹 보기',
            },
            {
              Icon: Flag,
              title: '기관·기업·정부 대회',
              text: '대회에 참가하고 정해진 조건에 도전하세요. 승인된 기관·기업·정부는 기간·시설·1인당 예산을 정해 개최할 수 있어요.',
              href: '/competitions',
              link: '대회 둘러보기',
            },
            {
              Icon: Database,
              title: '데이터와 계산 근거',
              text: '지도·강우·시설 비용은 어디에서 왔는지, 자료와 계산의 근거를 확인해요.',
              href: '/#home-data',
              link: '데이터 살펴보기',
            },
          ].map(({ Icon, title, text, href, link }) => (
            <article key={href}>
              <Icon size={24} />
              <h3>{title}</h3>
              <p>{text}</p>
              <HomeLink href={href} className="home-text-link">
                {link}
                <ArrowUpRight size={16} />
              </HomeLink>
            </article>
          ))}
        </div>
      </section>

      <DataSection accountId={accountId} />
      <HomeCompetitionGuide />
      <footer className="home-footer">
        <img src="/brand/wordmark.png" alt="WATER LEAGUE" width="160" height="64" />
        <p>
          서울 공개자료와 관측 강우로 즐기는 빗물 전략 게임.
          <br />
          게임의 효과는 탐색 계산이며 실제 현장 침수 예측이나 시공 승인을 대신하지 않습니다.
        </p>
        <a href="mailto:1233day@naver.com">문의: 1233day@naver.com</a>
      </footer>
      {choosingMode && <GameStartDialog onClose={() => setChoosingMode(false)} />}
    </main>
  );
}
