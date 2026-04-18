# CI/CD 遷移計劃：手動發版 → release-please 自動化

> 狀態：**Phase 1 草案** — 所有 `.new` 檔已寫齊供 user 預覽，**尚未啟用**。
> 切換由 user 決定時機。

---

## 為什麼做這件事？

目前手動發版流程痛點：
1. 每次發版要手寫 `CHANGELOG.md` 條目（容易漏、格式不一致）
2. 要手動 bump `csp_lib/__init__.py` 的 `__version__`
3. 要記得 `git tag vX.Y.Z` 再 push
4. 發版日期完全靠人力排程
5. 版本號決策容易失誤（patch vs minor vs major 界線模糊）

release-please 解決方式：
- 掃 main 上的 **conventional commits** → 自動算下個版本號
- 自動寫 `CHANGELOG.md`、bump `__version__`、推 tag
- user 只控制兩件事：**什麼 commit 合進 main**、**Release PR 什麼時候 merge**
- 發版日期 = merge Release PR 的那一刻

---

## 新流程一眼看懂

```
開發者              main 分支                  release-please (bot)          PyPI
  │                    │                              │                        │
  ├─ feat/xxx PR ─────►│                              │                        │
  │                    ├─ 偵測 conventional commit ──►│                        │
  │                    │                              │                        │
  │                    │    ◄── 更新 Release PR ──────┤                        │
  │                    │        (草稿：CHANGELOG +    │                        │
  │                    │         __version__ bump)   │                        │
  │                    │                              │                        │
  │   user merge       │                              │                        │
  │   Release PR ─────►│                              │                        │
  │                    ├─ 自動打 tag vX.Y.Z ─────────►│                        │
  │                    │                              ├─ tag 觸發 release.yml ►├─ publish
  │                    │                              │                        │
```

---

## Phase 1 交付物（已完成 ✅）

所有草案檔命名為 `*.new.*`，**不覆蓋現役檔案**，user review 後才會切換。

### 配置檔
- ✅ `release-please-config.json` — release-please 主配置（pin release-type=python）
- ✅ `.release-please-manifest.json` — pin 當前版本 `0.8.2`（防首次跑時亂 bump）

### Workflows
- ✅ `.github/workflows/ci.new.yml` — PR + push main 的 lint/test/build-check（macOS 只在 push main 跑、加 concurrency、actions pin SHA）
- ✅ `.github/workflows/release.new.yml` — tag 觸發的 PyPI publish + GitHub Release（tag pattern 嚴格化、加 RC→TestPyPI 流程）
- ✅ `.github/workflows/release-please.new.yml` — push main 自動維護 Release PR
- ✅ `.github/workflows/commitlint.new.yml` — CI 層 commit message 檢查（不只靠 pre-commit）

### Scripts
- ✅ `scripts/check_commit_msg.new.py` — 加 scope 白名單（禁版號 scope）、支援 `!` breaking marker、放行 release-please bot commits

### Agent Prompts
- ✅ `CLAUDE.new.md` — 7 段改動（branching 3 層→2 層、CHANGELOG 歸屬轉移、commit scope 規則、agent 責任、skills 表、bug fix protocol 加註、version policy 改語）
- ✅ `.claude/agents/feature-driver.new.md` — 最大改動：不指派版本號，改輸出 `commit_type + scope + bump_estimate`
- ✅ `.claude/agents/doc-organizer.new.md` — 移除 CHANGELOG 責任，docs `version:` 欄位改用 bump_estimate 推估
- ✅ `.claude/agents/architect.new.md` — 新增 breaking change 標註驗證職責
- ✅ `.claude/agents/merge-coordinator.new.md` — 只處理 feature→main，不再有 version branch / tag

### Skills
- ✅ `.claude/skills/pipeline/SKILL.new.md` — 重寫 Step 9/10（不再指派版本 → commit type；不再手寫 CHANGELOG → Release PR）
- ✅ `.claude/skills/backlog/SKILL.new.md` — 改主題分組（Active/Next Up/Exploring/Breaking Pipeline/Completed）
- ✅ `.claude/skills/changelog/SKILL.new.md` — 轉唯讀：預覽 Release PR，不再寫 CHANGELOG.md

### Backlog
- ✅ `BACKLOG.new.md` — 441 行主題分組版（已預先備好）

