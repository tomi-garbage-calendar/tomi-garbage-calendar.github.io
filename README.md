# 東御市ごみ収集カレンダー
Tomi City Garbage Collection Calendar

長野県東御市の非公式ごみ収集カレンダーです。収集日程、分別方法、排出場所などを分かりやすく案内します。

An unofficial garbage collection calendar for Tomi City, Nagano, Japan. Provides information on collection schedules, waste sorting, and disposal locations.

**非公式 / Unofficial:** 本プロジェクトは東御市が運営・公認するものではありません。  
This project is neither operated nor endorsed by the City of Tomi.

## ローカルでプレビューする

リポジトリのルートで確認済みJSONからサイトを生成し、ローカルのHTTPサーバーで開きます。プレビューの生成にはPythonがあれば実行できます。

```sh
python scripts/build.py dist
python -m http.server 8000 --bind 127.0.0.1 --directory dist
```

ブラウザで [http://127.0.0.1:8000/](http://127.0.0.1:8000/) を開き、地区を選択してください。`site/index.html` を直接開くとブラウザがJavaScriptモジュールをブロックします。また、カレンダーが読み込む `data/index.json` と年度別のJSONはビルド時に生成されます。再ビルドする場合は空の出力先を指定してください。

## 公式PDFの更新確認と公開

一次情報源は[東御市の市民カレンダー掲載ページ](https://www.city.tomi.nagano.jp/category/gomi/150910.html)です。GitHub Actions は毎月1日 09:23（日本時間）を目安に、掲載中の各年度のPDFを確認します。必要なときは手動でも実行できます。確認済みデータの出典と SHA-256 が一致する年度は解析を省略します。確認待ちのPDFも、同じ抽出コードとハッシュの解析結果が Actions キャッシュにあれば再利用します。

### 確認から公開まで

1. 新しい確認候補があると、更新確認ワークフローがレビュー用Issueを作成します。Issueのリンクから `calendar-review` を取得し、`*-report.html` の追加・削除を公式PDFと照合します。
2. 承認する場合は、リポジトリへの書き込み権限を持つアカウントで、そのIssueに **`/approve`** とだけコメントします。Actionsが候補と現在の公式PDFのハッシュを検証し、`data/approved/<年度>.json` を `main` に登録してPagesの公開を開始します。

初回はリポジトリで **Issues** を有効にし、 **Settings → Pages → Build and deployment → Source** を **GitHub Actions** に設定します。`main` への直接書き込みをルールで禁止している場合は、下記の手動登録とPRを使用します。取得・解析・検証の失敗時や未確認の更新が残っている間は、既存の公開サイトが引き続き配信されます。 [GitHub Pages のカスタムワークフロー](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)

### 手動で登録する場合

候補を確認後、ワークフローのサマリーに記載された SHA-256 を指定します。生成された確認済みJSONをPRで `main` にマージします。

   ```sh
   python -m pip install -r requirements.txt
   python scripts/pipeline.py approve 2026-candidate.json <候補ファイルのSHA-256>
   ```

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
