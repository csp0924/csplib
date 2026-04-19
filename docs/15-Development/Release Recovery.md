---
tags:
  - type/guide
  - status/complete
created: 2026-04-20
updated: 2026-04-20
---

# Release Recovery SOP

`release.yml` 在 tag push 後可能在不同階段失敗，**處理方式取決於失敗點**。
最大原則：**PyPI 版本號 immutable**（用過就燒掉，即使 yank 也不能重發同一個 `X.Y.Z`），
所以一切恢復策略都圍繞「保護版本號不被誤燒」。

---

## Job 拓樸

```
preflight ──┬─▶ test (3 OS)  ──┐
            ├─▶ build dist     ├─▶ publish-pypi ──▶ create-gh-release
            └─▶ notes          ┘  (environment: pypi)
```

`publish-pypi` 之前的所有 fail 都**沒有燒版本號**（PyPI 沒收到任何檔案）。
`publish-pypi` 開始執行就進入危險區。

---

## 失敗情境對照表

| 失敗點 | PyPI 狀態 | tag 狀態 | GH Release | 燒版本號？ | 嚴重度 |
|--------|-----------|---------|-----------|-----------|--------|
| `preflight` | 沒發 | 已存在 | 無 | 否 | 低 |
| `test` (3 OS) | 沒發 | 已存在 | 無 | 否 | 低 |
| `build` | 沒發 | 已存在 | 無 | 否 | 低 |
| `notes` | 沒發 | 已存在 | 無 | 否 | 低 |
| `publish-pypi`（environment 等待 approve）| 沒發 | 已存在 | 無 | 否 | 低 |
| `publish-pypi` upload 中失敗 | **可能部分成功** | 已存在 | 無 | **可能** | 高 |
| `create-gh-release` | 已發 | 已存在 | 無 | 是（已成功） | 中 |

---

## 情境 1：publish 之前 fail（preflight / test / build / notes）

**不要刪 tag、不要 force push。** release-please 以「最後一個有效 tag」為基準計算下個版本。

### 步驟

1. **看 GitHub Actions log**，確認 fail 的 root cause。
2. **開 `fix:` PR 修問題、merge 到 main**。
3. release-please 偵測到「main 上有新 commit」→ 自動更新 Release PR，**版本號自動 bump 到下個 patch**：
   - 若失敗的是 `v1.0.0`，新 Release PR 會是 `v1.0.1`
4. 一切如常 merge Release PR → 新 tag → 重跑 release.yml。

### 後果

- `v1.0.0` tag 留在 GitHub repo，但 PyPI 上不存在這個版本（**版本號跳號**）。
- 使用者 `pip install csp0924-lib==1.0.0` 會失敗，這是預期行為。
- 可選清理：到 GitHub repo Releases 頁面，把 `v1.0.0` draft release 刪掉（或標 pre-release 並加說明）。

### 為什麼不刪 tag 重發？

- 刪 tag 後 release-please 會重算，但**它的 manifest 已經寫了 `1.0.0`**，不會自動往回。
- 強行讓 release-please 回到 `1.0.0` 需要手動改 `.release-please-manifest.json` + `CHANGELOG.md`，容易出錯。
- 跳號是最便宜的選項。

---

## 情境 2：publish-pypi 卡在 environment approval

這是設計好的人工關卡。如果 test 已綠但你看到 log 有疑慮（例如某個測試只是 flaky 過了），**不要 approve**：

### 選項 A：先 approve，發出去再說

適用於：你檢查過 fail 是 noise（網路 flaky / 已知 retry 過綠）。

### 選項 B：reject 並進入「跳號」流程

1. 在 GitHub Actions 該 run 頁面，**reject** environment approval（cancel run）。
2. 之後處理同情境 1（開 fix PR → 跳號到 `v1.0.1`）。

---

## 情境 3：publish-pypi upload 中失敗（最危險）

可能原因：網路斷線、PyPI 上游故障、attestations 簽名失敗。

### 先確認 PyPI 收到什麼

到 https://pypi.org/project/csp0924-lib/#history 查看：

#### 狀況 3a：什麼都沒收到

PyPI 端沒留下任何檔案 → 等同情境 1，**版本號沒燒**。
- 處理：跳號到下個 patch（同情境 1 步驟）。

#### 狀況 3b：部分檔案上傳了（例如 wheel 上去但 sdist 沒）

**版本號已燒**。即使 yank 也不能重發 `X.Y.Z`。
- 處理：
  1. 把已上傳的檔案 **yank**（管理介面 → release → Options → Yank release）。
     yank 不會刪檔案，但 `pip install` 預設不會選 yanked 版本。
  2. 跳號到下個 patch（同情境 1 步驟），重發為 `v1.0.1`。
  3. 在 `CHANGELOG.md` 對應 section 加註：「v1.0.0 was yanked due to incomplete upload, use v1.0.1 instead」。
     （release-please 會把 `v1.0.0` section 留下來；手動加 yanked 註解即可。）

#### 狀況 3c：完整上傳但後續 step（如 attestation）fail

**版本號已燒、檔案完整可裝**。
- 處理：
  1. 看 fail 的 step 是什麼。如果只是 GH Release 創建失敗，手動補（情境 4）。
  2. 如果是嚴重瑕疵（例如 attestation 沒簽成功），yank 後跳號（同 3b）。

---

## 情境 4：publish-pypi 成功但 create-gh-release fail

PyPI 已經發了，使用者裝得到。只差 GitHub Release 沒建。

### 手動補 GitHub Release

```bash
# 用 gh CLI 補建 release（從 CHANGELOG 取 notes）
TAG=v1.0.0
python3 -c "
import re
content = open('CHANGELOG.md', encoding='utf-8').read()
m = re.search(rf'## \[{re.escape(\"${TAG#v}\")}\].*?\n(.*?)(?=\n## \[|\Z)', content, re.DOTALL)
print(m.group(1).strip() if m else f'Release ${TAG}')
" > release_notes.md

# 從 release.yml 的 build artifact 下載 dist/，或本機 build
gh release create "$TAG" \
  dist/*.whl dist/*.tar.gz \
  --title "$TAG" \
  --notes-file release_notes.md
```

或直接重跑 release.yml（手動 workflow_dispatch；但要小心 publish-pypi 會 skip 因為 PyPI 已存在版本）。

---

## 預防措施

### 1. environment: pypi 必設 Required reviewers

到 GitHub repo **Settings → Environments → pypi → Required reviewers** 加自己。
這樣 publish-pypi 開始前會 prompt approve，給你機會 review test/build log。

### 2. 平常 PR 階段就壓低 flaky test 風險

release.yml 的 test 跟 PR CI 跑同樣的測試，PR 階段就把 flaky 修乾淨能減少 release-time fail。
參考 `bug_lessons/async_test_state_race.md`。

### 3. tag 推上去前先 dry-run（RC 走 TestPyPI）

要發大版本（major bump 或重大 minor）前，可以先打 RC tag：

```bash
git tag v1.0.0-rc1
git push origin v1.0.0-rc1
```

這會走 TestPyPI 流程（不影響正式 PyPI），驗證整條 publish 鏈路 OK 再打正式 tag。
**注意**：RC tag 走 release-please 的話會被 manifest 規範擋掉，要手動打。

---

## 相關檔案

- `.github/workflows/release.yml` — release pipeline 本身
- `.github/workflows/release-please.yml` — Release PR 維護 + tag 自動產生
- `release-please-config.json` / `.release-please-manifest.json` — release-please 狀態
- `bug_lessons/ci_release_please_pitfalls.md` — release-please 從手動版控遷移時的踩雷合輯