---

## Phase 2 — PoC 驗證（尚未執行）

建議先在 `ci/release-please-poc` 分支驗證：

1. 把 `release-please.new.yml` rename 為 `release-please.yml`（其他 `.new` 檔保持）
2. Push 一個假的 `feat(ci): test release-please bootstrap` commit
3. 確認 release-please bot 開出 Release PR，內容正確：
   - CHANGELOG 新 section 排版 OK
   - `__version__` bump 到 `0.9.0`（符合 minor）
   - manifest 更新
4. **不要** merge Release PR，只是驗證 PR 長相
5. 把 PoC 分支 close，清掉 Release PR

**停損點**：若 PoC 發現 `include-v-in-tag` / `extra-files` / `changelog-sections` 有問題，回頭調 `release-please-config.json` 再試。

---

## Phase 3 — 正式切換（user 決定時機）

切換順序（風險由低到高）：

### Step A（低風險）先拆 CI workflow
把 `ci.new.yml` + `commitlint.new.yml` 納入 main（跟 build-wheels.yml 並存），確認新 workflow 跑得起來。這段不動發版流程。

### Step B（中風險）啟用 release-please
1. `mv release-please-config.json → 保留原樣`（已在 repo root）
2. `mv .github/workflows/release-please.new.yml → release-please.yml`
3. Push 到 main
4. 等 release-please bot 開 Release PR
5. 驗證內容正確（**先不 merge**）

### Step C（高風險）切換發版路徑
1. `mv .github/workflows/release.new.yml → release.yml`
2. `rm .github/workflows/build-wheels.yml`（或先 rename 為 `.old.yml` 保留一段時間）
3. 更新 `scripts/check_commit_msg.py`：`mv check_commit_msg.new.py → check_commit_msg.py`
4. 切換 agent prompts：
   ```
   mv CLAUDE.new.md CLAUDE.md
   mv .claude/agents/feature-driver.new.md .claude/agents/feature-driver.md
   mv .claude/agents/doc-organizer.new.md .claude/agents/doc-organizer.md
   mv .claude/agents/architect.new.md .claude/agents/architect.md
   mv .claude/agents/merge-coordinator.new.md .claude/agents/merge-coordinator.md
   mv .claude/skills/pipeline/SKILL.new.md .claude/skills/pipeline/SKILL.md
   mv .claude/skills/backlog/SKILL.new.md .claude/skills/backlog/SKILL.md
   mv .claude/skills/changelog/SKILL.new.md .claude/skills/changelog/SKILL.md
   mv BACKLOG.new.md BACKLOG.md   # 注意：BACKLOG.md 是 gitignored，此步可能要改 .gitignore
   ```
5. Merge 第一個 Release PR → 產出 `v0.9.0`（或 `v0.8.3` 視 commit 內容）

### Step D（收尾）清理 v0.8.x-backup tags
```bash
git tag -d v0.8.0-backup v0.8.1-backup v0.8.2-backup
git push origin :refs/tags/v0.8.0-backup
git push origin :refs/tags/v0.8.1-backup
git push origin :refs/tags/v0.8.2-backup
```

---

## Phase 4 — 驗證（切換後第一個主題）

下個需求進來時，跑完整 pipeline：

1. `/pipeline <需求>` → feature-driver 輸出 `commit_type + bump_estimate`
2. architect → implementer → test-planner → regression-guard → doc-organizer
3. doc-organizer **不改 CHANGELOG**（驗證新規則生效）
4. Push feature branch → 開 PR → CI 綠燈
5. Merge → main
6. release-please 自動更新 Release PR（確認 CHANGELOG 條目正確）
7. user merge Release PR → tag → PyPI 發佈

若任一步出錯 → 走下方回滾。

---

## 回滾方案

各階段的回滾策略：

| 階段 | 症狀 | 回滾步驟 |
|------|------|---------|
| Phase 2 PoC 失敗 | Release PR 內容怪 / bot 不動作 | close PoC 分支，調 config 重試 |
| Phase 3 Step A | 新 ci.yml 有 bug | `rm ci.yml`，留 build-wheels.yml 繼續跑 |
| Phase 3 Step B | release-please 亂 bump 版本號 | `rm release-please.yml`，close Release PR，調 `.release-please-manifest.json` pin 正確版本 |
| Phase 3 Step C | 發版出錯 | `git revert` 切換 commit；必要時緊急 hotfix 直接手打 tag（暫退回手動流程） |
| Phase 4 實戰失敗 | agent 不配合新規則 | 把 `.new` 檔 rename 回原名（從 git history revert） |

