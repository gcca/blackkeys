# Blackkeys — Next-Steps Plan

_Prepared 2026-10-04. Planning only: none of the steps below has been carried out._

## 0. Context

This plan comes from a read-only survey of all eight subprojects and CI, done with parallel agents. Each subproject's canonical context in `companions/mdagents/` was checked against the current source. Every finding cites `file:line`. The three most important findings (hydrant's simulated user roster, ws storing the plaintext password, the GHCR push target) were re-checked by hand.

**Overall state**
- **Repo:** the monorepo was re-imported as a single commit (`2ade9b2`). Five auto-commits followed, all with timestamp messages. Since the import only ws, hydrant and ios have changed. Commit hashes cited in the contexts no longer exist.
- **Auth pipeline:** ws signup → RabbitMQ `blackkeys-signup` → hydrant → memcached `auth:user:*` → signin (ws, iOS, dwa). Every hop is wired up, but **the flow is broken end to end and currently insecure** (items 1, 2 and 11).
- **Brands pipeline:** assets-bo writes to S3 → assets (gRPC) → ws → iOS. It works, but bo's override edits never reach clients, and images over 4 MiB fail (items 3 and 13).
- **Events:** `/v1/events/list` answers 503 in practice because no service provides the data (item 12).
- **CI:** there is one workflow. It builds the ws dependency image and its push target is wrong. No subproject's tests run in CI (items 6 and 10).
- **Contexts:** every subproject's context has drifted from the code (item 18).

**Correction applied while merging:** ws blueprints do **not** use a `/blackkeys-ws` URL prefix: no `version_prefix` is set in `blueprints/{auth,events,brands,index}.py`. Routes are served at `/v1/...`. Any note that says otherwise, including older context text, is stale.

**Constraints for every item**
- Use each project's own build and test commands:

  | Project | Command |
  |---|---|
  | cmd, hydrant, assets | `ninja test` |
  | ws, dwa | `pdm run python -m unittest discover` |
  | bo | `cmake … && ctest` |
  | ios | `xcodebuild test` |
  | ecosystem | `docker compose config` |

- No commits, pushes, deploys, `fly secrets`, live-database or memcached changes, DerivedData deletes, or git history rewrites unless you authorize that specific action.
- Edit contexts only through the context-compaction and context-bootstrap procedures.
- Python interpreter: the project's `.pdm-python`, otherwise `~/Developer/e/13/bin/python`.

---

## 1. Decisions needed from you

| # | Decision | Recommendation | Blocks |
|---|---|---|---|
| D1 | Who hashes the signup password? | **ws** hashes with argon2id before the DB insert. The queue carries only the hash. | 2, 5, 11 |
| D2 | What does hydrant do with signups? | **(B) Nothing to the auth cache.** ws read-through stays the only writer of `auth:user:*`. Only consider (A) cache-warming with memcached `add` after insert→publish has been made sequential. | 11 |
| D3 | Where does event data come from? | **New `Events` RPC on assets backed by `events.parquet`.** ws reads through and writes back; the hydration publish is retired. | 12 |
| D4 | How do bo overrides reach clients? | **assets applies `brand-overrides.json`** and reloads by ETag. | 13, 12 |
| D5 | GHCR namespace for the ws deps image | `ghcr.io/plaza-san-miguel/…`, derived from `github.repository_owner`. The alternative is `gcca` with a PAT. | 6, 10 |
| D6 | Image size vs. memcached item size | Keep bo at 10 MiB, raise the assets memcached to `-I 12m`, and set the ws gRPC receive limit to 12 MiB. | 3 |
| D7 | Grafana anonymous role and alert contact | Confirm `Editor` is wanted. Use a webhook or Slack contact point read from a Fly secret, or pause the rules until one exists. | 19 |
| D8 | Large video, stale standalone clones, per-subproject LICENSE copies | Track the video with LFS from now on, with no history rewrite. Archive `~/Developer/blackkeys-{ws,dwa,ecosystem,hydrant}`. Keep the LICENSE copies (Docker build contexts use them). | 21 |
| D9 | iOS brand-cache TTL | **Keep 630 s.** Correct the stale "24 h" in the context. | 16 |

---

## 2. Roadmap at a glance

| Phase | Items | Theme |
|---|---|---|
| **P0** | 1, 2, 3, 4, 5 | Security and data correctness |
| **P1** | 6, 7, 8, 9, 10 | Get builds, tests, CI and compose working |
| **P2** | 11–17 | Finish half-built features |
| **P3** | 18–22 | Hygiene, ops, docs, memory |

Recommended order is in §7.

---

## 3. P0 — Security and correctness

### 1. Make hydrant's simulation opt-in, off by default  `[security]` `M`
- **Goal:** Hydrant never writes users with known passwords into ws memcached unless simulation is explicitly enabled.
- **Evidence:**
  - `blackkeys-hydrant/src/hydrant/simulation.c3:9-17` defines seven users, all with the password `"stars"`.
  - `populate.c3:49` always calls `simulation::roster`.
  - `main.c3:56-62` exits 1 when there are no records.
  - `main.c3:73` and `consumers/usersignup.c3:79` republish on every MQ message.
  - `blackkeys-ws/blackkeys/repositories.py:87-98` trusts a cache hit without checking the DB.
  - Compose points hydrant at the ws memcached nodes (`docker-compose.yaml:416-421`).
  - **This also affects real accounts:** a real user who signs up with a name from the roster can be logged into with `"stars"`.
- **Files:** `src/hydrant/core/conf.c3`, `populate.c3`, `main.c3`, `consumers/usersignup.c3`, `test/{conf,populate,simulation}.c3`.
- **Approach:**
  1. Add `bool simulate` to `Settings`. It comes from `HYDRANT_SIMULATION` and is true only when the value is exactly `"1"`; the default is false.
  2. Change the signature to `populate::prepare(Allocator, simulation::Credential[] credentials, conf::Settings)`, so the caller injects the roster.
  3. In `main.c3`, build records only when `settings.simulate` is set. Otherwise log `simulation disabled` and skip the loop. `--once` then exits 0. The MQ consumers still start.
  4. In `usersignup::consume`, call publish only when `records.len > 0`.
  5. Log a loud warning when simulation is on.
  6. Never set `HYDRANT_SIMULATION` in compose or Fly.
