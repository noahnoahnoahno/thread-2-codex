import React, { useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const APP_TITLE = '롱폼 to 쇼츠 자동변환기';
const DEFAULT_OUTPUT_DIR = '/Users/noahai/Downloads/AI Shorts Clipper';
const permissionStates = [
  'needs_review',
  'user_owned',
  'licensed',
  'platform_export',
  'embed_only',
  'blocked',
];

function detectPlatform(url) {
  try {
    const { hostname } = new URL(url);
    const host = hostname.replace(/^www\./, '').toLowerCase();
    if (host === 'youtu.be' || host === 'youtube.com' || host === 'm.youtube.com' || host === 'music.youtube.com' || host.endsWith('.youtube.com')) {
      return 'youtube';
    }
    if (host === 'tiktok.com' || host === 'vm.tiktok.com' || host === 'vt.tiktok.com' || host.endsWith('.tiktok.com')) {
      return 'tiktok';
    }
    if (host === 'douyin.com' || host === 'iesdouyin.com' || host === 'v.douyin.com' || host.endsWith('.douyin.com')) {
      return 'douyin';
    }
    if (host === 'threads.net' || host === 'threads.com' || host.endsWith('.threads.net') || host.endsWith('.threads.com')) {
      return 'threads';
    }
  } catch {
    return 'unsupported';
  }
  return 'unsupported';
}

function inspectAllowedUrl(url, permissionState) {
  const platform = detectPlatform(url);
  if (platform === 'unsupported') {
    return {
      platform,
      original_url: url,
      canonical_url: null,
      title: null,
      thumbnail_url: null,
      duration_sec: null,
      capabilities: ['blocked'],
      permission_state: 'blocked',
      next_action: 'block',
      source_notes: ['Unsupported URL. Upload a local file if you have rights to process it.'],
    };
  }

  const allowedStates = new Set(['user_owned', 'licensed', 'platform_export']);
  const capabilities = ['metadata', 'upload_required'];
  const sourceNotes = [
    'Metadata and embed checks should run before any binary import.',
    'Direct extraction is disabled unless the extractor feature flag and permission gate are both enabled.',
  ];

  if (platform === 'youtube' || platform === 'threads') {
    capabilities.push('embed');
  }
  if (platform === 'tiktok' || platform === 'douyin') {
    capabilities.push('authorized_user_export');
  }

  const nextAction = allowedStates.has(permissionState) ? 'import_media' : 'request_upload';
  if (allowedStates.has(permissionState)) {
    capabilities.push('authorized_binary_import');
  }

  return {
    platform,
    original_url: url,
    canonical_url: url,
    title: null,
    thumbnail_url: null,
    duration_sec: null,
    capabilities,
    permission_state: permissionState,
    next_action: nextAction,
    source_notes: sourceNotes,
  };
}

function App() {
  const [url, setUrl] = useState('');
  const [permissionState, setPermissionState] = useState('needs_review');
  const [extractorEnabled, setExtractorEnabled] = useState(false);
  const [outputDir, setOutputDir] = useState(DEFAULT_OUTPUT_DIR);
  const [status, setStatus] = useState('URL을 붙여넣고 먼저 검사하세요.');
  const [result, setResult] = useState('');

  const resultValue = useMemo(() => result, [result]);

  const writeResult = (payload) => {
    setResult(JSON.stringify(payload, null, 2));
  };

  const inspectUrl = () => {
    const trimmedUrl = url.trim();
    if (!trimmedUrl) {
      window.alert('URL을 입력하세요.');
      return;
    }
    const flow = inspectAllowedUrl(trimmedUrl, permissionState);
    writeResult(flow);
    setStatus(`검사 완료: ${flow.platform} / next_action=${flow.next_action}`);
  };

  const chooseOutputDir = () => {
    window.alert('웹앱에서는 로컬 폴더 선택 창을 직접 열 수 없습니다. 데스크톱 앱에서는 폴더 선택 창이 열립니다.');
  };

  const extractUrl = () => {
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
    setStatus('추출 중입니다. 창을 닫지 마세요.');
    writeResult({
      status: 'extract_failed',
      message: '정적 웹앱에서는 로컬 추출 엔진을 실행할 수 없습니다. 원본 데스크톱 앱 또는 별도 백엔드 연결이 필요합니다.',
      original_url: trimmedUrl,
      output_dir: outputDir,
      permission_state: permissionState,
      extractor_enabled: extractorEnabled,
    });
    setStatus('추출 실패');
  };

  return (
    <main className="app-shell">
      <section className="app-window" aria-label={APP_TITLE}>
        <h1>{APP_TITLE}</h1>
        <p className="subtitle">권한 확인 후 허용된 URL만 로컬 파일로 가져옵니다.</p>

        <div className="url-row">
          <input
            aria-label="URL"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
          />
          <button type="button" onClick={inspectUrl}>검사</button>
        </div>

        <div className="controls-row">
          <label htmlFor="permission">권한 상태</label>
          <select
            id="permission"
            value={permissionState}
            onChange={(event) => setPermissionState(event.target.value)}
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
          />
          <button type="button" onClick={chooseOutputDir}>선택</button>
        </div>

        <textarea
          aria-label="검사 결과"
          value={resultValue}
          readOnly
        />

        <div className="action-row">
          <span>{status}</span>
          <button type="button" onClick={extractUrl}>추출 시작</button>
        </div>
      </section>
    </main>
  );
}

createRoot(document.getElementById('root')).render(<App />);
