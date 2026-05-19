import React from 'react';
import { createRoot } from 'react-dom/client';
import {
  ArrowUpRight,
  BadgeCheck,
  Captions,
  CheckCircle2,
  Clock3,
  FileVideo2,
  Film,
  Gauge,
  KeyRound,
  Layers3,
  ListChecks,
  MonitorPlay,
  PlaySquare,
  Scissors,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  UploadCloud,
  WandSparkles,
} from 'lucide-react';
import './styles.css';

const metrics = [
  { label: '후보 클립', value: '6개', note: '자막 기반 자동 추천', icon: Scissors },
  { label: '렌더 비율', value: '9:16', note: '1080x1920 쇼츠 출력', icon: MonitorPlay },
  { label: '처리 방식', value: '로컬', note: '권한 있는 원본 파일 기준', icon: ShieldCheck },
  { label: '다음 단계', value: '큐 분리', note: '서버 백엔드 예정', icon: Layers3 },
];

const pipeline = [
  {
    title: '원본 준비',
    text: '권한이 있는 롱폼 영상과 SRT/VTT 자막을 준비합니다.',
    icon: UploadCloud,
  },
  {
    title: '자막 파싱',
    text: '타임스탬프를 읽어 후킹, 숫자, 감정, 실용 신호를 점수화합니다.',
    icon: Captions,
  },
  {
    title: '후보 추천',
    text: '18~60초 길이의 쇼츠 후보를 겹침 없이 6개까지 추립니다.',
    icon: WandSparkles,
  },
  {
    title: '편집 검수',
    text: '제목, 자막, 레이아웃, 브랜딩, 시작/끝 지점을 사람이 확인합니다.',
    icon: SlidersHorizontal,
  },
  {
    title: 'MP4 렌더링',
    text: 'FFmpeg로 세로형 쇼츠를 만들고 결과 폴더에 산출물을 남깁니다.',
    icon: Film,
  },
];

const safeguards = [
  '권한 없는 외부 영상 다운로드를 기본 흐름으로 넣지 않음',
  '대용량 원본 영상과 결과 MP4는 GitHub 업로드 제외',
  'API 키와 로컬 작업 로그는 공개 저장소에서 분리',
  '자막/영상 분석 결과는 사용자가 검수한 뒤 렌더링',
  '실제 처리 기능은 서버 작업 큐와 저장소 정책 확정 후 연결',
];

const outputs = [
  { label: 'candidates.json', text: '추천 구간, 제목, 점수, 해시태그' },
  { label: 'final_shorts.mp4', text: '9:16 세로형 쇼츠 결과물' },
  { label: 'clip.srt', text: '클립별 자막 사이드카 파일' },
  { label: 'review notes', text: '편집 메모와 검수 경고' },
];

function App() {
  return (
    <main className="app-shell">
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">
            <Sparkles size={18} />
            THREAD 2
          </p>
          <h1>03 롱폼 to 쇼츠 자동변환기</h1>
          <p className="lede">
            긴 영상과 자막을 분석해 쇼츠 후보를 추천하고, 검수 후 9:16 MP4로
            렌더링하는 제작 보조 워크플로우입니다.
          </p>
          <div className="hero-actions">
            <a className="primary-action" href="#pipeline">
              변환 흐름 보기
              <ArrowUpRight size={18} />
            </a>
            <a className="secondary-action" href="https://ningning.kr">
              게이트로 이동
            </a>
          </div>
        </div>

        <div className="hero-visual" aria-hidden="true">
          <div className="editor-frame">
            <div className="source-card">
              <FileVideo2 size={28} />
              <div>
                <strong>longform_source.mp4</strong>
                <span>42:18 · transcript synced</span>
              </div>
            </div>
            <div className="shorts-preview">
              <div className="phone-screen">
                <PlaySquare size={42} />
                <strong>00:42</strong>
                <span>Hook score 87</span>
              </div>
              <div className="candidate-stack">
                <div><span>01</span><strong>충격 도입부</strong></div>
                <div><span>02</span><strong>숫자 증거</strong></div>
                <div><span>03</span><strong>실행 팁</strong></div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="metric-grid" aria-label="포팅 현황">
        {metrics.map((item) => {
          const Icon = item.icon;
          return (
            <article className="metric-card" key={item.label}>
              <Icon size={24} />
              <span>{item.label}</span>
              <strong>{item.value}</strong>
              <p>{item.note}</p>
            </article>
          );
        })}
      </section>

      <section className="content-grid">
        <article className="panel wide" id="pipeline">
          <div className="section-head">
            <Gauge size={24} />
            <div>
              <h2>자동변환 파이프라인</h2>
              <p>첫 공개 웹앱은 처리 구조와 운영 상태를 보여주고, 실제 렌더링은 백엔드 분리 후 연결합니다.</p>
            </div>
          </div>
          <div className="pipeline-list">
            {pipeline.map((step, index) => {
              const Icon = step.icon;
              return (
                <div className="pipeline-step" key={step.title}>
                  <div className="step-index">{String(index + 1).padStart(2, '0')}</div>
                  <div className="step-icon"><Icon size={22} /></div>
                  <div>
                    <h3>{step.title}</h3>
                    <p>{step.text}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </article>

        <aside className="panel">
          <div className="section-head compact">
            <ShieldCheck size={24} />
            <div>
              <h2>공개 배포 기준</h2>
              <p>Static Site 포팅</p>
            </div>
          </div>
          <ul className="check-list">
            {safeguards.map((item) => (
              <li key={item}>
                <CheckCircle2 size={18} />
                {item}
              </li>
            ))}
          </ul>
        </aside>
      </section>

      <section className="content-grid bottom">
        <article className="panel">
          <div className="section-head compact">
            <ListChecks size={24} />
            <div>
              <h2>주요 산출물</h2>
              <p>원본 프로젝트 기준</p>
            </div>
          </div>
          <div className="output-list">
            {outputs.map((item) => (
              <div className="output-row" key={item.label}>
                <BadgeCheck size={18} />
                <div>
                  <strong>{item.label}</strong>
                  <span>{item.text}</span>
                </div>
              </div>
            ))}
          </div>
        </article>

        <article className="panel deploy-panel">
          <div className="section-head compact">
            <KeyRound size={24} />
            <div>
              <h2>배포 상태</h2>
              <p>thread-2 슬롯</p>
            </div>
          </div>
          <div className="deploy-rows">
            <div><span>도메인</span><strong>thread-2.ningning.kr</strong></div>
            <div><span>GitHub</span><strong>thread-2-codex</strong></div>
            <div><span>빌드</span><strong>npm run build / dist</strong></div>
            <div><span>상태</span><strong><Clock3 size={15} /> 배포 준비</strong></div>
          </div>
        </article>
      </section>
    </main>
  );
}

createRoot(document.getElementById('root')).render(<App />);