- **Reuse:** `conf::read_string` and `read_uint` (`conf.c3:36-48`); `simulation::roster`, unchanged.
- **Depends / blocks:** Lands together with item 2's hydrant changes. Blocks item 8.
- **Verify:** in `blackkeys-hydrant`, run `ninja test && ninja fmt-check`. New tests:
  - simulation is off when the variable is unset, `"0"` or `"yes"`, and on when it is `"1"`;
  - `prepare` with an injected two-user roster produces 2 records with `auth:user:<name>` keys.
- **Risks:** Keys already in memcached expire on their own after 210 s. Flushing them sooner is a live-data operation and needs your approval. A later option is to have ws HMAC-sign its cache values.

### 2. Hash signup passwords in ws; the queue carries only the hash  `[security]` `M`
- **Goal:** No plaintext password reaches Turso, RabbitMQ or hydrant's stdout, and users who sign up can then sign in.
- **Evidence:**
  - `blueprints/auth.py:88` passes the raw password along.
  - `repositories.py:123-127` uses `gather` to run the insert and the publish **concurrently**.
  - `backends/stores/db.py:70-73` inserts the password as given.
  - `application.py:28` rejects any stored value that isn't `$argon2id$…`.
  - `blackkeys-hydrant/.../usersignup.c3:36` prints the password.
  - The schemas `ws/schemas/auth.fbs` and `hydrant/schemas/user_signup.fbs` have the same slot layout.
- **Files:**
  - ws: `application.py`, `blueprints/auth.py`, `repositories.py`, `backends/publishers/signup.py`, `tests/test_signup.py`, `tests/test_auth.py`.
  - hydrant: `consumers/usersignup.c3`, `test/usersignup.c3`.
- **Approach:**
  1. Pin the hasher explicitly: `PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, type=Type.ID)`. This matches cmd's `argon2id.rs` and hydrant's `conf.c3:8-10`.
  2. Add `AuthService.SignUp(username, password, email)`. It hashes via `asyncio.to_thread(hasher.hash, …)` and then calls `repository.CreateUser(username, password_hash, email)`. The blueprint calls `SignUp`.
  3. Rename the parameters to `password_hash` throughout. `EncodeUserSignup` raises `ValueError` unless the value starts with `$argon2id$`.
  4. **Make the insert and publish sequential:** await the insert first, so a conflict or unavailability error is raised before anything is published. Then publish.
  5. Keep the FlatBuffers field name `password`, which avoids regenerating code on both sides. A rename is optional.
  6. Hydrant: `decode` returns an `UNHASHED_PASSWORD` fault when the value isn't argon2, and the report prints only the username.
- **Reuse:** `AuthService.password_hasher` (`application.py:14`). `commands/local_create_user.py:29-31` already uses the same pattern.
- **Verify:**
  - In `blackkeys-ws`: `pdm run python -m unittest discover -v` and `pdm run python -m compileall -q blackkeys tests ws.py`. New tests:
    - the stored and published values both start with `$argon2id$` and verify against the password;
    - on a conflict, the publisher is never called;
    - `EncodeUserSignup("alice","plain")` raises.
  - In hydrant: `ninja test`, with the decode fixture rebuilt using an argon2 string, plus a test that a plaintext password is rejected.
- **Risks:**
  - If the publish fails after a successful insert, the user already exists. Recommend returning 202 and logging, since login falls back to the DB.
  - **Existing plaintext rows in Turso need a reset or rehash.** That is a live-data change; cmd's `change_password` can do it, with your authorization.

### 3. Raise ws's gRPC receive limit above bo's 10 MiB upload cap  `[correctness]` `S`
- **Goal:** Any image bo accepts can be served through ws.
- **Evidence:**
  - bo's `handling/brand/routes/common.hpp:21` sets `kMaxPngBytes = 10 MiB`.
  - ws's `backends/services/brands.py:41` calls `insecure_channel` with no options, so the 4 MiB default receive limit applies.
  - assets' `main.go:38` uses `grpc.NewServer()`; Go's send limit is unbounded.
  - The assets memcached runs with `-I 10m` (`docker-compose.yaml:56`), so a 10 MiB image never fits in the cache.
- **Files:** `blackkeys-ws/blackkeys/backends/services/brands.py`, `tests/test_brands.py`, and the `-I` value in `blackkeys-ecosystem/docker-compose.yaml` and the assets memcached `fly.toml`.
- **Approach:**
  1. Define `ASSETS_MAX_RECEIVE_BYTES = 12 * 1024 * 1024`.
  2. Pass `options=[("grpc.max_receive_message_length", ASSETS_MAX_RECEIVE_BYTES)]` to the channel.
  3. Optionally add `grpc.MaxSendMsgSize(12<<20)` in assets to make the limit explicit.
  4. Apply D6 to the memcached item size.
- **Verify:** in `blackkeys-ws`, `pdm run python -m unittest tests.test_brands -v`, then `discover`. New test: patch `insecure_channel` and assert the options are passed. For the compose change, `docker compose config -q` in ecosystem.

### 4. Read and parse `brands.parquet` once in bo create and delete  `[correctness]` `S`
- **Goal:** Validation and the mutation use the same bytes. This removes the window where the wrong row can be deleted, and it halves the S3 reads.
- **Evidence:**
  - `routes/brands_delete.cpp:18` validates against one fetch, then `:31` fetches again and calls `RemoveRow`.
  - `brands_create.cpp:42` and `:83` follow the same pattern.
  - `brands_update.cpp:192-210` already does it correctly with a single read.
- **Files:** `routes/common.{hpp,cpp}`, `routes/brands_delete.cpp`, `routes/brands_create.cpp`, and optionally `brands_update.cpp`.
- **Approach:**
  1. Add `struct BrandsSnapshot { std::string bytes; storage::ParquetTable table; }` and `std::optional<BrandsSnapshot> FetchBrandsSnapshot(const Callback&)`, using the same error mapping as today.
  2. Reimplement `FetchBrandsTable` on top of the new function.
  3. `ApplyDelete` and `ApplyCreate` use `snap->table` for checks and `snap->bytes` for `RemoveRow` and `AppendRow`. Delete the second fetch.
