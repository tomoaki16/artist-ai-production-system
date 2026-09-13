# 録音楽器の音程・発音解析 技術選定

## 結論

録音ベースの単音解析は **librosa pYINを主解析器**、Spotify Basic Pitchを将来のクロスチェック候補とする。録音ギターの多音解析は **Basic Pitch ONNXを第一候補**とする。現在の自作autocorrelation解析は、強い倍音へ固定されて4小節を同一音として扱う失敗が確認されたため、音程判断には使用しない。

製品へ組み込むライセンス範囲は、リスク回避を優先してISC、MIT、BSD、Apache-2.0等のpermissive licenseを原則とする。GPLv3のaubio、AGPLv3または商用契約のEssentiaは採用しない。

## 必要な解析能力

本製品が必要としているのは、録音全体の代表周波数ではない。最低限、次のnote eventが必要である。

- プロジェクト上の開始位置（小節・拍）
- 終了位置または長さ
- MIDI note numberと音名
- confidence
- onset confidence / voiced probability
- bend、slide、vibrato等による連続音高変化
- 元のWAV、クリップ、解析器、解析器バージョン

ベースは原則monophonicだが、倍音、ピッキングノイズ、スライド、ミュート、音の重なりによってオクターブ誤認や短い誤検出が起きる。したがってframe単位のF0をそのままAIへ渡さず、onsetによる区切り、Viterbi平滑化、短音除去、音域制約、コードとの整合性を別段階で検証する。

ギターは和音を含むため、単一F0推定器だけでは解析できない。multi-pitchとonsetを同時に扱うAutomatic Music Transcription（AMT）が必要になる。

## 候補比較

| 候補 | 主用途 | 多音 | ライセンス | 配布評価 | 結論 |
|---|---|---:|---|---|---|
| librosa pYIN | 単音F0、voicing | 不可 | ISC | 条件が軽い。依存ライセンス管理は必要 | ベース主解析に採用 |
| Spotify Basic Pitch | note onset/offset、multi-pitch、MIDI | 可 | Apache-2.0 | NOTICE・LICENSE同梱等が必要 | ギター第一候補、ベース補助 |
| ONNX Runtime | Basic Pitch推論 | ― | MIT | copyright/license notice保持 | 推論基盤候補 |
| torchcrepe | 単音F0 | 不可 | MIT | PyTorchが重い。weights由来も固定版で監査が必要 | 比較候補に留保 |
| aubio | onset、pitch、notes | 単音中心 | GPLv3+ | 閉鎖的な商用配布と相性が悪い | 不採用 |
| Essentia | MIR全般 | 一部 | AGPLv3 / commercial | ソース公開または商用契約の検討が必要 | 不採用 |

## librosa pYIN

librosaはISC Licenseで公開され、pYIN、YIN、pitch tracking、onset detectionを提供する。pYINはYINからF0候補と確率を計算し、Viterbi decodingで最も可能性の高いF0系列とvoicingを推定する。これは、単純なautocorrelationで起きやすい倍音固定と急激なオクターブ飛びを抑える用途に適している。^1 ^2

実装上はベースの想定音域を例えばE1〜G4に制限する。5弦ベース、ダウンチューニング、カポ等ではArtistの設定で範囲を変更できるようにする。pYINの結果は連続F0であるため、別途onset detectionと組み合わせてnote eventへ変換する。

### 検証

倍音を含む1秒ずつの合成ベース `E2 → G♯2 → A2 → B2` に対し、pYINは各区間の中央値をMIDI `40 → 44 → 45 → 47` と正しく検出した。voiced率は1.0、voiced probability中央値は0.946だった。この結果は合成音に対する技術動作確認であり、実録音に対する精度保証ではない。

### ライセンス対応

librosa本体は、copyright noticeとpermission noticeを全コピーに表示することを条件に、使用・複製・変更・配布を有償無償で許可するISC Licenseである。^3 配布物に`THIRD_PARTY_NOTICES`を設け、librosaのcopyrightとISC全文を収録する。

ただし、Python packageの依存にはNumPy、SciPy、numba、soundfile等が含まれる。最終バイナリへ同梱する全依存をSBOMとlicense scannerで固定版ごとに確認する。特にlibsndfileを同梱する場合はLGPL条件を別途満たす必要がある。PCM WAVは現在の自前readerで読み、soundfileの利用範囲を減らす設計を維持する。

## Spotify Basic Pitch

Basic Pitchはinstrument-agnosticな軽量AMTで、frame-wise onset、multi-pitch、note activationを共同推定する。公式説明ではpolyphonic instrumentを扱い、1つの楽器だけを録音した素材で最もよく機能する。本製品のステム単位のギター解析と一致する。^4 ^5

公式Python packageはMac、Windows、UbuntuとPython 3.7〜3.11を対応環境として掲げ、TensorFlow、CoreML、TFLite、ONNXモデルを含む。公式版0.4.0の依存定義はPython 3.11以降のLinuxでTensorFlow `<2.15.1` を要求するため、Python 3.12では通常インストールが解決しないことを確認した。一方、`--no-deps`でpackageを導入しONNX Runtime等を個別導入すると、Python 3.12でもONNX modelの読み込みと推論は動作した。これは公式サポート外構成なので、そのまま製品依存にはしない。^4 ^6

### 検証

同じ合成ベースに対し、Basic PitchはE2、G♯2、A2、B2を検出した。ただしG♯2が複数note eventへ分割され、開始直後に短いB3誤検出が出た。したがってnote length、confidence、同音間gapに基づくpost-processingが必須である。実測推論はCPUで数秒以内だったが、起動・model load時間と配布サイズは別途評価する。

### ライセンス対応

