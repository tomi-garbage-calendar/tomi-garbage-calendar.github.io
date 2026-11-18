# 東御市ごみ収集カレンダー
Tomi City Garbage Collection Calendar

長野県東御市の非公式ごみ収集カレンダーです。収集日程、分別方法、排出場所などを分かりやすく案内します。

An unofficial garbage collection calendar for Tomi City, Nagano, Japan. Provides information on collection schedules, waste sorting, and disposal locations.

**非公式 / Unofficial:** 本プロジェクトは東御市が運営・公認するものではありません。  
This project is neither operated nor endorsed by the City of Tomi.

## 公式PDFの更新確認と公開

一次情報源は[東御市の市民カレンダー掲載ページ](https://www.city.tomi.nagano.jp/category/gomi/150910.html)です。GitHub Actions は毎日 06:23（日本時間）を目安に、掲載中の各年度のPDFを取得します。確認済みデータの出典と SHA-256 が一致する年度は解析を省略します。確認待ちのPDFも、同じ抽出コードとハッシュの解析結果が Actions キャッシュにあれば再利用します。

### 確認から公開まで

1. 更新確認ワークフローの実行結果から `calendar-review` を取得します。年度別の `*-report.html` で追加・削除と警告を確認し、公式PDFと照合します。 `*-report.json` には PDFページ番号、日付欄の座標、抽出テキスト、画像識別子、図形数、利用時のOCR結果があります。
2. `*-candidate.json` がある場合は、確認後にワークフローのサマリーに記載された SHA-256 を指定して次を実行します。取得時から公式PDFが更新されていれば登録は失敗します。

   ```sh
   python -m pip install -r requirements.txt
   python scripts/pipeline.py approve 2026-candidate.json <候補ファイルのSHA-256>
   ```

3. 生成された `data/approved/2026.json` をコミットし、PRで確認して `main` にマージします。初回のみリポジトリの **Settings → Pages → Build and deployment → Source** を **GitHub Actions** に設定します。PRではビルドを検証し、`main` へのマージ後、掲載中の全PDFのハッシュを確認済みデータと照合してからデプロイします。取得・解析・検証の失敗時や未確認の更新が残っている間は、既存の公開サイトが引き続き配信されます。 [GitHub Pages のカスタムワークフロー](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)

確認済みのJSONは年度ごとに保持します。公式ページから掲載が終了した年度もサイトと地区別ICSに含まれます。1〜3月は翌年の暦日として扱います。ICSは全年度を含む終日予定で、地区・日付・品目ごとに安定したUIDを付けています。

### 抽出とローカル実行

令和8年度の公式PDF 3種類（各6ページ、1ページに2か月）で版面を確認しました。日付のフォント・座標と暦上の曜日を照合し、各日付欄内の品目テキスト、埋め込み画像、ベクター図形を解析します。もやせるごみ・生ごみには画像を含む複合図柄があり、北御牧の金物・陶器等とトレー等は画像と地区表記から対象区域を特定します。地区名付きの資源回収は該当地区の予定にします。休日受入も日付付きの予定として扱います。

未対応の小型の図柄やラベル、テキスト層の欠落を検出した場合は、日本語の Tesseract OCR を確認用に実行します。版面や図柄に変更があり解析できなければ、公式PDFを照合して抽出ルールを更新し、更新確認を再実行します。ローカルでOCRを実行するには `tesseract` コマンドと日本語モデル `jpn` が必要です。

```sh
python -m pip install -r requirements.txt
python scripts/pipeline.py check
python scripts/build.py dist
```

確認用ファイルは `.work/review/` に生成されます。公開用ビルドは確認済みJSONがある場合に実行でき、空の出力先に地区別ページ、地区別ICS、年度別JSONを生成します。

ICSだけを生成する場合は `python scripts/generate_ics.py .work/ics` を実行します。公開後は地区別ページと GitHub Actions のデプロイ結果に購読用のHTTPS URLが表示されます。カレンダーアプリの「URLで追加」にそのURLを指定すると、同じURLで年度更新を受け取れます。

トップページでは、東御市の現地日付（日本時間）で今日・明日・明後日の予定を確認できます。選択した地区はブラウザに保存されます。トップページの文言は `site/calendar.js` の言語別辞書で管理し、地区名と品目は年度別JSONの表記を使用します。