- **Reuse:** `storage::GetObject`, `storage::ParseParquetTable`, `SendError`.
- **Verify:** in `blackkeys-assets-bo`, run `cmake -S . -B build -DASSETSBO_TEST=ON && cmake --build build -j 16 && ctest --test-dir build --output-on-failure`. All tests must pass with the same count. New test: `FetchBrandsSnapshot` with no S3 returns 502. Success-path tests are in item 17.
- **Risks:** Two concurrent writers can still lose an update. Follow-up: S3 conditional PUT with `If-Match`.

### 5. Guard ws `local-create_user` against writing to a synced replica  `[correctness]` `S`
- **Goal:** Never write directly to a Turso synced replica. If the replica's credentials are present, run pull → insert → push instead.
- **Evidence:**
  - `blackkeys-ws/blackkeys/commands/local_create_user.py:27-35` opens with `connect_local` and inserts. **`blackkeys-ws/blackkeys.db-info` exists right now**, so the default target is a synced replica.
  - The reference behavior is in cmd's `create_user/src/sqlite3.rs`: `write_target` (`:50-68`) and the synced path (`:121-157`).
  - The file also contains a docstring at `:20`, which breaks the codebase's no-docstring convention.
- **Files:** `blackkeys/commands/local_create_user.py`, `tests/test_commands.py`.
- **Approach:**
  1. Add `SyncedReplicaRefused` and `WriteTarget(db, url, token)`:
     - no `-info` file: return `None` (plain local write);
     - `-info` file present with both credentials: return them;
     - `-info` file present without credentials: raise.
  2. Read the credentials via `Settings.FromEnv()`.
  3. For the synced path, use `connect_sync(...)`, then `pull`, insert, commit, `push`. Errors propagate rather than being swallowed the way `PushDatabase` does. Scrub the token from error messages.
  4. Refuse to run when the database file does not exist.
  5. Remove the docstring.
- **Reuse:** `turso.lib_sync_aio.connect_sync` (as in `persistence/turso.py:15-19`) and the hasher pinned in item 2.
- **Verify:** in `blackkeys-ws`, `pdm run python -m unittest tests.test_commands -v`, using only a scratch temp directory. New tests:
  - sidecar present without env vars: raises, and the database is unchanged;
  - no sidecar: the local insert works;
  - sidecar present with env vars: takes the sync branch (`connect_sync` mocked);
  - the token is redacted from errors.

  **Never run this against the repo's `blackkeys.db`.**

---

## 4. P1 — Get builds, tests and CI working

### 6. Fix the GHCR namespace and make the deps tag immutable  `[ops]` `S`
- **Goal:** The deps workflow can push using `GITHUB_TOKEN`, and ws builds pin a deps tag tied to the lock file's hash.
- **Evidence:**
  - `.github/workflows/blackkeys-ws-deps.yaml:11` sets `IMAGE: ghcr.io/gcca/blackkeys-ws`, but the remote is `plaza-san-miguel/blackkeys`. `packages: write` is already granted (`:8`).
  - Only the mutable tags `deps` and `deps-<arch>` are pushed (`:52`, `:78`).
  - `blackkeys-ws/Dockerfile:3` defaults `DEPS_IMAGE=ghcr.io/gcca/blackkeys-ws:deps`, and `scripts/build-deps.fish:23,42,62` hard-codes `gcca`.
  - The compose ws build (`docker-compose.yaml:376-380`) passes no build args, so it inherits the unpushed default.
- **Files:** the workflow, `blackkeys-ws/Dockerfile`, `blackkeys-ws/scripts/build-deps.fish`, `blackkeys-ecosystem/docker-compose.yaml`.
- **Approach:**
  1. In both jobs, set `IMAGE=ghcr.io/${GITHUB_REPOSITORY_OWNER,,}/blackkeys-ws` through `$GITHUB_ENV` (the `,,` lowercases the owner name).
  2. Also tag `deps-<lock12>-<arch>`, and add `:deps-<lock12>` to the manifest. The manifest job needs a checkout to compute the hash.
  3. Change the Dockerfile default to the namespace chosen in D5.
  4. `build-deps.fish` derives the namespace from `git remote get-url origin`.
  5. Compose: `args: { DEPS_IMAGE: ${BLACKKEYS_WS_DEPS_IMAGE:-blackkeys-ws:deps} }`, so local builds use the image built locally.
- **Verify:**
  - Run `actionlint` on the workflow, or `check-yaml` if actionlint isn't available.
  - In ecosystem: `docker compose --profile apps config`.
  - In `blackkeys-ws`: `fish scripts/build-deps.fish` (without `--push`) passes its smoke test.
  - **Running the workflow publishes an image and needs your authorization.**
- **Risks:** New packages in an org's GHCR are private by default, so Fly and local pulls will need credentials or a visibility change.

### 7. Consistent compose and nginx port map; MinIO settings for assets  `[ops]` `S`
- **Goal:** The compose `apps` profile starts cleanly, nginx routes correctly, and dwa reaches ws.
- **Evidence:**
  - The compose assets service (`:355-374`) sets no `AWS_*` variables, but `blackkeys-assets/blackkeys/core/conf.go:61-85` requires them. MinIO and its init job already exist in compose (`:163-190`; bucket `blackkeys-assets`).
  - `nginx.conf:36-37` sends `/dwa/` to 8000, which is ws's port. `:46-47` sends `/api/` to 8001, where nothing listens.
  - dwa's `core/conf.py:12` defaults `API_URL` to `:8001`, but dwa itself runs on Sanic's default port 8000.
- **Port map:**
  - ws: **8000** (unchanged; matches Fly).
  - dwa: **8001**.
  - nginx `/api/` → 8000, `/dwa/` → 8001.
  - dwa `API_URL` default: `http://localhost:8000`.
- **Files:** `blackkeys-ecosystem/{docker-compose.yaml,nginx.conf}`, `blackkeys-dwa/blackkeys/core/conf.py`, `blackkeys-dwa/tests/test_routes.py`.
- **Approach:**
  1. Give assets the local MinIO settings: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION=us-east-1`, `AWS_ENDPOINT_URL_S3=http://minio:9000`.
  2. Add `depends_on: minio-init: {condition: service_completed_successfully}`.
  3. Swap the two nginx ports.
  4. Change the dwa default and document `--port=8001`.
