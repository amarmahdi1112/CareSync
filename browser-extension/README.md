# CareSync Attendance Entry

A stateful Chrome extension for entering CareSync daily attendance into the daycare portal's visible room attendance page. It follows the portal's normal controls and waits for the page to confirm each write before continuing.

The extension is designed for CareSync's **Daily CSV ZIP** export. It does not scrape credentials, bypass the portal, or call private portal endpoints directly.

## Build

Requirements:

- Node.js 20 or newer
- npm
- Google Chrome or a Chromium browser with Manifest V3 support

From this directory:

```bash
npm install
npm run build
```

The loadable extension is written to `dist/`.

To run the automated checks:

```bash
npm test
```

## Load the extension in Chrome

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Select **Load unpacked**.
4. Choose this project's `browser-extension/dist` directory.
5. Pin **CareSync Attendance Entry** so its panel is easy to reopen.

After rebuilding, return to `chrome://extensions` and select the extension's reload button before testing the new build.

## Prepare the portal and CareSync data

1. In CareSync, generate the schedules you intend to enter.
2. Open **Export** and download **Daily CSV ZIP**. The archive may contain children from the whole daycare, not only the room you are about to enter.
3. Sign in to the daycare portal yourself.
4. Navigate to the attendance page and make the intended room visible — for example, **Infants**.
5. Check that the portal shows the correct room before connecting. The extension acts only on the room currently displayed.

The CareSync ZIP may contain one or two attendance sessions for a child on a date. Both sessions are validated and processed in order. Empty second-session fields are treated as a single-session day. A partial session — start without end, or end without start — is rejected rather than guessed.

KinderLogix's attendance controls use five-minute increments. The extension converts non-grid source values to the nearest five minutes before comparing or writing them and records the number of adjusted IN/OUT values in the run log. For example, `14:26` becomes `2:25 pm`. Rounding that would cross midnight is rejected.

## Review and run

Open the extension and complete the workflow in order:

1. Select **Connect this tab**. Chrome grants access only to the current portal origin.
2. Select **Scan room**. Confirm that the detected room and portal children are the ones you expect.
3. Select **Choose CareSync ZIP** and choose the Daily CSV ZIP.
4. Review **Room matching**. Exact normalized-name matches are marked automatically, and the selectors remain available for manual corrections.
5. Open the separate **AI recommendation approval** section and select **Generate AI recommendations with DeepSeek**. Approve or deny every returned pair there; DeepSeek recommendations are never applied automatically. Denied pairs move into a saved queue, where **Rematch denied children** requests different candidates for only those unresolved children.
6. Check the room-scope confirmation only after verifying that the remaining children belong to other rooms, then review the date range, room, child mappings, attendance sessions, and warnings.
7. Authorize the date-by-date pipeline only after confirming the room and ZIP dates. On each date, the extension removes every existing session visible in that room, enters and verifies only the approved mapped schedules for that same date, and then advances.

Name matching uses a reviewable confidence workflow. It first resolves unique normalized exact names in the browser. The optional DeepSeek pass receives only unresolved names and opaque per-list IDs through the local CareSync backend; it never receives attendance dates, IN/OUT times, schedules, or the ZIP. Every DeepSeek candidate—regardless of confidence—is held for operator review in the separate **AI recommendation approval** section and is never applied automatically. Every row shows the CareSync child, suggested KinderLogix child, confidence, reason, and direct **Approve this match** and **Deny** buttons.

To avoid model output truncation on large rooms, the backend splits portal children into bounded batches (20 by default), combines every completion, keeps the highest-confidence globally unique source/portal pairs, and runs a second pass when recommendations from different chunks compete for the same source child. If DeepSeek still reaches its output limit, only the affected batch is discarded and automatically divided into smaller batches until a complete JSON result is returned; partial JSON is never applied. One shared provider-call ceiling and elapsed deadline bound the complete first pass, recursive recovery, and collision-repair pass. The panel reports the total number of DeepSeek attempts used. Configure these limits with `DEEPSEEK_NAME_MATCH_CHUNK_SIZE`, `DEEPSEEK_NAME_MATCH_MAX_PROVIDER_CALLS`, and `DEEPSEEK_NAME_MATCH_DEADLINE_SECONDS` in `backend/.env`.

If a bounded recovery still cannot finish, the provider times out, the backend returns a transient failure, or the response is unreadable, the extension preserves the ZIP, current room, approved mappings, and denied pairs, then shows a durable **Retry** action in the AI approval section. A five-minute browser request timeout prevents the panel from waiting indefinitely. Reopening the panel does not lose that recovery state, and duplicate clicks share one in-flight request instead of starting competing matches.

