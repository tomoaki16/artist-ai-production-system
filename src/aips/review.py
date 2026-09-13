"""Self-contained material review UI for validating the Artist decision flow."""

from __future__ import annotations

from html import escape
import json
from typing import Any


STATUS_LABELS = {
    "playback": "使う",
    "muted_candidate": "参照",
    "inactive_due_to_solo": "参照",
}

ROLE_LABELS = {
    "drums": "ドラム",
    "bass": "ベース",
    "guitar": "ギター",
    "keys": "鍵盤",
    "unknown": "未設定",
}


def render_material_review(context: dict[str, Any]) -> str:
    """Render a portable HTML screen that exports Artist-confirmed decisions."""
    rows = []
    for index, track in enumerate(context.get("tracks", [])):
        default_status = STATUS_LABELS.get(track.get("selection_status"), "参照")
        role = track.get("inferred_role", "unknown")
        source_type = "録音" if track.get("audio_assets") else "MIDI" if track.get("notes") else "空"
        details = f"{source_type}・{track.get('clip_count', 0)}クリップ"
        if track.get("notes"):
            details += f"・{len(track['notes'])}ノート"
        usage_options = (("use", "使う"), ("reference", "参照"), ("ignore", "無視"))
        buttons = "".join(
            f'<button type="button" data-value="{value}" class="choice{(" active" if label == default_status else "")}">{label}</button>'
            for value, label in usage_options
        )
        role_options = "".join(
            f'<option value="{value}"{(" selected" if value == role else "")}>{label}</option>'
            for value, label in ROLE_LABELS.items()
        )
        rows.append(f"""
        <article class="track" data-id="{escape(str(track.get('id', index)))}">
          <div class="track-main">
            <div><h2>{escape(str(track.get('name', '名称なし')))}</h2><p>{escape(details)}</p></div>
            <select aria-label="楽器の役割">{role_options}</select>
          </div>
          <div class="decisions" role="group" aria-label="素材の扱い">{buttons}</div>
        </article>""")

    selection = context.get("selection") or {}
    range_text = (
        f"{selection.get('start_bar')}小節目から{selection.get('bars')}小節"
        if selection else "プロジェクト全体"
    )
    payload = json.dumps({
        "schema_version": "0.1",
        "source": context.get("source"),
        "selection": context.get("selection"),
    }, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>素材を確認</title><style>
:root{{--ink:#202124;--sub:#6b6f76;--line:#dfe1e5;--paper:#fff;--accent:#5b4bdb;--soft:#f1efff}}
*{{box-sizing:border-box}} body{{margin:0;background:#f5f5f7;color:var(--ink);font-family:system-ui,-apple-system,"Noto Sans JP",sans-serif}}
main{{max-width:760px;margin:auto;padding:32px 18px 100px}} header{{margin-bottom:24px}} h1{{font-size:28px;margin:0 0 8px}} header p{{color:var(--sub);margin:4px 0;line-height:1.6}}
.track{{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:16px;margin:12px 0}}
.track-main{{display:flex;align-items:center;justify-content:space-between;gap:16px}} h2{{font-size:17px;margin:0 0 5px}} .track p{{font-size:13px;color:var(--sub);margin:0}}
select{{font:inherit;padding:9px 30px 9px 10px;border:1px solid var(--line);border-radius:9px;background:white}}
.decisions{{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:14px}} .choice{{border:1px solid var(--line);background:white;padding:9px;border-radius:9px;font-weight:650;cursor:pointer}}
.choice.active{{color:var(--accent);border-color:var(--accent);background:var(--soft)}}
.note{{font-size:13px;color:var(--sub);padding:12px 2px}} footer{{position:fixed;bottom:0;left:0;right:0;background:rgba(255,255,255,.94);border-top:1px solid var(--line);padding:14px 18px;backdrop-filter:blur(8px)}}
.footer-inner{{max-width:724px;margin:auto;display:flex;align-items:center;justify-content:space-between;gap:16px}} #summary{{font-size:13px;color:var(--sub)}} #save{{border:0;border-radius:10px;background:var(--accent);color:white;font-weight:700;padding:12px 18px;cursor:pointer}}
@media(max-width:560px){{main{{padding-top:22px}}.track-main{{align-items:flex-start}}select{{max-width:125px}}.footer-inner{{align-items:stretch;flex-direction:column;gap:8px}}#save{{width:100%}}}}
</style></head><body><main>
<header><h1>AIに渡す素材を確認</h1><p>{escape(range_text)}</p><p>自動判定は仮です。作品の意図に合わせて、素材の扱いと楽器を決めてください。</p></header>
{''.join(rows)}
<p class="note">「参照」は音楽的な背景としてAIに見せますが、変更対象にはしません。「無視」はAIへ渡しません。</p>
</main><footer><div class="footer-inner"><span id="summary"></span><button id="save">この内容で決定</button></div></footer>
<script>
const base={payload};
function updateSummary(){{const values=[...document.querySelectorAll('.choice.active')].map(x=>x.dataset.value);document.querySelector('#summary').textContent=`使う ${{values.filter(x=>x==='use').length}}・参照 ${{values.filter(x=>x==='reference').length}}・無視 ${{values.filter(x=>x==='ignore').length}}`;}}
document.querySelectorAll('.choice').forEach(button=>button.onclick=()=>{{button.parentElement.querySelectorAll('.choice').forEach(x=>x.classList.remove('active'));button.classList.add('active');updateSummary();}});
document.querySelector('#save').onclick=()=>{{base.track_decisions=[...document.querySelectorAll('.track')].map(row=>({{track_id:row.dataset.id,usage:row.querySelector('.choice.active').dataset.value,role:row.querySelector('select').value}}));const blob=new Blob([JSON.stringify(base,null,2)],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='artist-decisions.json';a.click();URL.revokeObjectURL(a.href);}};
updateSummary();
</script></body></html>"""


def render_ai_payload_preview(payload: dict[str, Any]) -> str:
    """Render exactly what is eligible for an AI provider before any transmission."""
    tracks = payload["project"]["tracks"]
    cards = []
    for track in tracks:
        usage = track["artist_usage"]
        badge = "変更可能" if usage == "use" else "参照のみ"
        assets = [asset.get("path") for asset in track.get("audio_assets", []) if asset.get("path")]
        facts = [ROLE_LABELS.get(track.get("role"), "未設定")]
        if track.get("notes"):
            facts.append(f"MIDI {len(track['notes'])}ノート")
        if assets:
            facts.append(f"録音 {len(assets)}ファイル")
        asset_html = "".join(f"<li>{escape(path)}</li>" for path in assets)
        cards.append(f"""<article class="track"><div><h2>{escape(track['name'])}</h2>
        <p>{escape('・'.join(facts))}</p></div><strong class="{'edit' if usage == 'use' else 'ref'}">{badge}</strong>
        {f'<details><summary>送信対象の録音ファイル名</summary><ul>{asset_html}</ul></details>' if assets else ''}</article>""")
    ignored = payload.get("excluded_from_ai", [])
    ignored_names = "、".join(item["name"] for item in ignored) or "なし"
    harmony = payload["project"].get("harmony", {})
    harmony_text = f"{len(harmony.get('events', []))}件" if harmony.get("available") else "なし（入力が必要）"
    raw = escape(json.dumps(payload, ensure_ascii=False, indent=2))
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI送信内容の確認</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f5f5f7;color:#202124;font-family:system-ui,-apple-system,"Noto Sans JP",sans-serif}}main{{max-width:760px;margin:auto;padding:32px 18px 70px}}h1{{font-size:28px;margin:0 0 8px}}.lead,p,summary,li{{line-height:1.55}}.lead{{color:#686c73;margin-bottom:22px}}.summary{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-bottom:20px}}.summary div,.track{{background:white;border:1px solid #dfe1e5;border-radius:14px;padding:16px}}.summary b{{display:block;font-size:21px}}.summary span,.track p{{font-size:13px;color:#686c73}}.track{{margin:11px 0;display:grid;grid-template-columns:1fr auto;gap:10px;align-items:start}}h2{{font-size:17px;margin:0 0 5px}}.track p{{margin:0}}strong{{font-size:12px;padding:6px 9px;border-radius:999px}}.edit{{color:#176b42;background:#e7f6ee}}.ref{{color:#625400;background:#fff6c9}}details{{grid-column:1/-1;margin-top:4px;font-size:13px}}details.raw{{background:white;border:1px solid #dfe1e5;border-radius:14px;padding:14px;margin-top:22px}}pre{{white-space:pre-wrap;word-break:break-word;font-size:11px}}.warning{{border-left:4px solid #5b4bdb;padding:11px 14px;background:#f1efff;border-radius:5px;margin:18px 0}}
</style></head><body><main><h1>AIへ渡す内容を確認</h1><p class="lead">まだ送信していません。以下が接続先AIの分析対象になります。</p>
<section class="summary"><div><b>{len(tracks)}</b><span>送信するトラック</span></div><div><b>{harmony_text}</b><span>コード情報</span></div></section>
<p class="warning">変更可能と参照のみの境界は、AIへの命令にも強制的に含まれます。</p>{''.join(cards)}
<p>AIへ送らないトラック：{escape(ignored_names)}</p><details class="raw"><summary>送信データの詳細を見る</summary><pre>{raw}</pre></details>
</main></body></html>"""
