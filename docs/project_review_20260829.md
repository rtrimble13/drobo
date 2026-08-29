# Project Review — drobo — 2026-08-29

## Status

Every finding in this report has been fixed on
`claude/project-review-enhancements-cl1baz` -- all four P0 defects, all eight
P1 findings, both P2 items, and every below-cap item.

Test count went from 55 to 131; `src/drobo/dropbox_client.py` went from 0% to
86% line coverage and the project total is 78%, measured on every run with a
70% floor. Every fix carries a regression test that was confirmed to fail
against the unfixed source.

Findings below are left as written at review time; each links to its issue.

| Finding | Issue | Status |
|---|---|---|
| `ls` with no PATH always fails | [#13](https://github.com/rtrimble13/drobo/issues/13) | Fixed |
| `download_file` truncates destination | [#14](https://github.com/rtrimble13/drobo/issues/14) | Fixed |
| `ls -t` crashes on mixed listings | [#15](https://github.com/rtrimble13/drobo/issues/15) | Fixed |
| `cp` masks every failure | [#16](https://github.com/rtrimble13/drobo/issues/16) | Fixed |
| Refresh-token-only rejected; interactive OAuth | [#17](https://github.com/rtrimble13/drobo/issues/17) | Fixed |
| No retry or backoff | [#18](https://github.com/rtrimble13/drobo/issues/18) | Fixed |
| `AuthError` raises TypeError | [#19](https://github.com/rtrimble13/drobo/issues/19) | Fixed |
| Publish workflow cannot publish | [#20](https://github.com/rtrimble13/drobo/issues/20) | Fixed |
| `.droborc` world-readable | [#21](https://github.com/rtrimble13/drobo/issues/21) | Fixed |
| Retry drops kwargs | [#22](https://github.com/rtrimble13/drobo/issues/22) | Fixed |
| `dropbox_client.py` untested | [#23](https://github.com/rtrimble13/drobo/issues/23) | Fixed (0% → 85%) |
| Duplicate `ConfigManager` | [#24](https://github.com/rtrimble13/drobo/issues/24) | Fixed |
| Docs contradict code | [#25](https://github.com/rtrimble13/drobo/issues/25) | Fixed |
| Whole-file buffering (>150 MB) | [#26](https://github.com/rtrimble13/drobo/issues/26) | Fixed |
| Coverage never measured | [#27](https://github.com/rtrimble13/drobo/issues/27) | Fixed |

Two changes went slightly beyond the findings as filed, because the fixes
would otherwise have been unreachable or untestable: a `drobo <app> auth`
command (the interactive OAuth flow had to move off the error path, and
without a command it would have been dead code — the docs had been promising
this tool since the beginning), and a `--config PATH` option (`ConfigManager`
already accepted the path; injecting it was the fix for #24).

## Verdict & summary

drobo is a small, cleanly layered Dropbox CLI (~1,550 lines of source) with a genuinely good structural idea: a strict `//` prefix to disambiguate remote from local paths, and a command surface that mirrors GNU coreutils closely enough to be predictable. The architecture is sound and the layering (`cli.py` → `commands.py` → `dropbox_client.py`) is worth preserving as-is.

The problem is not the design — it is that the happy path has never been exercised end-to-end against the code as written. Four defects are confirmed reproducible, and the first of them means `drobo <app> ls` with no arguments fails 100% of the time. Every `ls` and `cp` example in the top-level README uses a path convention the code rejects. A failed download destroys the local file it was overwriting. `ls -t` raises a `TypeError` on any folder containing both files and subfolders — and the test that should catch it uses string dates and no folders, so it passes.

The common root cause is a testing blind spot rather than carelessness: `dropbox_client.py` — 294 lines holding all of the auth, token, and network-error handling — has **zero** test coverage, and the 55 passing tests mock it out entirely. Several of the confirmed bugs live in that file. Coverage is configured in `pyproject.toml` but never actually measured, so nothing surfaced the gap.

Fix the four P0s and the docs drift and this becomes a usable tool quickly; they are all small, contained changes. The larger structural work — retry/backoff, chunked transfers, real client tests — is what turns it into a dependable one.

## How this review was scoped

**Language/stack:** Python 3.10–3.13, `click` for the CLI, the official `dropbox` SDK, `configistate` for config. setuptools/pyproject build, pytest, GitHub Actions CI. Git history was available and used for churn analysis.

**Read in full and traced:** all four source modules — `src/drobo/cli.py` (303), `src/drobo/commands.py` (809), `src/drobo/dropbox_client.py` (294), `src/drobo/config.py` (135). Data flow was traced end-to-end for every command (`ls`, `cp`, `mv`, `rm`), including path normalisation, wildcard expansion, and the recursive helpers. All four CI workflows, `pyproject.toml`, `Makefile`, `environment.yml`, and both READMEs read in full.

**Verified by execution, not inference.** The dev dependencies were installed and the suite run (55 passed, 0.5s). Every defect reported below as High confidence was reproduced against the real code with a mocked SDK — the reproduction scripts covered the `ls` default-path failure (via `CliRunner`), the `ls -t` `TypeError`, the `cp` error masking, the `download_file` truncation (confirmed by writing a real file, failing the download, and reading it back empty), the `AuthError` constructor signature, and the `0644` config permissions (confirmed by creating a config through `ConfigManager` and stat-ing it). Findings that could not be executed are marked Medium confidence and say so.

**Sampled:** `test/test_commands.py` (1,293 lines) — read the fixtures and the `ls` sort tests closely, skimmed the `cp`/`mv`/`rm` cases. `test_cli.py` and `test_config.py` read in full.

**Skipped:** `.vscode/` (editor config, no bearing on correctness), `.gitignore`, `LICENSE`, and the `.git` internals. No live Dropbox account was available, so nothing was verified against the real API — the >150 MB upload limit and the SDK's auto-refresh behaviour are cited from documented Dropbox behaviour, not observed.

**One thing this review could not check:** whether the broken publish workflow has ever actually shipped a release. The `v1.0.0` tag exists and the workflow as written has nothing to upload; which of those won in practice is not determinable from the repo alone.

## Findings

Ordered by priority tier, then severity. All 15 are filed as GitHub issues.

### [P0] `ls` with no PATH argument always fails — [#13](https://github.com/rtrimble13/drobo/issues/13)
- **Lens:** Hidden bug
- **Priority:** P0 · **Impact:** High · **Effort:** Low · **Severity:** Critical · **Confidence:** High
- **Evidence:** `src/drobo/cli.py:96`, `src/drobo/commands.py:78`
- **Why it matters:** The click default for the path argument is `/`, which `_is_remote_path` rejects. The single most basic invocation of the tool — `drobo <app> ls` — exits 1 with an error claiming the user supplied a local path, when they supplied nothing. Reproduced via `CliRunner`.
- **Recommendation:** Change the default to `//`; `ls_with_options` already maps that to the empty string the API wants for root.

### [P0] `download_file` truncates the destination before downloading — [#14](https://github.com/rtrimble13/drobo/issues/14)
- **Lens:** Hidden bug
- **Priority:** P0 · **Impact:** High · **Effort:** Low · **Severity:** Critical · **Confidence:** High
- **Evidence:** `src/drobo/dropbox_client.py:168`, reached from `src/drobo/commands.py:664` (`cp`) and `src/drobo/commands.py:380` (`mv`)
- **Why it matters:** `open(local_path, "wb")` runs *before* `files_download`, so any transient failure leaves the pre-existing local file zero-length. Reproduced: a file containing real data was emptied by a download that raised `ConnectionError`. Silent, unrecoverable local data loss on an ordinary failure.
- **Recommendation:** Download to a temp file in the destination directory, then `os.replace` into place only on success.

### [P0] `ls -t` crashes on any folder with both files and subfolders — [#15](https://github.com/rtrimble13/drobo/issues/15)
- **Lens:** Hidden bug
- **Priority:** P0 · **Impact:** High · **Effort:** Low · **Severity:** High · **Confidence:** High
- **Evidence:** `src/drobo/commands.py:121-130`, `src/drobo/dropbox_client.py:149-151`
- **Why it matters:** The sort key returns a `float` for files (from `datetime.timestamp()`) and `""` for folders (which never get a `modified` key), so `sorted` compares `str` to `float` and raises `TypeError`. Affects nearly every real folder. The existing test at `test/test_commands.py:169` masks it by using string dates and no folder entries.
- **Recommendation:** Normalise the key to a single numeric epoch with `0.0` as the floor; fix the test fixture to use `datetime` values and include a folder.

### [P0] `cp` rewrites every failure as "No such file or directory" — [#16](https://github.com/rtrimble13/drobo/issues/16)
- **Lens:** Hidden bug
- **Priority:** P0 · **Impact:** High · **Effort:** Low · **Severity:** High · **Confidence:** High
- **Evidence:** `src/drobo/commands.py:682-683`, `src/drobo/commands.py:715-716`
- **Why it matters:** A blanket `except Exception` wraps the whole helper body, including the code that raises the correct diagnostics. Reproduced: copying a remote directory without `-r` reports "No such file or directory" instead of "is a directory (use -r)". Auth failures, rate limits, and network errors are all flattened into the same wrong message, and `--verbose` doesn't help because the original exception object is discarded.
- **Recommendation:** Narrow the `try` to just the `get_metadata` call; move type dispatch outside it; use `raise ... from e` wherever a broad catch is genuinely wanted.

### [P1] Refresh-token-only configs rejected; "refresh" is an interactive OAuth re-auth — [#17](https://github.com/rtrimble13/drobo/issues/17)
- **Lens:** Robustness
- **Priority:** P1 · **Impact:** High · **Effort:** Medium · **Severity:** High · **Confidence:** High
- **Evidence:** `src/drobo/config.py:36-38`, `src/drobo/dropbox_client.py:33-36`, `src/drobo/dropbox_client.py:67-105`
- **Why it matters:** `has_valid_tokens()` checks only the access token, so the recommended and more secure setup — a refresh token with no long-lived access token — is refused, even though the client is constructed with everything the SDK needs to mint tokens itself. Separately, `refresh_access_token()` never uses the stored refresh token: it starts a browser OAuth flow and blocks on `input()`, making the tool unusable from cron, CI, or any pipe — it hangs rather than failing.
- **Recommendation:** Accept either token; let the SDK auto-refresh and just persist the result; move the interactive flow into an explicit `auth` command guarded by `stdin.isatty()`.

### [P1] No retry or backoff anywhere — [#18](https://github.com/rtrimble13/drobo/issues/18)
- **Lens:** Robustness
- **Priority:** P1 · **Impact:** High · **Effort:** Medium · **Severity:** High · **Confidence:** High
- **Evidence:** no matches for `retry|backoff|sleep|RateLimit|429` in `src/`; hot paths at `src/drobo/commands.py:784-802`, `src/drobo/commands.py:751-766`, `src/drobo/commands.py:728-743`
- **Why it matters:** The recursive helpers issue one metadata round-trip per directory plus one call per file, unthrottled — hundreds of sequential calls for a modest tree. Dropbox's `RateLimitError` carries a `retry_after` that is never read, and transient network errors aren't caught at all. A 429 aborts mid-tree, leaving a half-copied result with no resume.
- **Recommendation:** One retry wrapper honouring `retry_after` with exponential backoff, applied to every API call; retry only idempotent-safe failures; cache `_is_remote_directory` within a run.

### [P1] `AuthError("Token refresh failed")` raises TypeError — [#19](https://github.com/rtrimble13/drobo/issues/19)
- **Lens:** Hidden bug
- **Priority:** P1 · **Impact:** Medium · **Effort:** Low · **Severity:** High · **Confidence:** High
- **Evidence:** `src/drobo/dropbox_client.py:63`
- **Why it matters:** The SDK's `AuthError.__init__` takes `(request_id, error)`; constructing it with one argument raises `TypeError` from inside the `except` block, masking the real refresh failure and defeating any `except AuthError:` handler. Verified against the installed SDK signature. Currently reachable only because the interactive flow blocks first — fixing #17 makes this path live.
- **Recommendation:** Raise a `RuntimeError` or a package-local `DroboAuthError` naming the app and cause, preserving `from e`.

### [P1] Publish workflow cannot publish — [#20](https://github.com/rtrimble13/drobo/issues/20)
- **Lens:** Hidden bug
- **Priority:** P1 · **Impact:** Medium · **Effort:** Low · **Severity:** High · **Confidence:** High
- **Evidence:** `.github/workflows/publish.yml`
- **Why it matters:** The job runs `pypa/gh-action-pypi-publish` with no `actions/checkout`, no `python -m build`, and no artifact download — the workspace is empty, so there is nothing to upload. The `Makefile` has a working `dist` target the workflow never calls. Release automation is non-functional.
- **Recommendation:** Add checkout, setup-python, and build steps; verify against TestPyPI; add a check that the tag, `pyproject.toml:6`, and `__init__.py:7` versions agree.

### [P1] `.droborc` written world-readable with secrets in plaintext — [#21](https://github.com/rtrimble13/drobo/issues/21)
- **Lens:** Robustness (security)
- **Priority:** P1 · **Impact:** Medium · **Effort:** Low · **Severity:** High · **Confidence:** High
- **Evidence:** `src/drobo/config.py:98`, `src/drobo/config.py:130`
- **Why it matters:** Confirmed by creating a config through the real code path: mode `0644`. The file holds `app_secret`, `access_token`, and `refresh_token` — the refresh token plus key and secret is indefinite access to the user's Dropbox. Because `_create_default_config` writes the file automatically on first run, the tool creates this exposure on the user's behalf before they can intervene.
- **Recommendation:** Create with `0600`; warn on load when an existing config is group/world-readable, following the `ssh` precedent.

### [P1] Post-refresh retry drops kwargs — `ls -R` silently degrades — [#22](https://github.com/rtrimble13/drobo/issues/22)
- **Lens:** Hidden bug
- **Priority:** P1 · **Impact:** Medium · **Effort:** Low · **Severity:** Medium · **Confidence:** High
- **Evidence:** `src/drobo/dropbox_client.py:160`, caller at `src/drobo/commands.py:102`
- **Why it matters:** `return self.list_folder(path)` omits `*args, **kwargs`, so a token expiring during `ls -R` produces a top-level-only listing presented as a complete recursive one. No error, no warning — just a wrong answer. This is the only one of the eight retry sites that drops its arguments.
- **Recommendation:** Forward `*args, **kwargs`; better, collapse all eight hand-rolled retry blocks into the single wrapper from #18. Also use `list(result.entries)` at `:129` rather than mutating the SDK's list.

### [P1] `dropbox_client.py` has zero test coverage — [#23](https://github.com/rtrimble13/drobo/issues/23)
- **Lens:** Refactoring (testability)
- **Priority:** P1 · **Impact:** High · **Effort:** Medium · **Severity:** — · **Confidence:** High
- **Evidence:** `test/test_commands.py:32` (the only reference to the module in the whole suite, and it patches it out)
- **Why it matters:** 294 lines and the second-most-churned file in the repo, holding all auth, token, and error-translation logic, executed by none of the 55 tests. Four confirmed defects in this review (#14, #19, #22, #17) live in that file and would each have been caught by a basic test. The 1,293-line `test_commands.py` gives an impression of coverage that stops at this layer.
- **Recommendation:** Add `test/test_dropbox_client.py` covering construction, entry mapping, pagination, auth retry, error translation, and local file handling — using real `FileMetadata`/`FolderMetadata` instances, since dispatch is by `isinstance`.

### [P1] `ConfigManager` constructed twice; token writes go through the wrong instance — [#24](https://github.com/rtrimble13/drobo/issues/24)
- **Lens:** Refactoring
- **Priority:** P1 · **Impact:** Medium · **Effort:** Low · **Severity:** — · **Confidence:** High
- **Evidence:** `src/drobo/cli.py:71`, `src/drobo/commands.py:58`
- **Why it matters:** `~/.droborc` is parsed twice per invocation, and the `AppConfig` the client holds belongs to manager #1 while `save_app_tokens` mutates manager #2's copy — the in-memory objects diverge, papered over only by the file write. Latent today; becomes real once token refresh works (#17). It also blocks a `--config PATH` option that `ConfigManager` already supports but no caller uses, and forces tests to patch module globals.
- **Recommendation:** Inject the manager through `setup_commands` into `CommandHandler`; one manager and one `AppConfig` per process.

### [P1] Documentation contradicts the code — [#25](https://github.com/rtrimble13/drobo/issues/25)
- **Lens:** Enhancement (docs)
- **Priority:** P1 · **Impact:** Medium · **Effort:** Low · **Severity:** — · **Confidence:** High
- **Evidence:** `README.md:38-60`, `doc/README.md:40-41`
- **Why it matters:** Every `ls` and `cp` example in the top-level README uses single-slash paths the code rejects or misroutes as local; only the last `mv` example uses the correct `//`. `doc/README.md` documents `-a/--all` and `-d/--directory` `ls` flags that were never implemented (`cli.py:97-111` has only `-l`, `-r`, `-R`, `-S`, `-t`) and shows examples using them. Combined with #13, a user following the quickstart cannot get one successful command out of the tool.
- **Recommendation:** Rewrite README examples to `//` and state the convention explicitly; remove the two unimplemented flags from the docs; add a crude CI check that extracts fenced `drobo` lines and parses them.

### [P2] Whole-file buffering — >150 MB uploads fail — [#26](https://github.com/rtrimble13/drobo/issues/26)
- **Lens:** Robustness
- **Priority:** P2 · **Impact:** Medium · **Effort:** Medium · **Severity:** Medium · **Confidence:** High
- **Evidence:** `src/drobo/dropbox_client.py:186` (`f.read()`), `src/drobo/dropbox_client.py:170` (`response.content`)
- **Why it matters:** `files_upload` is limited to 150 MB by Dropbox; anything larger needs upload sessions, and there is no chunking in the codebase. Below the ceiling, each transfer allocates the whole file in heap — once per file during a recursive copy. No resumability and no progress indication.
- **Recommendation:** Chunked upload sessions above an 8 MB threshold; `files_download_to_file` or `iter_content` for downloads; combine with #14's atomic rename. Offset arithmetic needs direct test coverage — errors there corrupt silently.

### [P2] Coverage configured but never measured — [#27](https://github.com/rtrimble13/drobo/issues/27)
- **Lens:** Enhancement (workflow)
- **Priority:** P2 · **Impact:** Medium · **Effort:** Low · **Severity:** — · **Confidence:** High
- **Evidence:** `pyproject.toml:35`, `pyproject.toml:81-82`, `pyproject.toml:75-79`, `.github/workflows/python-package.yaml:20`
- **Why it matters:** `pytest-cov` is a declared dev dependency and `[tool.coverage.run]` is configured, but `--cov` appears in no `addopts`, no CI step, and no make target — so no report is ever produced. This is why a 294-line module with zero coverage went unnoticed across 8 commits.
- **Recommendation:** Add `--cov=src/drobo --cov-report=term-missing` to `addopts`; set `fail_under` after #23 lands and ratchet. Same pass: `environment.yml` omits `pytest-mock`/`pytest-cov` so a conda env can't run the suite, and `[tool.black] target-version = ["py38"]` contradicts `requires-python = ">=3.10"`.

### Below the backlog cap

Real but minor; noted here without work items. **All of these have since been
fixed** on the review branch.

- **`mv` reports errors with a `cp:` prefix.** `_validate_source_consistency` and `_validate_destination_for_multiple_files` hardcode `"cp: ..."` (`commands.py:542,555,562`) but are called from `mv` (`commands.py:262,267`). Reproduced: `mv` of mixed sources prints `cp: cannot mix remote and local source files`. Pass the command name in.
- **Missing local sources are silently dropped.** `_expand_source_wildcards` only extends when `glob.glob` matches (`commands.py:528-530`), so `cp missing.txt //dest` reports "no files matched" rather than "No such file or directory". Distinguish a literal path from a glob.
- **Empty directories are invisible in `ls -R`.** `_build_recursive_tree` appends only entries of type `file` (`commands.py:155-156`), so folders with no files never appear.
- **`~/.drobo.log` grows without bound.** `setup_logging` unconditionally attaches a `FileHandler` (`cli.py:26`) with no rotation and no size cap, and creates it with default permissions — while `--verbose` sets the *root* logger to DEBUG, so third-party library output lands there too. Use `RotatingFileHandler`, and consider scoping the level to the `drobo` logger rather than root.
- **Dead code:** `_download_directory_recursive` (`commands.py:745-749`) is a wrapper with no callers.
- **`-S` and `-t` are mutually exclusive** by the `if/elif` at `commands.py:114-118`; GNU `ls` lets the later flag win. Minor fidelity gap in a tool that advertises coreutils behaviour.
- **`security.yml` runs a 4-way Python matrix** for `dependency-review-action`, which doesn't use Python — four identical jobs where one would do, and the job is a no-op on `push` since the step is `if: pull_request`. The workflow is also named "Security Checks" but runs no SAST or dependency audit; `pip-audit` or CodeQL would make the name honest.
- **No Dependabot config** despite four pinned-by-major dependencies and four workflows using pinned action versions.
- **`os.path.abspath` in `_normalize_remote_path`** (`commands.py:34`) produces backslashes on Windows, which would corrupt remote paths. The package advertises no platform constraint and CI is Linux-only, so this is untested territory — either declare POSIX-only or use `posixpath` explicitly for remote paths. *(Medium confidence — not verified on Windows.)*

## New feature ideas

Quarantined per the review method; each cites evidence in the code rather than general product speculation. No work items filed.

- **`drobo <app> auth` command** (P2) — *Evidence:* `dropbox_client.py:78-98` already contains a complete, working `DropboxOAuth2FlowNoRedirect` implementation, but it is reachable only from an error path. Meanwhile `doc/README.md` step 3 tells the user to "Use the Dropbox OAuth flow to obtain access and refresh tokens" and hands them no tool to do it. Promoting the existing code to a first-class command closes the documented onboarding gap and is largely a matter of moving it.
- **`--config PATH` global option** (P2) — *Evidence:* `ConfigManager.__init__` already accepts `config_path` (`config.py:52`) and no caller ever passes it. The plumbing exists; only the click option and the wiring from #24 are missing. Enables per-project configs and makes integration testing straightforward.
- **`drobo <app> stat` / `du`** (P3) — *Evidence:* `DropboxClient.get_metadata` (`dropbox_client.py:232-244`) already returns name, path, type, size, and mtime, and is used only internally for existence checks. A read-only command exposing it is nearly free given the method exists.
- **One-way `sync`** (P3) — *Evidence:* `mv -u` at `commands.py:345-368` already implements newer-than mtime comparison across local and remote, including the `datetime`/epoch normalisation. That comparison is the core of a directory sync; combined with the recursive walkers already present (`commands.py:728-802`), the remaining work is reconciliation and deletion policy.

## What's done well

- **The layering is genuinely clean and worth preserving.** `cli.py` does argument parsing and nothing else, `commands.py` holds command semantics, `dropbox_client.py` owns all SDK contact. No layer reaches past its neighbour, which is why most of the fixes above are contained to a single file.
- **The `//` remote-path convention is the right call.** Making remote-vs-local explicit and syntactic (`commands.py:20-22`) rather than guessing from context is a better design than most CLI wrappers manage, and it is applied consistently throughout `commands.py` and the `cli.py` docstrings. The README not following it is a docs bug, not a design one.
- **Real coreutils fidelity in the command surface.** `cp` implements all three GNU forms — positional, `-T`, and `-t` — with the correct argument constraints (`cli.py:141-190`, `commands.py:176-195`), including `-T` requiring exactly two operands. `mv -u`'s newer-than semantics (`commands.py:345-368`) correctly handle both `datetime` and epoch inputs. This is more care than "mimics Linux ls" usually implies.
- **The conflict path in `copy_file` is handled deliberately.** `dropbox_client.py:213-227` distinguishes a source-lookup failure from a destination conflict and resolves the latter by explicit delete-then-copy, rather than reaching for `autorename=True` and silently producing "file (1).txt". That is the harder and better choice.
- **Test ergonomics are good where tests exist.** The `command_handler` fixture (`test/test_commands.py:28-35`) is well factored, the suite runs in 0.5s, and `addopts` already sets `--strict-markers --strict-config` — strictness most projects add only after being burned.
- **CI hygiene is above average for a project this size.** Four workflows, a real 3.10–3.13 matrix on both lint and tests, and explicit `permissions: contents: read` on three of the four — default-deny permissions are a good habit and frequently skipped.
- **The `Makefile` and `copilot-instructions.md` agree** on the developer workflow, and the documented targets all work as described.
