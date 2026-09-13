# Studio One Integration Architecture

Status: Architecture Decision  
Date: 2026-09-13

## 結論

Artist AI Production Systemは、Studio Oneへ読み込めるVST3プラグインとして提供する。ただし実装は、VST3本体・ローカル解析サービス・DAWproject Bridgeの3層構成とする。

## なぜVST3単体にしないか

Steinberg公式説明では、VST3はホストから供給される音声またはイベントのストリームを処理するコンポーネントであり、ホストから見れば任意数のAudio/Event入出力とパラメータを持つブラックボックスである。チャンネル名や色など一部のChannel Contextは取得できるが、プロジェクト全体の任意トラックやDAW固有コードトラックを列挙・編集する標準APIとは定義されていない。

本製品が必要とする「複数トラックを横断した解析」「長時間の音高推定」「外部AI通信」をオーディオ処理コールバックへ載せると、リアルタイム処理を阻害する。そのため重い処理を別プロセスへ分離する。

## 構成

| 層 | 主な責任 |
|---|---|
| VST3 Plug-in | Studio One内のUI、現在チャンネルのAudio/Event受信、結果表示、試聴 |
| Local Analysis Service | pYIN、Basic Pitch、コード照合、Artist確定値、AI接続、提案検証 |
| DAWproject Bridge | トラック、クリップ、Warp、録音素材、MIDIのプロジェクト文脈取得 |
| MIDI Delivery | 標準MIDIファイル生成、DAWへのドラッグ＆ドロップ／取り込み |

## データフロー

1. Studio OneプロジェクトをDAWprojectとして渡す、またはVST3へ対象チャンネルを再生して入力する。
2. Local Analysis Serviceが録音とMIDIを解析する。
3. VST3 UIにコード・Bass・Guitarの解析結果を表示する。
4. Artistが解析値を修正し、固定／提案可を確定する。
5. ユーザー所有のAIへProducer Requestを送る。
6. Authority Validation Gateを通過した提案だけをVST3 UIに返す。
7. 採用案をMIDIとしてStudio Oneへ取り込む。

## MVPで保証するStudio One連携

- Windows版Studio OneでVST3として認識・起動できる
- プラグイン画面からLocal Analysis Serviceへ接続できる
- DAWprojectを選択して解析できる
- Artistの修正・確定・AI依頼・提案比較をプラグイン画面内で完結できる
- 採用結果を標準MIDIとしてStudio Oneへ戻せる

## MVPで保証しないこと

- VST3だけでStudio One内の全トラックを自動走査すること
- Studio One固有コードトラックの自動取得
- Studio Oneの既存イベントをVST3から直接書き換えること
- AI通信や音高解析をリアルタイムオーディオスレッドで実行すること

## 配布とライセンス

Steinberg VST3 SDKは現在MIT Licenseで提供され、条件を守れば商用製品を含む利用・改変・再配布が可能。VST名称・ロゴを使う場合は別途Trademark Usage Guidelinesへ従う。

## Primary sources

- Steinberg, VST3 SDK: https://github.com/steinbergmedia/vst3sdk
- Steinberg VST3 SDK README, plug-in model and capabilities: https://github.com/steinbergmedia/vst3sdk#about-vst-plug-ins-in-general
- Steinberg VST3 SDK license and usage guidance: https://github.com/steinbergmedia/vst3sdk#license--usage-guidelines