- **Verify:**
  - In `blackkeys-ecosystem`: `docker compose --profile core --profile apps config -q` and `nginx -t -c $PWD/nginx.conf`.
  - In `blackkeys-dwa`: `pdm run python -m unittest discover -v`.
- **Risks:** A fresh MinIO has no `brands.parquet`, so List fails until it is seeded. Seeding is a separate step that you run.

### 8. Fix the failing tests and the formatter globs (hydrant, dwa)  `[tests]` `S`
- **Goal:** hydrant `ninja test` and `ninja fmt-check` pass, and dwa's `unittest discover` passes.
- **Evidence:**
  - hydrant: `test/simulation.c3:11-12` and `test/populate.c3:26` expect a user `ada`, who is no longer in the roster. These two tests always fail; the failure has nothing to do with test order.
  - hydrant: the `build.ninja:24,32` globs omit `src/hydrant/consumers/*.c3`, and `test/fbufs.c3:41` fails the format check.
  - dwa: `tests/test_routes.py:459-462` expects `text/html`, but `blueprints/index.py:41-43` returns `text/plain`.
- **Approach:**
  1. In the simulation test, assert `credentials[0] == simulation::ROSTER[0]`.
  2. The populate tests use item 1's injected roster `{{"ada","difference-engine"}}`.
  3. Add the consumers glob to both the format rule and the format-check rule.
  4. Run `ninja fmt` once.
  5. In dwa, assert `startswith("text/plain")`; a healthcheck should stay plain text.
- **Depends:** item 1, for the new `prepare` signature.
- **Verify:**
  - In hydrant: `ninja fmt-check && ninja test`, with every test passing.
  - In `blackkeys-dwa`: `pdm run python -m unittest discover -v`, expecting 32 of 32.

### 9. iOS: test runner hang and unsigned UI-test bundle  `[tests]` `M`
- **Goal:** `xcodebuild test` passes from a shared scheme, with no per-user Xcode state committed.
- **Evidence:**
  - The latest run (`…/DerivedData/blackkeys-amiesivisqriwlaufodzuavwrjfy/Logs/Test/Test-blackkeys-2026.10.04_23-21-18--0500.xcresult`) has two failures:
    - `blackkeysTests`: "test runner hung before establishing connection";
    - `blackkeysUITests`: "Trying to load an unsigned library".
  - An orphaned DerivedData folder, `blackkeys-ejrbxpzrhneqinfgdvcctoburgyb`, still exists.
  - Per-user files are committed: `xcuserdata/.../xcschememanagement.plist` and `UserInterfaceState.xcuserstate`.
  - No shared scheme is committed.
  - `project.pbxproj:57` references a stale `iPhoneOS26.0.sdk` Foundation framework.
  - The test targets rely on Automatic signing with team `UP9X8Y5R8S`.
- **Files:** `blackkeys-ios/blackkeys.xcodeproj/project.pbxproj`, a new `xcshareddata/xcschemes/blackkeys.xcscheme`, and `.gitignore`. The `git rm --cached` of the xcuserdata files is for you to run.
- **Approach (diagnose first):**
  1. Run `xcodebuild -list`, and `-showBuildSettings … | grep -E 'CODE_SIGN|SDK|DEPLOYMENT'` for each test target.
  2. Run `-only-testing:blackkeysTests` on its own to separate the hang from the signing problem.
  3. Use ad-hoc `CODE_SIGN_IDENTITY="-"` for the simulator test targets.
  4. Remove the stale Foundation references (`:10`, `:57`, `:135`, `:169`). Do this in Xcode.
  5. Mark the scheme as Shared, and ignore `xcuserdata/`.
  6. **Ask before deleting DerivedData or erasing a simulator.**
- **Verify:** `xcodebuild test -project blackkeys.xcodeproj -scheme blackkeys -destination 'platform=iOS Simulator,name=iPhone 18 Pro,OS=27.0'` reports `** TEST SUCCEEDED **`, and `xcrun xcresulttool get test-results summary` shows 0 failed. Source has 33 unit tests and 5 UI tests.
- **Risks:** The hang may come from the simulator or the iOS 27.0 runtime rather than the project.

### 10. Per-subproject test CI (`.github/workflows/ci.yaml`)  `[ci]` `L`
- **Goal:** Each PR runs only the test suites for the subprojects it touches.
- **Evidence:**
  - The deps workflow is the only workflow.
  - cmd hard-codes `/opt/homebrew/opt/argon2/lib` (`build.ninja:8,20,35`).
  - hydrant's `project.json` is macOS-specific. A `project.linux.json` exists, and the Dockerfile pins C3 0.8.2.
  - bo needs Drogon, the AWS SDK and Arrow/Parquet.
  - assets requires Go 1.26.0.
- **Approach (phased):**
  1. A `changes` job using `dorny/paths-filter@v3`; each subproject job runs only when its filter matches. Set `permissions: contents: read` and `concurrency` with cancel-in-progress.
  2. **Phase 1 (cheap jobs):**
     - ws and dwa: `setup-pdm` with 3.13, `pdm sync -d`, `unittest discover`, `compileall`. ws also needs `libmemcached-dev`.
     - assets: `setup-go` from `go-version-file`, then `go vet`, `go test`, and a gofmt check.
     - ecosystem: `docker compose … config -q` and `pre-commit run check-yaml`.
  3. **Phase 2:**
     - cmd: `libargon2-dev` and `ninja-build`; needs item 20's `argon2_lib` variable.
     - hydrant: a test stage in its Dockerfile (`c3c test` and `ninja fmt-check`) or a Wolfi container. hydrant runs on arm64, so use `ubuntu-24.04-arm`.
  4. **Phase 3:** bo inside its Dockerfile's `deps` stage, pushed to GHCR (depends on item 6), then cmake and ctest.