Basic PitchはApache License 2.0で、copyright licenseとpatent licenseを含む。再配布時はLICENSEの提供、変更ファイルへの変更表示、copyright・patent・trademark・attribution noticeの保持、付属NOTICEの内容を配布物のNOTICEまたはdocumentation等へ含める必要がある。Spotify名称・商標の使用許諾ではない。^7

公式NOTICEにはBasic Pitchのほか、librosa、mir_eval、NumPy、pretty-midi、resampy、SciPy、TensorFlow等のattributionが列挙されている。採用する実行経路だけでなく、実際に配布するpackage/modelに対応するnoticeを保持する。^8

## 除外候補

### aubio

aubioはonset、pitch、MIDI-like note、quiet/loud regionを提供し、Windows/macOS/Linuxで構築できる。しかし公式repositoryはGPLv3-or-laterである。将来の配布形態を閉鎖ソースにも開いておくというリスク回避方針に合わないため、実装へ組み込まない。^9

### Essentia

Essentiaの公式licensing informationは、非商用向けopen licenseをAGPLv3とし、商用用途にはcommercial licenseを案内している。将来の一般・有料配布で契約または強いcopyleft対応が必要になるため、現段階では採用しない。^10

### torchcrepe

torchcrepeはMIT Licenseで、Viterbi decoding、periodicity、thresholdingを提供し、double/half-frequency errorへの対策も明記する。ただしmonophonic専用でBasic Pitchと役割が重なり、PyTorchの配布サイズが大きい。repositoryはmodel weightsをoriginal CREPEから変換したと説明しているため、採用時はweightsを含む固定releaseのprovenanceとnoticeを再監査する。現段階では採用しない。^11

## 採用アーキテクチャ

解析器は交換可能なadapterにする。

1. `MonophonicPitchAdapter`: librosa pYIN
2. `PolyphonicTranscriptionAdapter`: Basic Pitch ONNX
3. `OnsetAdapter`: librosa onset strength/detect
4. `PostProcessor`: 音域制約、短音除去、同音結合、拍への量子化候補
5. `MusicContextMapper`: clip offset、playStart、tempo mapを使いproject beatへ変換
6. `Validation`: コード構成音との一致は補正ではなくdiagnosticとして表示

AIへ渡す値には`engine`、`engine_version`、`model_hash`、`confidence`、`source_asset`、`source_time`、`project_time`を持たせる。コードと合わない音を自動修正してはいけない。演奏ミスか意図的な経過音かを決めるのはArtistである。

## 実装順序

1. 現在のautocorrelation pitch結果をAI入力から外す
2. pYINによるframe-wise F0とvoicingを追加
3. onset＋F0からベースnote eventsを生成
4. synthetic fixtureと手動正解ラベル付き実録音fixtureで評価
5. Basic Pitch ONNX adapterをoptional engineとして追加
6. ギター単音、パワーコード、triad、ストロークで評価
7. third-party notices、SBOM、model hash、license CIを追加
8. Windows/macOSの署名済みbuildで依存物を再監査

## 合格基準

ライブラリを採用しただけでは合格にしない。

- ベースのnote onset F1、note with onset F1、pitch accuracyを測定
- E1〜G4でoctave errorを別集計
- slide、hammer-on、mute、sustain、noiseをfixture化
- 4〜8小節を実用時間内で解析
- confidenceが低いnoteをUI上で区別
- 元録音と推定MIDIを同時試聴できる
- Artistが音名を修正でき、修正履歴を保持
- 全同梱dependency/modelのlicense inventoryがCIで生成される

## 法務・運用上の注意

本書は技術上のライセンス調査であり法律意見ではない。公開・販売前には固定したdependency lockfile、配布バイナリ、model file、installerを対象に専門家または社内法務の確認を行う。開発中にpermissive licenseだったprojectが将来変更される可能性があるため、versionとartifact hashを固定する。

## Sources

1. librosa, [Pitch and tuning API](https://librosa.org/doc/main/api/pitch.html), accessed 2026-09-13.
2. Mauch and Dixon, [pYIN: A Fundamental Frequency Estimator Using Probabilistic Threshold Distributions](https://archives.ismir.net/ismir2014/paper/000286.pdf), ISMIR 2014.
3. librosa development team, [librosa ISC License](https://github.com/librosa/librosa/blob/main/LICENSE.md), 2026.
4. Spotify, [Basic Pitch repository and documentation](https://github.com/spotify/basic-pitch), accessed 2026-09-13.
5. Bittner et al., [A Lightweight Instrument-Agnostic Model for Polyphonic Note Transcription and Multipitch Estimation](https://arxiv.org/abs/2203.09893), ICASSP 2022.
6. Spotify, [Basic Pitch pyproject.toml](https://github.com/spotify/basic-pitch/blob/main/pyproject.toml), version 0.4.0 metadata.
7. Spotify, [Basic Pitch Apache-2.0 License](https://github.com/spotify/basic-pitch/blob/main/LICENSE), accessed 2026-09-13.
8. Spotify, [Basic Pitch NOTICE](https://github.com/spotify/basic-pitch/blob/main/NOTICE), accessed 2026-09-13.
9. aubio project, [aubio repository—GPLv3-or-later license statement](https://github.com/aubio/aubio), accessed 2026-09-13.
10. Music Technology Group, Universitat Pompeu Fabra, [Essentia Licensing](https://essentia.upf.edu/licensing_information.html), accessed 2026-09-13.
11. maxrmorrison, [torchcrepe repository](https://github.com/maxrmorrison/torchcrepe), accessed 2026-09-13.
12. Microsoft, [ONNX Runtime MIT License](https://github.com/microsoft/onnxruntime/blob/main/LICENSE), accessed 2026-09-13.
