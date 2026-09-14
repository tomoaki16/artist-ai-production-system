"""Local-only browser UI for the vertical Producer workflow."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from .connections import ConnectionConfig
from .workflow import produce_assets


def render_producer_ui(provider: str, model: str, intent: str) -> str:
    """Render a secret-free launch screen for a configured AI connection."""
    bootstrap = json.dumps({"provider": provider, "model": model}, ensure_ascii=False)
    safe_intent = (intent.replace("&", "&amp;").replace("<", "&lt;")
                   .replace(">", "&gt;").replace('"', "&quot;"))
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>AI Producerへ依頼</title>
<style>:root{{--ink:#191a1d;--sub:#686c73;--line:#dedfe3;--accent:#5b4bdb;--soft:#f1efff}}
*{{box-sizing:border-box}}body{{margin:0;background:#f5f5f7;color:var(--ink);font-family:system-ui,-apple-system,"Noto Sans JP",sans-serif}}main{{max-width:720px;margin:auto;padding:42px 18px}}.card{{background:white;border:1px solid var(--line);border-radius:18px;padding:22px}}h1{{font-size:28px;margin:0 0 8px}}p{{line-height:1.6}}.lead{{color:var(--sub)}}dl{{display:grid;grid-template-columns:110px 1fr;gap:9px;margin:24px 0}}dt{{color:var(--sub)}}dd{{margin:0;font-weight:650}}.intent{{background:var(--soft);border-radius:12px;padding:14px}}button{{width:100%;border:0;border-radius:11px;background:var(--accent);color:white;padding:14px;font:inherit;font-weight:750;cursor:pointer}}button:disabled{{opacity:.55;cursor:wait}}#status{{min-height:24px;color:var(--sub)}}#result{{display:none;margin-top:18px;border-top:1px solid var(--line);padding-top:18px}}#result a{{display:block;color:var(--accent);font-weight:700;margin:10px 0}}.error{{color:#a32929!important}}small{{display:block;color:var(--sub);margin-top:12px;line-height:1.5}}</style></head>
<body><main><section class="card"><h1>AI Producerへ依頼</h1><p class="lead">確定済みの音楽情報とArtistの境界を使って、比較できる3案を生成します。</p>
<dl><dt>接続先</dt><dd id="provider"></dd><dt>モデル</dt><dd id="model"></dd><dt>Artistの意図</dt><dd class="intent">{safe_intent}</dd></dl>
<button id="produce">AIに3案を依頼</button><p id="status"></p><section id="result"><strong>生成が完了しました</strong><a href="/output/index.html">3案を比較する</a><div id="midi"></div></section>
<small>APIキーはこの画面へ送られません。ローカルプロセスが環境変数から実行時にだけ読みます。</small></section></main>
<script>const config={bootstrap};provider.textContent=config.provider;model.textContent=config.model;
produce.onclick=async()=>{{produce.disabled=true;status.className='';status.textContent='AIへ依頼し、提案を検査しています…';result.style.display='none';try{{const response=await fetch('/api/produce',{{method:'POST'}});const data=await response.json();if(!response.ok)throw new Error(data.error||'生成に失敗しました');status.textContent=`${{data.proposal_count}}案の検査とMIDI生成が完了しました。`;midi.innerHTML=data.midi.map(x=>`<a href="${{x.url}}" download>${{x.name}}を取得</a>`).join('');result.style.display='block';}}catch(error){{status.className='error';status.textContent=error.message;}}finally{{produce.disabled=false;}}}};</script></body></html>'''


class ProducerUIHandler(BaseHTTPRequestHandler):
    """Serve one configured request without exposing filesystem or credentials."""

    config: ConnectionConfig
    producer_request: dict[str, Any]
    output_dir: Path
    caller: Callable[..., dict[str, Any]] | None = None

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/":
            artist = self.producer_request.get("artist", {})
            body = render_producer_ui(
                self.config.provider, self.config.model, str(artist.get("intent", ""))
            ).encode("utf-8")
            self._send(200, "text/html; charset=utf-8", body)
            return
        if path.startswith("/output/"):
            relative = path.removeprefix("/output/")
            candidate = (self.output_dir / relative).resolve()
            root = self.output_dir.resolve()
            if candidate != root and root in candidate.parents and candidate.is_file():
                content_type = "audio/midi" if candidate.suffix == ".mid" else "text/html; charset=utf-8"
                self._send(200, content_type, candidate.read_bytes())
                return
        self._send(404, "application/json", b'{"error":"not found"}')

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/produce":
            self._send(404, "application/json", b'{"error":"not found"}')
            return
        try:
            options = {"caller": self.caller} if self.caller else {}
            assets = produce_assets(
                self.config, self.producer_request, self.output_dir, **options
            )
            midi = [{"name": path.stem, "url": f"/output/midi-takes/{path.name}"}
                    for path in assets["midi"]]
            payload = {"ok": True, "proposal_count": len(midi), "midi": midi}
            self._send(200, "application/json; charset=utf-8",
                       json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        except Exception as exc:  # boundary: return a useful local UI error
            payload = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
            self._send(400, "application/json; charset=utf-8", payload)

    def log_message(self, format: str, *args: object) -> None:
        pass


def build_producer_ui_server(
    config: ConnectionConfig,
    producer_request: dict[str, Any],
    output_dir: str | Path,
    *,
    port: int = 8765,
    caller: Callable[[ConnectionConfig, dict[str, Any]], dict[str, Any]] | None = None,
) -> ThreadingHTTPServer:
    """Build a loopback-only server; caller injection keeps HTTP tests offline."""
    handler = type("ConfiguredProducerUI", (ProducerUIHandler,), {
        "config": config, "producer_request": producer_request,
        "output_dir": Path(output_dir),
        "caller": staticmethod(caller) if caller else None,
    })
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def serve_producer_ui(config: ConnectionConfig, producer_request: dict[str, Any],
                      output_dir: str | Path, *, port: int = 8765) -> None:
    server = build_producer_ui_server(config, producer_request, output_dir, port=port)
    print(f"AI Producer UI: http://127.0.0.1:{port}")
    server.serve_forever()