Confirmed exact, AI-assisted, and manual mappings are remembered in local extension storage across monthly ZIP imports. A remembered mapping is restored only when the CareSync child ID and normalized name, KinderLogix child ID and normalized name, and portal room ID all still match. Manually clearing a mapping also removes it from memory, so a known-bad association does not return on the next import.

Denied AI recommendations are also remembered across monthly ZIP imports and extension restarts. Each decision is scoped to the exact CareSync child, KinderLogix child, and portal room, and both names are revalidated before the decision is reused. A rematch sends only still-unresolved denied children and forbids every rejected pair; approved mappings are left untouched. Approving an alternative clears that child's denied history. Use **Forget name decisions** only when you intentionally want to clear both remembered mappings and denied pairs.

## Configure AI name matching

Keep the DeepSeek API key in `backend/.env`; never put it in the extension manifest, source, or Chrome storage:

```dotenv
DEEPSEEK_API_KEY=your-key-here
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_NAME_MATCH_THRESHOLD=0.92
DEEPSEEK_NAME_MATCH_CHUNK_SIZE=20
DEEPSEEK_NAME_MATCH_MAX_PROVIDER_CALLS=300
DEEPSEEK_NAME_MATCH_DEADLINE_SECONDS=180
```

Start CareSync Basic on `127.0.0.1:3002` before selecting the DeepSeek button. Basic mounts only the narrow `/api/v1/ai/name-matches` adapter from the compatibility AI surface. The adapter is restricted to loopback requests from a Chrome-extension origin, reads no tenant records, accepts only bounded child IDs/names and denied ID pairs, and keeps the provider key on the backend. After changing the manifest or rebuilding, reload the unpacked extension from `chrome://extensions`.

Every authorized run uses a durable date-by-date loop:

1. Opens the next included ZIP date and confirms that the intended room and date are visible.
2. **Cleans that date:** removes every existing attendance session for every child visible in the selected room, waiting for server-rendered deletion confirmation after every action.
3. **Enters and verifies that date:** writes each approved mapped IN time, waits for the saved/green confirmation, writes the OUT time, and waits for the completed/red confirmation. A validated second session is processed in order when present.
4. Advances to the next date only after cleanup and entry for the current date are complete.

Deletion is restricted to step 2. After entry begins for a date, the extension never automatically deletes a saved, partial, or unexpected row; it preserves the portal data, records the issue, and continues.

The durable checkpoint records both the date and its current `dayStage` (`cleanup` or `entry`), plus the child, session, and portal action. Pausing, closing the panel, or reloading the portal resumes that exact date stage rather than restarting the batch. Cleanup is page-wide only within the selected room and current imported date; it never targets another room or dates outside the ZIP.

Recoverable date-child problems are recorded in the activity log and skipped so the batch can continue. For example, if an approved mapped child is not visible on a particular date, that date-child record is logged and the remaining records still run. A safety or portal-state failure pauses at the saved checkpoint instead; correct the reported condition and select **Resume checkpoint**. Do not interpret a warning or skipped-record count as a halted batch.

Keep the portal tab open and signed in while a run is active. Avoid manually editing the same room in another tab at the same time.

## Pause, resume, and stop

- **Pause** prevents the extension from starting another portal action. A request already in flight may still finish; **Resume** reconciles the saved checkpoint with the visible portal row before continuing.
- **Resume** continues from the persisted date stage, child, session, and action. After a safety failure, **Resume checkpoint** retries from that same protected point after you correct the reported condition.
- **Stop** cancels the run. It does not undo records the portal already confirmed.

Run progress, mappings, warnings, and the activity log are saved in Chrome extension storage. Reopening the panel or reloading the portal page does not restart a running or paused job from the beginning. The extension reconciles persisted progress with the visible portal state before continuing, so an action confirmed immediately before a reload is not blindly repeated.

Do not clear the extension's site data, remove the extension, or load a different build during an active run. Those actions can remove its recovery state.

## Safety rules

