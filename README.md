# Artist AI Production System

> Artist owns the taste. AI expands the possibilities.

DAW上で制作するArtistの感性・知識・経験を、AI Producer & Engineerによって拡張する音楽制作支援システムです。

このプロジェクトは、言葉から完成曲を生成する自動作曲ツールではありません。制作途中の楽曲をAIが分析し、Artistが選んだ制作方針に沿って、比較・編集可能なMIDI案を生成することを目指します。

## Core principles

- 人間はArtist、AIはProducer & Engineer
- 感性、制作方針、採否はArtistが決める
- AIは分析、探索、試作、打ち込みを高速化する
- 知識や指示の解像度が高いほど、出力も高度になる
- 生成結果はDAW上で編集可能にする
- 「誰でもプロっぽい曲」ではなく、Artistの能力を増幅する
- Studio Oneで検証するが、コアは特定DAWへ依存させない
- MIDIと録音オーディオが混在する制作を前提とする
- 将来の一般配布を前提に設計する

## Current status

Product definition / portable architecture / technical validation

## Documentation

- [製品憲法・意思決定ログ](docs/product-constitution.md)
- [V0.1アーキテクチャ](docs/v0.1-architecture.md)

## Initial technical direction

V0.1はDAWproject、Standard MIDI File、Audio stems、コード情報を共通Music Contextへ変換し、4〜8小節の既存アンサンブルに対して複数の編集可能なMIDI案を返すクロスプラットフォームのデスクトップ型プロトタイプとして検証します。
