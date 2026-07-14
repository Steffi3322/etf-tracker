# 台灣主動式 ETF 操盤動向追蹤

盤後追蹤四檔主動 ETF 持股異動。資料來源為投信官網下載的持股明細（真實股數／權重），經管理員上傳後供多人唯讀查看。

| 代號 | 名稱 |
|------|------|
| 00400A | 國泰動能高息主動 |
| 00403A | 統一升級50主動 |
| 00981A | 統一台股增長主動 |
| 00992A | 群益台灣科技創新主動 |

## 快速開始（本機）

```bash
cd etf_vibe_app
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

- 公開儀表板：首頁（唯讀）
- 管理上傳：側邊欄 **Admin**（需密碼；未設定時可用開發模式）

## 功能

- **四檔總覽**：最新異動、跨檔同步加碼、缺資料日曆、圖表
- **單檔深度分析**：區間調倉、一週矩陣、原始持股庫存、CSV 匯出
- **單檔／批次上傳**：解析投信 Excel／CSV，權重加總檢查後寫入
- **檔名推斷**：可從檔名辨識 ETF 與交易日
- **讀寫分離**：Viewer 唯讀；Admin 需密碼才能上傳／清空
- **雲端 DB（選用）**：Turso，方便多人遠端查看

> 不提供自動爬蟲／估算股數。僅接受投信官方明細檔中的真實數據。

## 多人遠端查看（部署）

```
投信官網 Excel ──(Admin 上傳)──► Turso 雲端 DB ◄── Viewer（Streamlit Cloud）
```

### 1. 建立 Turso 資料庫

1. 註冊並安裝 CLI：https://docs.turso.tech/cli
2. 建立 DB 並取得連線資訊：

```bash
turso auth login
turso db create etf-tracker
turso db show etf-tracker --url
turso db tokens create etf-tracker
```

3. （可選）匯入本機既有資料：

```bash
cd etf_vibe_app
python export_sql.py > /tmp/holdings_seed.sql
turso db shell etf-tracker < /tmp/holdings_seed.sql
```

### 2. 設定 secrets

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

```toml
ADMIN_PASSWORD = "你的強密碼"
TURSO_DATABASE_URL = "libsql://...."
TURSO_AUTH_TOKEN = "eyJ...."
```

### 3. 推上 GitHub 並部署 Streamlit Cloud

```bash
# 在專案根目錄
git remote add origin https://github.com/<你的帳號>/stock.git
git push -u origin main
```

1. 開啟 [share.streamlit.io](https://share.streamlit.io) → New app
2. Repository 選剛推上的 repo
3. Main file path：`etf_vibe_app/app.py`
4. Advanced settings → Secrets：貼上與本機相同的 `secrets.toml` 內容
5. Deploy 後把公開網址分享給其他人（唯讀）
6. 你自己用側邊欄 **Admin** 登入後上傳持股明細

> Streamlit Cloud 的本機 SQLite 無法持久保存，**多人遠端務必設定 Turso**。

## 使用流程

1. 盤後從投信官網下載持股明細
2. 依統一檔名改名（見下）→ **Admin** → 上傳持股
3. 確認權重加總合理後寫入
4. 其他人開啟公開首頁查看異動與缺資料日曆

### 統一檔名（建議固定使用）

格式：`{ETF代號}_{YYYYMMDD}.xlsx`

| 範例 | 自動歸檔 |
|------|----------|
| `00400A_20260709.xlsx` | 00400A · 2026-07-09 |
| `00403A_20260709.xlsx` | 00403A · 2026-07-09 |
| `00981A_20260709.xlsx` | 00981A · 2026-07-09 |
| `00992A_20260709.xlsx` | 00992A · 2026-07-09 |

仍相容舊格式（如 `國泰動能_2026-07-09.xlsx`），但日常請用統一檔名最穩。

### Parser 行為

1. 優先依表頭欄位（代號／名稱／權重／股數）解析
2. 失敗則回退啟發式列掃描
3. 寫入前檢查股票權重加總（現金部位會使加總低於 100%，約 90–105% 視為可接受）

## 專案結構

```
etf_vibe_app/
├── app.py              # 公開 Viewer
├── pages/1_Admin.py    # 管理後台（單檔／批次上傳）
├── db.py               # SQLite / Turso
├── parser.py           # Excel/CSV 解析 + 權重檢查
├── analysis.py         # 區間 diff、策略標籤
├── dashboard.py        # 四檔總覽 + 缺資料日曆
├── views.py            # 單檔深度分析
├── auth.py             # 管理密碼
└── .streamlit/         # 主題與 secrets 範例
```
