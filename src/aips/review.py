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
        "transport": context.get("transport"),
        "harmony": context.get("harmony"),
        "tracks": context.get("tracks", []),
    }, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>素材を確認</title><style>
:root{{--ink:#202124;--sub:#6b6f76;--line:#dfe1e5;--paper:#fff;--accent:#5b4bdb;--soft:#f1efff}}
*{{box-sizing:border-box}} body{{margin:0;background:#f5f5f7;color:var(--ink);font-family:system-ui,-apple-system,"Noto Sans JP",sans-serif}}
main{{max-width:760px;margin:auto;padding:32px 18px 120px}} header{{margin-bottom:24px}} h1{{font-size:28px;margin:0 0 8px}} header p{{color:var(--sub);margin:4px 0;line-height:1.6}}
.track{{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:16px;margin:12px 0}}
.track-main{{display:flex;align-items:center;justify-content:space-between;gap:16px}} h2{{font-size:17px;margin:0 0 5px}} .track p{{font-size:13px;color:var(--sub);margin:0}}
select{{font:inherit;padding:9px 30px 9px 10px;border:1px solid var(--line);border-radius:9px;background:white}}
.decisions{{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:14px}} .choice{{border:1px solid var(--line);background:white;padding:9px;border-radius:9px;font-weight:650;cursor:pointer}}
.choice.active{{color:var(--accent);border-color:var(--accent);background:var(--soft)}}
.note{{font-size:13px;color:var(--sub);padding:12px 2px}} footer{{position:fixed;bottom:0;left:0;right:0;background:rgba(255,255,255,.94);border-top:1px solid var(--line);padding:14px 18px;backdrop-filter:blur(8px)}}
.footer-inner{{max-width:724px;margin:auto;display:flex;align-items:center;justify-content:space-between;gap:16px}} #summary{{font-size:13px;color:var(--sub)}} .actions{{display:flex;gap:8px}}button.primary{{border:0;border-radius:10px;background:var(--accent);color:white;font-weight:700;padding:12px 18px;cursor:pointer}}button.secondary{{border:1px solid var(--line);border-radius:10px;background:white;color:var(--ink);font-weight:650;padding:11px 15px;cursor:pointer}}.hidden{{display:none!important}}.send-card{{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:start;background:white;border:1px solid var(--line);border-radius:14px;padding:16px;margin:11px 0}}.badge{{font-size:12px;padding:6px 9px;border-radius:999px}}.editable{{color:#176b42;background:#e7f6ee}}.reference{{color:#625400;background:#fff6c9}}.warning{{border-left:4px solid var(--accent);padding:11px 14px;background:var(--soft);border-radius:5px;margin:18px 0}}.send-summary{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}}.send-summary div{{background:white;border:1px solid var(--line);border-radius:14px;padding:16px}}.send-summary b{{display:block;font-size:21px}}.send-summary span{{font-size:13px;color:var(--sub)}}
@media(max-width:560px){{main{{padding-top:22px}}.track-main{{align-items:flex-start}}select{{max-width:125px}}.footer-inner{{align-items:stretch;flex-direction:column;gap:8px}}.actions{{display:grid;grid-template-columns:1fr 1fr}}button.primary{{width:100%}}}}
</style></head><body><main><section id="material-step">
<header><h1>AIに渡す素材を確認</h1><p>{escape(range_text)}</p><p>自動判定は仮です。作品の意図に合わせて、素材の扱いと楽器を決めてください。</p></header>
{''.join(rows)}
<p class="note">「参照」は音楽的な背景としてAIに見せますが、変更対象にはしません。「無視」はAIへ渡しません。</p>
</section><section id="send-step" class="hidden"><header><h1>AIへ渡す内容を確認</h1><p>まだAIには送信していません。変更できる素材と、参考にするだけの素材を確認してください。</p></header><div id="send-preview"></div><p class="warning">次は録音素材の解析設定へ進みます。AI接続と実送信はまだ実装していません。</p></section>
</main><footer><div class="footer-inner"><span id="summary"></span><div class="actions"><button id="back" class="secondary hidden">戻る</button><button id="download" class="secondary hidden">JSONを保存</button><button id="next" class="primary">次へ：送信内容を確認</button></div></div></footer>
<script>
const base={payload};
function updateSummary(){{const values=[...document.querySelectorAll('.choice.active')].map(x=>x.dataset.value);document.querySelector('#summary').textContent=`使う ${{values.filter(x=>x==='use').length}}・参照 ${{values.filter(x=>x==='reference').length}}・無視 ${{values.filter(x=>x==='ignore').length}}`;}}
document.querySelectorAll('.choice').forEach(button=>button.onclick=()=>{{button.parentElement.querySelectorAll('.choice').forEach(x=>x.classList.remove('active'));button.classList.add('active');updateSummary();}});
function decisions(){{return [...document.querySelectorAll('#material-step .track')].map(row=>({{track_id:row.dataset.id,usage:row.querySelector('.choice.active').dataset.value,role:row.querySelector('select').value}}));}}
function showPreview(){{const ds=decisions();base.track_decisions=ds;const byId=Object.fromEntries(ds.map(x=>[x.track_id,x]));const included=base.tracks.filter(t=>byId[t.id].usage!=='ignore');const ignored=base.tracks.filter(t=>byId[t.id].usage==='ignore');const labels={{drums:'ドラム',bass:'ベース',guitar:'ギター',keys:'鍵盤',unknown:'未設定'}};document.querySelector('#send-preview').innerHTML=`<div class="send-summary"><div><b>${{included.length}}</b><span>AIへ渡すトラック</span></div><div><b>${{base.harmony?.available?(base.harmony.events?.length||0)+'件':'なし'}}</b><span>コード情報</span></div></div><p class="warning">変更可能と参照のみの境界は、AIへの命令にも含めます。</p>${{included.map(t=>{{const d=byId[t.id],audio=t.audio_assets?.length||0,notes=t.notes?.length||0;return `<article class="send-card"><div><h2>${{t.name}}</h2><p>${{labels[d.role]}}${{audio?'・録音 '+audio+'ファイル':''}}${{notes?'・MIDI '+notes+'ノート':''}}</p></div><strong class="badge ${{d.usage==='use'?'editable':'reference'}}">${{d.usage==='use'?'変更可能':'参照のみ'}}</strong></article>`}}).join('')}}<p>AIへ送らないトラック：${{ignored.map(t=>t.name).join('、')||'なし'}}</p>`;document.querySelector('#material-step').classList.add('hidden');document.querySelector('#send-step').classList.remove('hidden');document.querySelector('#back').classList.remove('hidden');document.querySelector('#download').classList.remove('hidden');document.querySelector('#next').textContent='次へ：録音素材の解析設定';document.querySelector('#summary').textContent='ステップ2 / 3';window.scrollTo(0,0);}}
document.querySelector('#next').onclick=()=>{{if(document.querySelector('#material-step').classList.contains('hidden')){{alert('録音素材の解析設定は次の実装範囲です。現在は送信内容の確認まで操作できます。');}}else showPreview();}};
document.querySelector('#back').onclick=()=>{{document.querySelector('#send-step').classList.add('hidden');document.querySelector('#material-step').classList.remove('hidden');document.querySelector('#back').classList.add('hidden');document.querySelector('#download').classList.add('hidden');document.querySelector('#next').textContent='次へ：送信内容を確認';updateSummary();window.scrollTo(0,0);}};
document.querySelector('#download').onclick=()=>{{base.track_decisions=decisions();const blob=new Blob([JSON.stringify(base,null,2)],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='artist-decisions.json';a.click();URL.revokeObjectURL(a.href);}};
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
