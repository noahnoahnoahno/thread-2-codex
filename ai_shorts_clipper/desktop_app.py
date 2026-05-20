from __future__ import annotations

import argparse
import json
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ai_shorts_clipper.media_ingest import extract_with_ytdlp, inspect_allowed_url
from ai_shorts_clipper.ytdlp_update import ensure_ytdlp_current


APP_TITLE = "AI Shorts Clipper"
DEFAULT_OUTPUT_DIR = Path.home() / "Downloads" / "AI Shorts Clipper"


class DesktopApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("820x620")
        self.root.minsize(720, 560)

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.url_var = tk.StringVar()
        self.permission_var = tk.StringVar(value="needs_review")
        self.enable_extractor_var = tk.BooleanVar(value=False)
        self.output_dir_var = tk.StringVar(value=str(DEFAULT_OUTPUT_DIR))
        self.status_var = tk.StringVar(value="URL을 붙여넣고 먼저 검사하세요.")

        self._build_layout()
        self._poll_events()

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        frame = ttk.Frame(self.root, padding=18)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(5, weight=1)

        title = ttk.Label(frame, text=APP_TITLE, font=("Helvetica", 22, "bold"))
        title.grid(row=0, column=0, sticky="w")

        subtitle = ttk.Label(frame, text="권한 확인 후 허용된 URL만 로컬 파일로 가져옵니다.")
        subtitle.grid(row=1, column=0, sticky="w", pady=(4, 18))

        url_row = ttk.Frame(frame)
        url_row.grid(row=2, column=0, sticky="ew")
        url_row.columnconfigure(0, weight=1)
        ttk.Entry(url_row, textvariable=self.url_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(url_row, text="검사", command=self.inspect_url).grid(row=0, column=1, padx=(8, 0))

        controls = ttk.Frame(frame)
        controls.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        controls.columnconfigure(1, weight=1)
        ttk.Label(controls, text="권한 상태").grid(row=0, column=0, sticky="w")
        permission = ttk.Combobox(
            controls,
            textvariable=self.permission_var,
            values=["needs_review", "user_owned", "licensed", "platform_export", "embed_only", "blocked"],
            state="readonly",
            width=18,
        )
        permission.grid(row=0, column=1, sticky="w", padx=(8, 18))
        ttk.Checkbutton(controls, text="선택 추출 엔진 사용", variable=self.enable_extractor_var).grid(
            row=0, column=2, sticky="w"
        )

        output_row = ttk.Frame(frame)
        output_row.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        output_row.columnconfigure(1, weight=1)
        ttk.Label(output_row, text="저장 폴더").grid(row=0, column=0, sticky="w")
        ttk.Entry(output_row, textvariable=self.output_dir_var).grid(row=0, column=1, sticky="ew", padx=(8, 8))
        ttk.Button(output_row, text="선택", command=self.choose_output_dir).grid(row=0, column=2)

        self.result_text = tk.Text(frame, height=16, wrap="word")
        self.result_text.grid(row=5, column=0, sticky="nsew", pady=(16, 0))
        self.result_text.configure(state="disabled")

        action_row = ttk.Frame(frame)
        action_row.grid(row=6, column=0, sticky="ew", pady=(14, 0))
        action_row.columnconfigure(0, weight=1)
        ttk.Label(action_row, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        ttk.Button(action_row, text="추출 시작", command=self.extract_url).grid(row=0, column=1, sticky="e")

    def choose_output_dir(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_dir_var.get() or str(DEFAULT_OUTPUT_DIR))
        if selected:
            self.output_dir_var.set(selected)

    def inspect_url(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning(APP_TITLE, "URL을 입력하세요.")
            return
        flow = inspect_allowed_url(url, permission_state=self.permission_var.get())
        self._write_result(flow.to_dict())
        self.status_var.set(f"검사 완료: {flow.platform} / next_action={flow.next_action}")

    def extract_url(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning(APP_TITLE, "URL을 입력하세요.")
            return
        if not self.enable_extractor_var.get():
            messagebox.showwarning(APP_TITLE, "추출 엔진 사용 체크가 필요합니다.")
            return
        if self.permission_var.get() not in {"user_owned", "licensed", "platform_export"}:
            messagebox.showwarning(APP_TITLE, "추출하려면 권한 상태가 user_owned, licensed, platform_export 중 하나여야 합니다.")
            return

        self.status_var.set("추출 중입니다. 창을 닫지 마세요.")
        self._set_controls_enabled(False)
        thread = threading.Thread(
            target=self._extract_worker,
            args=(url, self.output_dir_var.get(), self.permission_var.get(), self.enable_extractor_var.get()),
            daemon=True,
        )
        thread.start()

    def _extract_worker(self, url: str, output_dir: str, permission_state: str, extractor_enabled: bool) -> None:
        try:
            result = extract_with_ytdlp(
                url,
                output_dir,
                permission_state=permission_state,
                extractor_enabled=extractor_enabled,
            )
        except Exception as exc:
            self.events.put(("error", str(exc)))
        else:
            self.events.put(("extracted", result.to_dict()))

    def _poll_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "error":
                    self.status_var.set("추출 실패")
                    messagebox.showerror(APP_TITLE, str(payload))
                elif event == "extracted":
                    self.status_var.set("추출 완료")
                    self._write_result(payload)
                self._set_controls_enabled(True)
        except queue.Empty:
            pass
        self.root.after(120, self._poll_events)

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for child in self.root.winfo_children():
            self._set_widget_state(child, state)
        self.result_text.configure(state="disabled")

    def _set_widget_state(self, widget: tk.Widget, state: str) -> None:
        try:
            widget.configure(state=state)
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._set_widget_state(child, state)

    def _write_result(self, payload: object) -> None:
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", json.dumps(payload, ensure_ascii=False, indent=2))
        self.result_text.configure(state="disabled")


def run_desktop_app() -> None:
    splash = tk.Tk()
    splash.title(APP_TITLE)
    splash.geometry("420x140")
    splash.resizable(False, False)
    ttk.Label(splash, text="yt-dlp 업데이트 확인 중...", font=("Helvetica", 16, "bold")).pack(pady=(28, 8))
    status_var = tk.StringVar(value="앱 시작 전 최신 버전을 확인합니다.")
    ttk.Label(splash, textvariable=status_var).pack()
    splash.update()

    update_status = ensure_ytdlp_current(reporter=status_var.set)
    splash.after(350, splash.destroy)
    splash.mainloop()

    root = tk.Tk()
    app = DesktopApp(root)
    if update_status.warning:
        app.status_var.set(update_status.warning)
    else:
        app.status_var.set(f"yt-dlp 준비 완료: {update_status.current_version or 'unknown'}")
    root.mainloop()


def self_test() -> int:
    status = ensure_ytdlp_current(reporter=lambda message: print(f"[startup] {message}", file=sys.stderr))
    print(json.dumps(status.to_dict(), ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="AI Shorts Clipper desktop app.")
    parser.add_argument("--self-test", action="store_true", help="Run startup checks and exit without opening the GUI.")
    args = parser.parse_args(argv)
    if args.self_test:
        raise SystemExit(self_test())
    run_desktop_app()


if __name__ == "__main__":
    main()
