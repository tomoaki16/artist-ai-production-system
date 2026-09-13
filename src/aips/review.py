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
