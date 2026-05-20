import React, { useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const APP_TITLE = 'AI Shorts Clipper';
const permissionStates = [
  'needs_review',
  'user_owned',
  'licensed',
  'platform_export',
  'embed_only',
  'blocked',
];

function App() {
  const [url, setUrl] = useState('');
  const [permissionState, setPermissionState] = useState('needs_review');
  const [extractorEnabled, setExtractorEnabled] = useState(false);
  const [outputDir, setOutputDir] = useState('서버 작업 폴더');
  const [subtitles, setSubtitles] = useState(null);
  const [video, setVideo] = useState(null);
  const [count, setCount] = useState(6);
  const [minDuration, setMinDuration] = useState(18);
  const [maxDuration, setMaxDuration] = useState(60);
  const [renderLimit, setRenderLimit] = useState(3);
  const [layout, setLayout] = useState('crop');
  const [burnSubtitles, setBurnSubtitles] = useState(false);
  const [status, setStatus] = useState('URL을 붙여넣고 먼저 검사하세요.');
  const [result, setResult] = useState('');
  const [downloadUrl, setDownloadUrl] = useState('');
  const [busy, setBusy] = useState(false);

  const clips = useMemo(() => {
    try {
      const parsed = JSON.parse(result);
      return Array.isArray(parsed.clips) ? parsed.clips : [];
    } catch {
      return [];
    }
  }, [result]);

  const writeResult = (payload) => {
    setResult(JSON.stringify(payload, null, 2));
  };

  const inspectUrl = async () => {
    const trimmedUrl = url.trim();
    if (!trimmedUrl) {
      window.alert('URL을 입력하세요.');
      return;
    }
    await runTask('검사 중입니다.', async () => {
      const response = await fetch('/api/inspect-url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: trimmedUrl, permission_state: permissionState }),
      });
      const payload = await readJson(response);
      writeResult(payload);
      setDownloadUrl('');
      setStatus(`검사 완료: ${payload.platform} / next_action=${payload.next_action}`);
    });
  };

  const extractUrl = async () => {
    const trimmedUrl = url.trim();
    if (!trimmedUrl) {
      window.alert('URL을 입력하세요.');
      return;
    }
    if (!extractorEnabled) {
      window.alert('추출 엔진 사용 체크가 필요합니다.');
      return;
    }
    if (!['user_owned', 'licensed', 'platform_export'].includes(permissionState)) {
      window.alert('추출하려면 권한 상태가 user_owned, licensed, platform_export 중 하나여야 합니다.');
      return;
    }
    await runTask('추출 중입니다. 창을 닫지 마세요.', async () => {
      const response = await fetch('/api/extract-url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: trimmedUrl,
          permission_state: permissionState,
          extractor_enabled: extractorEnabled,
        }),
      });
      const payload = await readJson(response);
      writeResult(payload);
      setDownloadUrl(payload.download_url || '');
      setStatus('추출 완료');
    });
  };

  const analyze = async () => {
    if (!subtitles) {
      window.alert('자막 파일을 선택하세요.');
      return;
    }
    const form = new FormData();
    form.append('subtitles', subtitles);
    form.append('count', String(count));
    form.append('min_duration', String(minDuration));
    form.append('max_duration', String(maxDuration));
    await runTask('후보 클립을 분석 중입니다.', async () => {
      const response = await fetch('/api/analyze', { method: 'POST', body: form });
      const payload = await readJson(response);
      writeResult(payload);
      setDownloadUrl('');
      setStatus(`분석 완료: 후보 ${payload.clip_count}개`);
    });
  };

  const render = async () => {
    if (!video || !subtitles) {
      window.alert('영상 파일과 자막 파일을 모두 선택하세요.');
      return;
    }
    const form = new FormData();
    form.append('video', video);
    form.append('subtitles', subtitles);
    form.append('count', String(count));
    form.append('min_duration', String(minDuration));
    form.append('max_duration', String(maxDuration));
    form.append('render_limit', String(renderLimit));
    form.append('layout', layout);
    form.append('burn_subtitles', String(burnSubtitles));
    await runTask('렌더링 중입니다. 창을 닫지 마세요.', async () => {
      const response = await fetch('/api/render', { method: 'POST', body: form });
      const payload = await readJson(response);
      writeResult(payload);
      setDownloadUrl('');
      setStatus('렌더링 작업이 접수되었습니다. 완료 상태를 확인 중입니다.');
      const finalPayload = payload.status_url
        ? await pollRenderJob(payload, (nextPayload) => {
          writeResult(nextPayload);
          setStatus(nextPayload.message || '렌더링 상태 확인 중입니다.');
        })
        : payload;
      writeResult(finalPayload);
      setDownloadUrl(finalPayload.download_url || '');
      setStatus(`렌더링 완료: MP4 ${finalPayload.rendered_count || 0}개`);
    });
  };

  const chooseOutputDir = () => {
    window.alert('웹앱에서는 서버 작업 폴더를 사용하고, 완료 파일은 ZIP으로 다운로드합니다.');
    setOutputDir('서버 작업 폴더');
  };

  const runTask = async (message, task) => {
    setBusy(true);
    setStatus(message);
    try {
      await task();
    } catch (error) {
      const messageText = error instanceof Error ? error.message : String(error);
      writeResult({ error: messageText });
      setDownloadUrl('');
      setStatus('작업 실패');
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="app-shell">
      <section className="app-window" aria-label={APP_TITLE}>
        <h1>{APP_TITLE}</h1>
        <p className="subtitle">권한 확인 후 허용된 URL만 로컬 파일로 가져옵니다.</p>

        <div className="url-row">
          <input aria-label="URL" value={url} onChange={(event) => setUrl(event.target.value)} />
          <button type="button" onClick={inspectUrl} disabled={busy}>검사</button>
        </div>

        <div className="controls-row">
          <label htmlFor="permission">권한 상태</label>
          <select
            id="permission"
            value={permissionState}
            onChange={(event) => setPermissionState(event.target.value)}
            disabled={busy}
          >
            {permissionStates.map((state) => (
              <option value={state} key={state}>{state}</option>
            ))}
          </select>
          <label className="check-control">
            <input
              type="checkbox"
              checked={extractorEnabled}
              onChange={(event) => setExtractorEnabled(event.target.checked)}
              disabled={busy}
            />
            선택 추출 엔진 사용
          </label>
        </div>

        <div className="output-row">
          <label htmlFor="output-dir">저장 폴더</label>
          <input
            id="output-dir"
            value={outputDir}
            onChange={(event) => setOutputDir(event.target.value)}
            disabled={busy}
          />
          <button type="button" onClick={chooseOutputDir} disabled={busy}>선택</button>
        </div>

        <section className="tool-box" aria-label="쇼츠 분석과 렌더링">
          <h2>쇼츠 후보 분석 / 렌더링</h2>
          <div className="file-row">
            <label>
              자막 파일
              <input
                type="file"
                accept=".srt,.vtt,.txt"
                onChange={(event) => setSubtitles(event.target.files?.[0] || null)}
                disabled={busy}
              />
            </label>
            <label>
              영상 파일
              <input
                type="file"
                accept="video/*,.mp4,.mov,.mkv,.webm,.m4v"
                onChange={(event) => setVideo(event.target.files?.[0] || null)}
                disabled={busy}
              />
            </label>
          </div>

          <div className="settings-row">
            <label>
              후보 수
              <input
                type="number"
                min="1"
                max="12"
                value={count}
                onChange={(event) => setCount(Number(event.target.value))}
                disabled={busy}
              />
            </label>
            <label>
              최소 길이
              <input
                type="number"
                min="1"
                max="180"
                value={minDuration}
                onChange={(event) => setMinDuration(Number(event.target.value))}
                disabled={busy}
              />
            </label>
            <label>
              최대 길이
              <input
                type="number"
                min="1"
                max="300"
                value={maxDuration}
                onChange={(event) => setMaxDuration(Number(event.target.value))}
                disabled={busy}
              />
            </label>
            <label>
              렌더 수
              <input
                type="number"
                min="1"
                max="6"
                value={renderLimit}
                onChange={(event) => setRenderLimit(Number(event.target.value))}
                disabled={busy}
              />
            </label>
            <label>
              레이아웃
              <select value={layout} onChange={(event) => setLayout(event.target.value)} disabled={busy}>
                <option value="crop">crop</option>
                <option value="letterbox">letterbox</option>
              </select>
            </label>
            <label className="check-control">
              <input
                type="checkbox"
                checked={burnSubtitles}
                onChange={(event) => setBurnSubtitles(event.target.checked)}
                disabled={busy}
              />
              자막 굽기
            </label>
          </div>
        </section>

        {clips.length ? (
          <section className="clips-box" aria-label="후보 클립">
            {clips.map((clip, index) => (
              <article key={`${clip.start_sec}-${clip.end_sec}`}>
                <strong>{index + 1}. {clip.title}</strong>
                <p>{clip.reason}</p>
                <small>{formatTime(clip.start_sec)} - {formatTime(clip.end_sec)}</small>
              </article>
            ))}
          </section>
        ) : null}

        <textarea aria-label="검사 결과" value={result} readOnly />

        <div className="action-row">
          <span>{status}</span>
          <button type="button" onClick={extractUrl} disabled={busy}>추출 시작</button>
          <button type="button" onClick={analyze} disabled={busy}>후보 분석</button>
          <button type="button" onClick={render} disabled={busy}>렌더링</button>
          {downloadUrl ? <a href={downloadUrl}>ZIP 다운로드</a> : null}
        </div>
      </section>
    </main>
  );
}

async function readJson(response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || '요청 처리에 실패했습니다.');
  }
  return payload;
}

async function pollRenderJob(initialPayload, onUpdate) {
  let payload = initialPayload;
  const statusUrl = initialPayload.status_url;
  for (let attempt = 0; attempt < 240; attempt += 1) {
    if (payload.status === 'succeeded') {
      return payload;
    }
    if (payload.status === 'failed') {
      throw new Error(payload.error || payload.message || '렌더링에 실패했습니다.');
    }
    await sleep(3000);
    const response = await fetch(statusUrl, { cache: 'no-store' });
    payload = await readJson(response);
    onUpdate(payload);
  }
  throw new Error('렌더링 상태 확인 시간이 초과되었습니다.');
}

function sleep(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function formatTime(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  const minutes = Math.floor(value / 60);
  const rest = Math.floor(value % 60);
  return `${minutes}:${String(rest).padStart(2, '0')}`;
}

createRoot(document.getElementById('root')).render(<App />);