- **Depends:** items 2, 7 and 8 (tests passing), item 6 (images) and item 20 (cmd's argon2 path).
- **Verify:** run `actionlint` locally. On a PR branch, a change touching only `blackkeys-dwa/` runs only the dwa job. **Pushing a branch or opening a PR needs your approval.**

---

## 5. P2 — Finish half-built features

### 11. Hydrant signup consumer: real logic, and what hydrant is for  `[feature]` `M`
- **Goal:** Replace the current print-and-republish behavior with decode → handle → ack or reject.
- **Evidence:**
  - `usersignup.c3:28-37` prints the message. `:79-83` republishes the simulated users, and a publish failure is fatal.
  - `mqshim.c` has only an ack (`:349`), no reject.
  - ws already reads through `auth:user:*` (`repositories.py:84-115`).
  - **If hydrant wrote the cache with `set` while ws publishes concurrently, a conflicting signup could overwrite an existing user's hash for 210 s.** That is why D2 recommends (B).
- **Decision (D2):** (B), hydrant writes nothing to the auth cache.
- **Files:** `src/hydrant/consumers/usersignup.c3`, `src/main.c3`, `3rdparty/mqshim.{c,h}`, `src/interop/mq.c3`, `test/usersignup.c3`.
- **Approach:**
  1. Add `mq_consumer_reject(consumer, requeue)` using `amqp_basic_reject`, exposed as `Consumer.reject`.
  2. Make `handle(char[] body)` a pure function returning `ACK` or `REJECT`. A message that fails to decode is rejected without requeue. A valid message logs the username only.
  3. Remove the password printing, the publish, and the `records` parameter. `consume(settings)` no longer takes a cache.
  4. With MQ configured, an empty record set is no longer fatal.
  5. Under (A) only: `cache.add(key, encode(username, hash), ttl)`; if the key already exists, ack; on a transient error, retry.
- **Reuse:** `userauth::key` and `encode`, `fbufs::decode_user_signup`, the hex fixtures in `test/usersignup.c3`.
- **Depends:** items 1 and 2. Shares the mqshim changes with item 14.
- **Verify:** `ninja test` in hydrant. New tests: `handle()` returns REJECT for garbage, for a BKUA buffer and for a truncated buffer, and ACK for a valid BKUS message.
- **Open question:** under (B), keep the signup queue at all? For example, as a hook for a future welcome email. A dead-letter queue would have to be a RabbitMQ *policy*, because ws declares the queue `durable=True` with no arguments.

### 12. Events data source, then iOS `EventsView` and dwa `/events/`  `[feature]` `L`
- **Goal:** `/v1/events/list` gets a real source, and both clients drop their sample data.
- **Evidence:**
  - ws `cache.py:188-199` reads the events key, but nothing writes it.
  - `repositories.py:194-225` falls back to `ASSETS_HOST + /events` (`services/events.py:6,24`). No service serves that path, and compose doesn't set `ASSETS_HOST`, so the result is always 503.
  - `backends/stores/local.py:3-11` has no TTL.
  - `hydration.c3:24-33` only prints the message.
  - The sample data lives in iOS `home/EventsView.swift:19-31` and dwa `blueprints/events.py:58-137`.
- **Decision (D3):** an assets `Events` RPC. Adding Parquet and a gRPC client in C3 would cost more than it is worth.
- **Approach:**
  1. **proto:** an `Event` message (`id`, `title`, `category`, `starts_at`/`ends_at` as Timestamps, `location`, `description`, `brand_name`, `picture_url`, `featured`, `tags`) and `service Events { rpc List }`.
  2. **assets:** decode `events.parquet` the same way as `brandRecord`, load it with item 13's reloader, and register the server with health. A missing object yields an empty list, not a startup failure.
  3. **ws:** run `ninja protos`. Add an `EventsService` gRPC client (copy of `services/brands.py`) and `WriteEventsList` with a TTL of about 300 s. The repository goes memcached → gRPC → write-back. Remove the local cache, the hydration publish and `ASSETS_HOST`.
  4. **iOS:** an `EventService` modeled on `BrandService.swift` (Codable `Event`, a file cache, the same error enum, Bearer token, `.iso8601` dates). Add `LoadState` to `EventsView`, and pass the token from `HomeView:56`.
  5. **dwa (after item 15):** fetch with Bearer, format times in America/Lima, and split featured from upcoming events.
- **Reuse:** `handling/brands.go`, `BrandsFromResponse` (`services/brands.py:17`), `_SetReplicated`, `BrandService.swift`, `BrandsStatusViews.swift`.
- **Depends:** item 13 (the reloader), item 15 (dwa), item 16 (the iOS 401 path). Once this lands, the hydration half of items 11 and 14 is no longer needed.
- **Verify:**
  - assets: `ninja test` (fixture in `samples/`).
  - ws: `ninja protos && pdm run python -m unittest discover` (update `tests/test_events.py`).
  - iOS: `xcodebuild test`, with new `EventServiceTests` using URLProtocol stubs.
  - dwa: `unittest discover` with a stubbed `api_client`.
- **Open questions:** who authors `events.parquet` (bo or an ETL)? What is the time-zone contract?

### 13. Make bo's overrides visible in assets  `[gap]` `M`
- **Goal:** assets serves brands with bo's edits applied, and picks up changes without a restart.
- **Evidence:**
  - `blackkeys-assets/blackkeys/storage/brands.go:18,47-67` loads `brands.parquet` once at startup and nothing else.
  - bo's overlay format (`storage/overrides.cpp:10-61`) is `{"<name>": {"<column>": "<string>"}}`. bo applies it while skipping `name` (`common.cpp:226-244`). Bools are stored as `"true"`/`"false"` and ints as decimal strings.
  - There are two stale-data layers on top: the assets memcached list (15 min) and ws `BRANDS_LIST_CACHE_TTL_SECONDS=4500` (`cache.py:204`).
- **Decision (D4):** assets applies the overlay. Creates, deletes and renames already rewrite the Parquet file, and assets doesn't see those either, so a reload is needed regardless.
- **Files:** `blackkeys/storage/brands.go`, `blackkeys/handling/brands.go`, `blackkeys/core/conf.go` (`ASSETS_RELOAD_SECONDS=60`), a new `handling/overrides.go` with tests, and ws's `cache.py:204`.
- **Approach:**
  1. storage: `HeadETag` and `FetchObject`. A missing overlay is treated as an empty map.
  2. `parseOverrides`, mirroring bo's `ParseOverrides`.
  3. `applyOverrides`:
     - string columns are set directly;
     - `is_active` is parsed as a bool, and `kiosk_id` with `ParseInt(…,10,32)`;
     - the `name` key and unknown keys are skipped;
     - values that fail to parse are logged and skipped.
  4. Keep the current snapshot in an `atomic.Pointer[snapshot{brands, version}]`, where version is the sha256 of the two ETags. A ticker goroutine checks both objects with HEAD and swaps in a new snapshot only when an ETag changes. On error, the old snapshot stays.
  5. Version the memcached key (`…:brands:list:v1:<version>`), and lower ws's brands TTL to 300 s.
- **Reuse:** `decodeBrands`, `NewS3Client`, the `newBrandsService` test injection, the bo `overrides-test.cc` samples.
- **Verify:** `ninja test` in `blackkeys-assets`. New tests: `TestApplyOverridesScalars`, `…BadIntSkipped`, `…IgnoresName`, `TestReloadSwapsOnETagChange`, `TestReloadKeepsOnError`. Plus ws unittest.
- **Note:** after this change, an edit reaches clients within about 6 minutes, plus the iOS cache TTL.

### 14. Hydrant resilience: reconnect, heartbeat, fail loudly  `[reliability]` `M`
- **Goal:** Hydrant survives broker restarts, and exits non-zero when it cannot recover.
- **Evidence:**
  - `main.c3:64-73` detaches the hydration thread. `hydration.c3:45-73` returns 1 on failure, so the thread dies silently.
  - There is no reconnect logic.
  - `mqshim.c:206-208` sets the heartbeat to 0.
  - Compose uses `restart: unless-stopped` (`:431`).
- **Approach:**
  1. mqshim keeps the connection parameters in `MqConsumer` and gains `mq_consumer_reconnect()` (round-robin over the nodes) and `mq_consumer_fatal()`. Fatal covers bad config, ACCESS_REFUSED, and queue 404 or 406.
  2. Set the heartbeat via `MQ_HEARTBEAT_SECONDS=30`.
  3. A new `runner::run(settings, queue, handler)` loops wait → handle → ack or reject. On recoverable errors it reconnects with backoff min(30, 2^n) plus jitter, resetting after each successful delivery. When the error is fatal, or `HYDRANT_MQ_RETRY_LIMIT_SECONDS=600` is exhausted, it calls `fail()`, which logs and does `exit(1)`.
  4. Both consumers use the runner. If a thread ever needs memcached, it gets its own `memcached_st`.
  5. Treat a broker that is unreachable at startup as retryable.
- **Depends:** do this together with item 11. After item 12, the hydration consumer may simply be deleted.
- **Verify:** `ninja test`, plus pure-function tests for the `backoff()` bounds and for `classify()` (fatal vs retry). Manual check (with your approval): `docker compose restart rabbitmq1` should be followed by reconnect logs.

### 15. dwa: sessions, CSRF, sign-out, live `/stores/`  `[feature]` `M`
- **Goal:** dwa keeps the ws token after sign-in, protects its POSTs, offers sign-out, and shows real brands on `/stores/`.
- **Evidence:**
  - `blueprints/auth.py:73-79` and `:180-190` check the token and then discard it.
  - `core/conf.py` has no secret.
  - `blueprints/stores.py:19-145` is hard-coded.
  - On the ws side, `RequireSession` expects `Bearer blackkeys-v1_…` (`middlewares.py:11-45`), and tokens last 7 days.
- **Approach:**
  1. `sessions.py`: `SealToken` and `OpenToken`, using HMAC-SHA256 with `SECRET` and a constant-time comparison. The `bk_session` cookie is HttpOnly, SameSite=Lax, Secure unless `COOKIE_SECURE=0`, with Max-Age taken from the token's `exp`.
  2. On sign-in, set the cookie on both the HX-Redirect and the 303 response.
  3. CSRF uses a double-submit `bk_csrf` cookie: SameSite=Strict, sent back via `hx-headers` and a hidden form field, plus an Origin/Referer check. A failed check returns 403. This also covers the sign-in and sign-up forms against login CSRF.
  4. `POST /signout/` clears the cookie and redirects to `/signin/`.
  5. A `@RequireWebSession` guard redirects to `/signin/?next=…`, accepting only relative `next` values.
  6. `/stores/` calls `GET /v1/brands/list` with Bearer:
     - 401: clear the cookie and redirect;
     - 503 or a network error: show the `demo_notice` message.
- **Reuse:** `IsHtmx` (`utils.py:4`), `RenderAppPage`, `StoreView`/`STORE_TINTS`, the HMAC pattern from ws's `core/auth.py:29-38`.
- **Verify:** `pdm run python -m unittest discover` in `blackkeys-dwa`. New tests:
  - sign-in sets an HttpOnly cookie;
  - a tampered cookie redirects;
  - a POST with no CSRF token gets 403, and a bad Origin gets 403;
  - sign-out clears the cookie;
  - `/stores/` handles 200, 401 and 503.
- **Open questions:** does htmx 4 still support `hx-headers`? ws has no token revocation. Should `/` and `/events/` also require sign-in?

### 16. iOS: handle 401, add sign-out, bound the image cache  `[ios]` `M`
- **Goal:** A 401 takes the user back to sign-in, there is a sign-out control, and the image cache is bounded and kept off the main thread.
- **Evidence:**
  - `BrandsView.swift:40-43,68-79` retries with the expired token.
  - `ContentView.swift:11,21` gives no way to clear the session.
  - `BrandImageCache.swift:12-76` has no size limits.
  - `BrandCards.swift:16-22` reads from disk on the main actor.
  - The brand cache TTL is 630 s (`core/conf.swift:5`).
- **Approach:**
  1. `ContentView.signOut()` is passed down as `onSignOut` to `HomeView`, then to `BrandsView`, and later to `EventsView`.
  2. A `.sessionExpired` error shows "Sign in again", which calls `onSignOut`.
  3. The `HomeView` username chip becomes a `Menu` containing a sign-out option.
  4. Cache limits: `NSCache.totalCostLimit = 50 MB`. The disk cache tracks access time and prunes the oldest files past 100 MB, off the main thread.
  5. `BrandCardImage.init` checks only the memory cache; disk and network loads happen in `.task`, with `byPreparingForDisplay()`.
- **Verify:** `xcodebuild test …`. New tests: pruning, a memory-only init (using a spy cache), 401 mapping to `.sessionExpired`, and a UI test that sign-out returns to `SignInView`.
- **Open question:** the session is never saved to the Keychain, so every launch requires sign-in. Is that intended?

### 17. bo create/delete success tests; assets storage tests  `[tests]` `S`
- **Goal:** Cover the success paths that can now be tested, and remove the comments that claim they can't.
- **Evidence:**
  - bo already has `MemoryObjectStore`, `ScopedObjectStore` and `BuildBrandsParquet` in `routes-test.cc:127-186`.
  - create and delete are only tested for failure without S3 (`:248-268,745-770`).
  - The stale comments are at `brands_create.cpp:34-40` and `brands_delete.cpp:11-16`.
  - assets `storage/` has no tests. The `NoSuchKey` → `ErrImageNotFound` mapping is at `storage/brands.go:80-84`.
- **Approach:**
  1. bo: add `CreateResponse` and `DeleteResponse` helpers.
  2. bo create tests: success returns 302 and the table has 2 rows; a duplicate returns 409 with no writes; a bad name returns 400; a write error returns 502.
  3. bo delete tests:
     - success removes the row and the brand's overlay entry;
     - no overlay file: one write;
     - a Parquet write failure returns 502 and leaves the overlay untouched;
     - an overlay parse error after the Parquet write returns 502 (this pins down today's partial-write behavior).
  4. assets: an `httptest.Server` fake S3 (path-style, via `NewS3Client`):
     - 404 NoSuchKey maps to `ErrImageNotFound`;
     - 403 maps to a wrapped error;
     - a missing content type defaults to `image/png`;
     - `image/webp` passes through.
- **Verify:** the bo `cmake … && ctest` command, and `ninja test` in assets.
- **Open questions:** deleting a brand leaves its images in S3. Creating a brand doesn't clear a leftover overlay entry with the same name. Should either be fixed?

---

## 6. P3 — Hygiene, ops, docs and memory

### 18. Correct the context files, then compact them  `[docs/memory]` `L`
- **Goal:** All 9 `blackkeys*.md` contexts (about 394 KB in total) match the source, and the oversized ones are compacted without losing anything.
- **Evidence (sample):**

  | Context | Stale or wrong claims |
  |---|---|
  | ws | `/blackkeys-ws` prefix (`:35-39,117`); `events_unavailable`; "no hydration consumer"; hydrant TTL 0 (it is 210); 4 commands (there are 5); repo path; 122 KB |
  | hydrant | standalone repo path; "monorepo absent"; 12 roster entries (there are 7); `schema/` (actual name `schemas/`); `src/argon2phc.c3` (actual `src/interop/argon2phc.c3`); "order-sensitive" failures; "no Dockerfile" |
  | assets | Stores architecture; fragment at `:71`; "comment-free" claim |
  | bo | "nothing scrapes it"; bind is `::`; aws-sdk 1.11.885 |
  | ecosystem | Grafana memory is 768 MB; `http_service` contradiction; reconcile script that doesn't exist; Prometheus retention of 5d not recorded |
  | ios | "24 h" TTL; `AsyncImage`; test state |
  | dwa | paths; port |
  | root | scope table covers only cmd and ios; still names stores rather than brands |

- **Approach (split):**
  1. **Phase A, now:** line-level fixes of false claims only. Archive any displaced unique text first (`archive-context.sh --label pre-correction`). This stops agents from acting on false memory.
  2. **Phase B, after the code items land:** use the context-compaction skill on **one file at a time**, in the order ws → bo → assets → ecosystem → hydrant → ios → dwa → root. For each file:
     - hash the current file, then archive it and `cmp` the copy;
     - classify every unit;
     - rewrite from the template (ws ≤ 25 KB, the others ≤ 15 KB);
     - write the ledger and the README index row;
     - run `verify-archive.sh` and `validate-context.sh`, and check the hash again just before replacing the file.

     cmd is skipped; it is already small.
  3. Update the repo paths to `/Users/gcca/Developer/blackkeys/<sub>`. The root context's scope table should cover all 8 subprojects.
- **Verify:**
  - `cmp` and SHA-256 match for each archived file.
  - Every ledger row is resolved.
  - Grepping for `blackkeys-ws/v`, `events_unavailable`, `Developer/blackkeys-hydrant` and `schema/` returns nothing.
  - `resolve-ctx.sh` reports a healthy status in every subproject.
- **Risks:** `companions` commits automatically with timestamp messages, so an archive counts as provisional until its commit appears in `git log`.

### 19. Ecosystem ops cleanup  `[ops]` `M`
- **Evidence:**
  - `grafana/reconcile-dashboards.py` **was never committed**, but the context describes it at `:304-313,445-453`.
  - `grafana/fly.toml` lacks `GF_AUTH_ANONYMOUS_ORG_ROLE`, although the context requires it.
  - `rules.yaml:55,103,151,199` send alerts to `grafana-default-email`, but no SMTP is configured.
  - The thresholds at `rules.yaml:141,189` are placeholders (`20000000`).
  - `.pre-commit-config.yaml` is a Django template, in a repo with no Django.
- **Approach:**
  1. Remove the reconcile script from the deploy order (item 18A). Rely on `foldersFromFilesStructure`. Rewrite the script to its spec only if nested folders are truly needed.
  2. Set the anonymous role according to D7.
  3. Provision a contact point from a Fly secret via `$__env{}` (a new `contactpoints.yaml` loaded via `[[files]]`), or pause the rules until one exists.
  4. Put units in the thresholds, and derive the values from the 5 days of Prometheus history.
  5. Replace pre-commit with `check-yaml`, `check-json`, `check-toml`, EOF and trailing-whitespace hooks, plus optionally `promtool check config`.
- **Verify:** `docker compose config` and `promtool check config prometheus/prometheus.yml`. Check provisioning on a local Grafana via `/api/v1/provisioning/contact-points`. Run `pre-commit run -a`. **No `fly deploy` without your authorization.**

### 20. cmd: password from stdin, portable build graph; pin pyturso in ws  `[tech-debt]` `M`
- **Evidence:**
  - `create_user/src/main.rs:73` and `change_password/src/main.rs:71` take `-p <password>`.
  - `build.ninja:8,20,35` hard-code the argon2 path.
  - The generic rule `cargo_build` (`:1-3`) builds only `list_users`.
  - Each crate has its own separate `target/` directory.
  - The `sqlite3.rs` modules actually wrap `turso`.
  - ws has `pyturso>=0.7.2`.
  - `list_users` has no `LIMIT`.
- **Approach:**
  1. Add `--password-stdin`. If no password is given and stdin is a TTY, prompt without echo. Keep `-p`, with a deprecation warning on stderr. Keep the parsing in pure functions.
  2. Add a ninja variable `argon2_lib`, and rename the rule to `cargo_build_list_users`.
  3. Use one shared `CARGO_TARGET_DIR=$$PWD/target`, not a Cargo workspace.
  4. `git mv` each `sqlite3.rs` → `db.rs`.
  5. Add `list_users --limit N` as a bound parameter.
  6. In ws, pin `pyturso==0.7.2` and run `pdm lock`. The lock hash changes, so the deps image needs a rebuild (item 6).
- **Verify:**
  - `ninja all && ninja test` in `blackkeys-cmd`.
  - `printf 'pw\n' | bin/blackkeys-create_user … --password-stdin -d <scratch.db>`, and confirm with `ps` that no password appears in argv.
  - ws unittest.

### 21. Repo hygiene  `[hygiene]` `M`
- **Evidence:**
  - There is no root README or `.gitignore`.
  - Per-user xcuserdata files are committed.
  - `blackkeys-assets-bo/.gitignore` line 2 contains a stray terminal escape (`\e[120;5u`), so `uploads/` is ignored only through the local `.git/info/exclude`.
  - The two copies of the 24 MB `SignInBackground.mp4` are the same blob.
  - ws lists `grpcio-tools` as a runtime dependency.
  - ws and dwa reference a `README.md` that doesn't exist.
  - The ws license string is `AGPL-GPL-3.0-or-later`.
  - Four stale standalone clones exist: `~/Developer/blackkeys-{ws,dwa,ecosystem,hydrant}`, each with a `CTX.md` pointing at the same canonical context.
  - `.agents/skills` and `.claude/skills` are untracked and have drifted from `companions`.
- **Approach:**
  1. Root README: a table of subproject, language, build tool, test command and `CTX.md` link, plus the timestamp commit convention.
  2. Root `.gitignore`: `xcuserdata/`, `__pycache__/`, `*.db`, `*.db-*`, `.DS_Store`, `/.agents/`, `/.claude/`. Run `git rm --cached` on the xcuserdata files.
  3. Fix bo's `.gitignore` line 2 to read `uploads/`.
  4. Video: `git lfs track '*.mp4'` from now on. Rewriting history is your call (D8).
  5. ws: move `grpcio-tools` to the dev dependency group, add short READMEs (or drop the `readme` key) in ws and dwa, and set the license to `AGPL-3.0-or-later`.
  6. Archive the stale clones (D8). Their `CTX.md` links can mislead agents.
  7. Make the skills trees symlinks to `companions/mdagents/skills`.
  8. Keep the per-subproject LICENSE files.
- **Verify:**
  - `git -c core.excludesFile=/dev/null check-ignore -v <paths>` for each new pattern.
  - `pdm lock --check` in ws and dwa.
  - `git status` is clean.

### 22. Authentication for assets-bo  `[security]` `S`
- **Evidence:**
  - `brand/routes.hpp:10-18` exposes create, update and delete with no authentication.
  - `fly.toml` has no public service, but the app binds `::` (`Dockerfile:128`, `options.hpp:12`), so it is reachable from every machine and WireGuard peer on the org's 6PN network.
  - The UI uses plain HTML forms.
- **Approach:**
  1. Settings `BO_BASIC_PASSWORD` (a Fly secret) and `BO_BASIC_USER` (default `blackkeys`).
  2. Use `registerPreRoutingAdvice` to require Basic auth on every route except `/healthcheck`, compared in constant time. A failure returns 401 with `WWW-Authenticate`.
  3. Reject POSTs whose `Origin` doesn't match.
  4. If no password is set and the bind address isn't loopback, exit non-zero at startup.
  5. Document that bo stays reachable only through the proxy.
- **Reuse:** `RequireEnv`/`ReadEnv` in `settings.cpp`, the `settings-test.cc` env fixture, the gtest patterns in `routes-test.cc`.
- **Verify:**
  - gtest cases for missing, wrong and correct credentials, the `/healthcheck` exemption, and the startup guard.
  - Locally, `curl -u` returns 200 and a request without credentials returns 401.
  - **`fly secrets set` before the next deploy needs your authorization.**

---

## 7. Recommended order

1. **Item 18A:** fix the false claims in the contexts, so agents stop acting on them.
2. **Items 1 and 2 together (P0),** then **item 8** (it depends on item 1's `prepare` signature) and **item 5** (it uses item 2's hasher).
3. **Items 3, 4 and 22:** small and independent.
4. **Items 7, 6 and 10 phase 1.** CI goes green once items 2, 7 and 8 have landed.
5. **Item 9** can run in parallel. It needs your approval for DerivedData and simulator resets.
6. **Item 17,** which provides the fake S3 for item 13. Then **items 11 and 14** together, then **item 13**, then the **item 12 backend**.
7. **Item 16,** then **item 15,** then the **item 12 clients** (iOS `EventService` and dwa `/events/`).
8. **Items 20 and 21,** then **item 10 phases 2 and 3,** then **item 19.**
9. **Item 18B last:** compact each context one at a time against the final state.

## 8. Critical files

- `blackkeys-hydrant/src/main.c3`, `src/hydrant/{populate,core/conf,consumers/usersignup}.c3`, `3rdparty/mqshim.c`
- `blackkeys-ws/blackkeys/{repositories,application}.py`, `backends/{publishers/signup,services/brands,stores/db,stores/cache}.py`, `commands/local_create_user.py`
- `blackkeys-assets/blackkeys/{storage,handling}/brands.go`, `protos/v1/service.proto`
- `blackkeys-assets-bo/src/blackkeys/assetsbo/handling/brand/routes/{common.cpp,brands_create.cpp,brands_delete.cpp}`, `src/assetsbo.cc`
- `blackkeys-ecosystem/{docker-compose.yaml,nginx.conf,grafana/fly.toml}`
- `blackkeys-dwa/blackkeys/{core/conf.py,blueprints/auth.py,blueprints/stores.py}`
- `blackkeys-ios/blackkeys/{ContentView.swift,home/HomeView.swift,home/brands/*}`
- `.github/workflows/{blackkeys-ws-deps.yaml,ci.yaml}`
- `companions/mdagents/blackkeys*.md`, `companions/mdagents/rules/compaction.md`
