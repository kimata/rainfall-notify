# 雨降り通知アプリ

[![Regression](https://github.com/kimata/rainfall-notify/actions/workflows/regression.yaml/badge.svg)](https://github.com/kimata/rainfall-notify/actions/workflows/regression.yaml)

## 概要

センサーデータを監視して雨が降り始めたタイミングを検知し、LINE 通知と音声アナウンスで知らせる Python アプリケーションです。

### 主な機能

- 🌧️ **雨降り検知**: InfluxDB に蓄積されたセンサーデータから雨の降り始めを検知
- 🔍 **誤検知防止**: 日射量データ（600W/m² 以上）を使用した光学センサーのノイズ除去
- 📱 **LINE 通知**: 気象レーダー画像付きの通知メッセージを送信
- 🔊 **音声通知**: 設定可能な時間帯（デフォルト 7-21 時）での音声アナウンス
- 🌦️ **天気予報統合**: Yahoo 天気から3時間先までの降水量予報を取得
- ⏱️ **重複通知防止**: 30分間の重複通知抑制機能

## システム要件

- Python 3.10 以上
- InfluxDB（センサーデータ格納用）
- LINE Bot API トークン
- 音声合成サーバー（オプション）

## インストール

### 依存関係のインストール

```bash
# Rye を使用する場合（推奨）
rye sync

# または pip を使用
pip install -r requirements.txt
```

## 設定

1. 設定ファイルの作成:
   ```bash
   cp config.example.yaml config.yaml
   ```

2. `config.yaml` を編集して以下の項目を設定:
   - InfluxDB 接続情報（URL、トークン、バケット名）
   - LINE Bot API アクセストークン
   - センサー設定（雨量計、日射計）
   - 音声通知サーバー URL
   - 通知時間帯の設定

### 設定例

```yaml
influxdb:
  url: http://your-influxdb-server:8086
  token: your-influxdb-token
  bucket: sensor

notify:
  line:
    channel:
      access_token: your-line-bot-token
  voice:
    hour:
      start: 8
      end: 21

sensor:
  rain_fall:
    hostname: weather-sensor
    measure: sensor.rainfall
```

## 使用方法

### 基本実行

```bash
# メインアプリケーション実行
python src/app.py

# 設定ファイルを指定
python src/app.py -c config.yaml

# デバッグモード
python src/app.py -D

# 監視回数を制限（テスト用）
python src/app.py -n 10
```

### 監視モジュール単体実行

```bash
# 監視機能のテスト
python src/rainfall/monitor.py -c config.yaml -D
```

## 開発

### テスト実行

```bash
# テスト実行（カバレッジ付き）
rye run pytest

# カバレッジレポート確認
open tests/evidence/coverage/index.html
```

### コード品質チェック

```bash
# リント実行
rye run ruff check .

# フォーマット実行
rye run ruff format .
```

## Docker での実行

### イメージのビルド

```bash
docker build -t rainfall-notify .
```

### コンテナ実行

```bash
docker run -d \
  --name rainfall-notify \
  -v $(pwd)/config.yaml:/app/config.yaml \
  -v /dev/shm:/dev/shm \
  rainfall-notify
```

## アーキテクチャ

```
InfluxDB → Monitor → Weather APIs → Notifications
   ↓           ↓            ↓            ↓
センサーデータ  雨検知処理   天気予報取得   LINE/音声通知
```

### 処理フロー

1. **データ収集**: InfluxDB からセンサーデータ（雨量、日射量）を取得
2. **雨検知**: 雨量しきい値（0.1mm）を超過で雨開始を判定
3. **誤検知除去**: 日射量 > 600W/m² の場合は誤検知として除外
4. **天気予報取得**: Yahoo 天気から3時間先の降水量予報を取得
5. **通知送信**: LINE メッセージと音声アナウンスで通知

## 対応センサー

- 雨量計（光学式、転倒ます式）
- 日射計（誤検知防止用）

## ライセンス

MIT License

## 📝 ライセンス

このプロジェクトは Apache License Version 2.0 のもとで公開されています。

---

<div align="center">

**⭐ このプロジェクトが役に立った場合は、Star をお願いします！**

[🐛 Issue 報告](https://github.com/kimata/rainfall-notify/issues) | [💡 Feature Request](https://github.com/kimata/rainfall-notify/issues/new?template=feature_request.md) | [📖 Wiki](https://github.com/kimata/rainfall-notify/wiki)

</div>