- Verify the visible portal room before scanning and again before starting.
- Use a freshly generated CareSync Daily CSV ZIP for the intended schedule batch.
- Review every AI-assisted or manual match in the visible room. Confirm unmapped children are outside this room; never use that confirmation to dismiss a missing room child.
- Inspect duplicate child/date records and partial sessions. The extension blocks unsafe data rather than choosing one.
- For each included ZIP date, cleanup deletes all existing portal attendance visible in the selected room before that date's new values are entered. The authorization checkbox is intentionally required for every reviewed run.
- Watch the activity log. Recoverable confirmation failures are retried and recorded while the batch continues; wrong-room, wrong-date, signed-out, or unsupported-page conditions preserve the checkpoint for a safe resume.
- Keep the original CareSync ZIP and the portal's audit/export records until the run has been reviewed.
- Test with a small date range before processing a full room.

The extension has automated tests for its local parsing, exact matching, validation, and date/time conversion logic. Its browser state machine has not been exercised against the live production daycare portal. Begin with a controlled portal test and independently verify the resulting attendance before a larger run.

## Troubleshooting

### An old error or checkpoint keeps returning

The extension intentionally stores recovery state in `chrome.storage.local`, so reloading the panel does not clear errors or checkpoints. Open **Local data & recovery** at the bottom of the panel and choose the narrowest applicable action:

- **Clear saved error** keeps the ZIP, mappings, checkpoint, and logs.
- **Clear run history** removes the checkpoint, progress, error, and activity log while keeping the ZIP and remembered names.
- **Remove imported ZIP** removes the ZIP, active mappings, and run history but preserves long-term name memory.
- **Forget name decisions** clears active and remembered child associations plus denied AI pairs while keeping the imported ZIP.
- **Reset all local data** removes all extension-owned local state, including the portal connection.

These controls are locked while a run is active. Stop the run before clearing recovery data; pausing alone deliberately preserves the checkpoint.

### Connect this tab does not work

Open the actual attendance page in the active tab and try again. Chrome must be allowed to grant the extension access to that portal origin. Restricted browser pages such as `chrome://` cannot be connected.

After Chrome restarts, its numeric tab IDs change. The extension validates the saved tab whenever the panel opens, removes only a dead connection/room snapshot, and preserves the imported ZIP, remembered names, denied AI pairs, and any recovery checkpoint. Keep the intended KinderLogix room open and select **Connect this tab** again. A checkpointed run is kept paused until you explicitly resume it on the reviewed room.

### Scan room finds no children

Make sure the date-specific attendance table has finished loading and the intended room is visible. Refresh the portal page, reopen the room, then scan again. Do not start if the reported room is wrong.

### A child is unmatched or ambiguous

First start the local CareSync backend and select **Generate AI recommendations with DeepSeek** in the separate AI approval section. If the matcher remains uncertain, use the portal-child selector manually. If the correct portal child is absent, stop and correct the portal room or source records. Children from other rooms may remain unmapped only after you explicitly confirm that room scope.

### DeepSeek matching is unavailable

Confirm CareSync Basic is running on `127.0.0.1:3002` and `DEEPSEEK_API_KEY` is set in `backend/.env`, then restart the backend. The API key stays on the backend and should never be pasted into the extension.

### The ZIP is rejected

Confirm that it is the unmodified **Daily CSV ZIP** produced by CareSync. Duplicate child/date records, invalid dates or times, incomplete sessions, overlapping sessions, a second session without the first, or missing required columns must be corrected at the source.

### The run pauses on a timeout

Inspect the visible row before resuming. Common causes are an expired login, a portal validation message, network loss, a changed portal layout, or a time outside the portal's permitted range. Do not repeatedly resume until the row's state is understood.

### The log says a record was skipped

A skipped-record warning does not mean the batch stopped. Record-level conditions explicitly classified as recoverable — such as a mapped child not being visible on one particular date — are logged, counted, and bypassed while the extension continues with the remaining records. Review the skipped details after completion and enter only those records manually if appropriate. If the panel instead shows **Checkpoint needs attention**, correct the reported safety or portal-state problem and select **Resume checkpoint**.

### The portal page was reloaded or the panel was closed

Reopen the extension on the same portal tab. Persisted progress should show the last confirmed checkpoint. Use **Resume**; do not import and start a second copy of the same run.

### Existing attendance was only partly replaced

Pause the run and inspect the activity log and visible row. **Stop** does not roll back confirmed writes. Correct the specific portal record manually if necessary, then scan and review again before starting a new run.

## Privacy

The ZIP, schedules, dates, and attendance times remain in the browser's local extension storage and are sent only through the already-open portal page as the operator directs. When the operator explicitly requests AI matching, only currently unresolved child names and opaque identifiers are sent via the loopback CareSync backend to DeepSeek. Treat the browser profile and exported ZIP as sensitive because they contain child attendance information.