**最終防線**：所有 `.new` 檔保留在 git history，任何時間都能 `git checkout <commit> -- <path>` 找回舊版本。

---

## Multi-File Version Bump（與 bump_version.py 對齊）

`scripts/bump_version.py` 原本會同步更新 **5 個檔、8 個位置**的版本字串。release-please 預設只改一個檔，因此在 `release-please-config.json` 的 `extra-files` 把全部納入：

| 檔案 | 位置 | Marker 形式 |
|------|------|------------|
| `csp_lib/__init__.py` | `__version__ = "..."` | `# x-release-please-version` |
| `README.md` | shields.io version badge (L5) | `<!-- x-release-please-version -->` |
| `README.md` | bibtex `version = {...}` (L178) | `% x-release-please-version` |
| `CITATION.cff` | `version: X.Y.Z` | `# x-release-please-version` |
| `NOTICE` | `(Version X.Y.Z)` | `# x-release-please-version` |
| `docs/Home.md` | `- **目前版本**: X.Y.Z` | `<!-- x-release-please-version -->` |

release-please 的 `generic` updater 會掃描每個檔案中含有 `x-release-please-version` marker 的行，把該行上的 semver 字串替換成新版本。同一行若有多個 semver，全部替換；不同行無 marker 則完全不動。

### `date-released` 例外

`CITATION.cff` 還有一個 `date-released:` 欄位，bump_version.py 原本會設為執行當下日期。release-please `generic` updater 只能 bump semver，無法改日期。解法：在 `release-please.new.yml` 加 `sync-citation-date` job，當 `release_created=true` 時自動：
1. checkout main
2. 用 Python regex 把 `date-released:` 改成今日 UTC
3. 以 `chore: sync CITATION.cff date-released ...` commit push 回 main

限制：sync commit 是 release tag 之後的 follow-up，**當次 tagged release 的 CITATION.cff 仍是舊日期**。下次 release 會帶入正確日期。追求絕對精確者可手動改後 `git tag --force`（不建議）。

### bump_version.py 的命運

release-please 接管後，`scripts/bump_version.py` 不再主動被呼叫，但**保留不刪**——用途：
1. 緊急 manual bump（release-please workflow 壞掉時的 fallback）
2. 本機開發預覽「bump 到 X.Y.Z 會改哪些地方」（`--dry-run` 模式）
3. CI_MIGRATION 的安全網，Phase 3 切換後的前兩三個 release 若 release-please 漏某個位置，手動跑此 script 補

---

## 已知相容性風險

1. **BACKLOG.md 是 gitignored**（見 memory）— 切 BACKLOG.new.md → BACKLOG.md 前需先檢查 `.gitignore`。若決定讓 BACKLOG 入版控，在 `.gitignore` 移除該條。
2. **`uv.lock` 也 gitignored**（見 memory）— 本次遷移不影響，但 CI cache key 用 `uv.lock` hash 可能有波動。
3. **cluster 模組有 bug 待 v0.10.0 修**（見 memory）— 本次遷移不動 cluster，無衝突。
4. **pre-commit hook 會同時跑 `check_commit_msg.py`** — 切換 script 時需同步更新 `.pre-commit-config.yaml` 的 hook entry（若有）。
5. **CITATION.cff `date-released` 一期落差** — 首次 release tagged 的 cff 可能是舊日期，下次 release 修正（見上節）。
6. **README.md bibtex marker 用 `%`**（bibtex 合法註解字元）— 若 bibtex 解析器嚴格要求某些格式，`% x-release-please-version` 可能被當無效 token；主流解析器（biber / bibtex / pandoc）皆能正確忽略。

---

## 記憶更新建議（切換完成後）

切換完成後，在 `~/.claude/projects/.../memory/` 下更新 `project_release_please_migration.md`：
- 從「暫停中」改為「完成」
- 記錄實際切換日期
- 記錄切換過程遇到的問題與解法（供未來 reference）
