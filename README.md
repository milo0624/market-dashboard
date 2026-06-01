# 市場早報 — GitHub Actions 設定說明
# 請幫忙的人照以下步驟操作，約 15 分鐘

---

## 準備：需要的東西
- GitHub 帳號（到 github.com 用 Google 登入註冊，免費）
- 這個資料夾的所有檔案

---

## 步驟一：建立 GitHub Repo

1. 登入 github.com
2. 右上角「+」→「New repository」
3. Repository name 填：`market-dashboard`
4. 選「Public」
5. 不要勾任何東西，直接點「Create repository」

---

## 步驟二：上傳檔案

在剛建立的 repo 頁面：

1. 點「uploading an existing file」
2. 把整個資料夾內的**所有檔案與資料夾**拖進去
   （注意：`.github` 資料夾也要上傳，它是隱藏資料夾，記得顯示隱藏檔案）
3. 點「Commit changes」

---

## 步驟三：設定富邦 API 密鑰（Secrets）

這步最重要，密鑰不會公開：

1. 進入 repo 頁面 → 上方「Settings」
2. 左側「Secrets and variables」→「Actions」
3. 點「New repository secret」，依序新增三個：

   | Name | Value |
   |------|-------|
   | `FUBON_ID` | 富邦帳號的身分證字號 |
   | `FUBON_PASSWORD` | 富邦網路下單密碼 |
   | `FUBON_CERT_PW` | 富邦憑證密碼 |

---

## 步驟四：開啟 GitHub Pages

1. repo 頁面 → 上方「Settings」
2. 左側「Pages」
3. Source 選「Deploy from a branch」
4. Branch 選「gh-pages」，資料夾選「/ (root)」
5. 點「Save」

---

## 步驟五：手動跑一次測試

1. repo 頁面 → 上方「Actions」
2. 左側點「每日市場資料更新」
3. 右側「Run workflow」→「Run workflow」
4. 等約 2 分鐘，看到綠色勾勾 = 成功

---

## 步驟六：取得 App 網址

格式為：
```
https://你的GitHub帳號.github.io/market-dashboard/
```

把這個網址傳給手機使用者，用 Safari 開啟後：
- 分享 → 加入主畫面 → 新增

---

## 之後全自動

每天週一到週五早上 08:00，GitHub 自動：
1. 執行 fetch_market.py
2. 呼叫富邦 Neo API 抓資料
3. 更新 data.json
4. 重新部署 App

手機 App 每次開啟都會讀最新的 data.json，顯示當日資料。

---

## 常見問題

**Actions 跑失敗（紅色叉叉）？**
→ 點進去看 log，最常見原因是富邦 Secrets 輸入錯誤，重新確認三個密鑰。

**gh-pages branch 不存在？**
→ Actions 第一次跑完後才會自動建立，再去 Pages 設定選一次。

**App 顯示「占位資料」？**
→ Actions 還沒跑過，或富邦登入失敗，看 Actions log 確認。
