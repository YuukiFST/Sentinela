/**
 * Omoikane session hooks for OpenCode, the counterpart of .claude/settings.json.
 *
 * - experimental.chat.system.transform: the wiki index (omoikane/bin/session-context.py) is added to the system
 *   prompt; computed once per session, like Claude Code's SessionStart.
 * - session idle (once per prompt) and dispose (process exit): the session is fetched through the SDK, written as
 *   the `opencode export` document and captured into omoikane/raw/inbox/sessions/
 *   (omoikane/bin/session-capture.py --harness opencode), like Claude Code's Stop and SessionEnd.
 *
 * Both scripts print one line and exit 0 on any failure, and do nothing when OMOIKANE_NO_CAPTURE is set, so this
 * file needs no error handling of its own. OpenCode loads .opencode/plugins/*.ts and installs @opencode-ai/plugin
 * next to it for the types (https://opencode.ai/docs/plugins). Events reach a plugin only for its own directory.
 */
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { Hooks, Plugin } from "@opencode-ai/plugin";

// session.idle and session.status {type: "idle"} both exist in SDK 1.18.30 and can announce the same moment;
// captures requested within this window run once.
const IDLE_SETTLE_MS = 300;

export const OmoikanePlugin: Plugin = async ({ client, directory, $ }) => {
	// Same guard as the scripts: a headless run started by wiki-ingest.ps1 is Omoikane maintaining itself.
	if (process.env.OMOIKANE_NO_CAPTURE) return {};

	const capture = join(directory, "omoikane", "bin", "session-capture.py");
	const context = join(directory, "omoikane", "bin", "session-context.py");
	const indexBySession = new Map<string, string>();
	// Event handlers are fire-and-forget: `opencode run` exits right after the session goes idle, so dispose
	// awaits the capture still in flight and captures sessions whose idle event never came.
	const inFlight = new Map<string, Promise<void>>();
	const timers = new Map<string, ReturnType<typeof setTimeout>>();
	const pending = new Set<string>();

	async function exportAndCapture(sessionID: string): Promise<void> {
		const session = await client.session.get({ path: { id: sessionID } });
		const messages = await client.session.messages({ path: { id: sessionID } });
		if (!session.data || !messages.data) return;
		const dir = join(tmpdir(), "omoikane");
		mkdirSync(dir, { recursive: true });
		const file = join(dir, `${sessionID}.json`);
		writeFileSync(file, JSON.stringify({ info: session.data, messages: messages.data }));
		try {
			await $`python ${capture} --harness opencode --transcript ${file} --session-id ${sessionID}`.cwd(directory).quiet().nothrow();
		} finally {
			rmSync(file, { force: true });
		}
	}

	function captureSession(sessionID: string): Promise<void> {
		const running = inFlight.get(sessionID);
		if (running) return running;
		const run = exportAndCapture(sessionID)
			.then(() => {
				pending.delete(sessionID);
			})
			.catch(() => undefined)
			.finally(() => inFlight.delete(sessionID));
		inFlight.set(sessionID, run);
		return run;
	}

	function captureSoon(sessionID: string): void {
		clearTimeout(timers.get(sessionID));
		timers.set(
			sessionID,
			setTimeout(() => {
				timers.delete(sessionID);
				void captureSession(sessionID);
			}, IDLE_SETTLE_MS),
		);
	}

	return {
		event: async ({ event }) => {
			if (event.type === "message.updated") pending.add(event.properties.info.sessionID);
			if (event.type === "session.idle") captureSoon(event.properties.sessionID);
			if (event.type === "session.status" && event.properties.status.type === "idle") {
				captureSoon(event.properties.sessionID);
			}
		},
		dispose: async () => {
			for (const timer of timers.values()) clearTimeout(timer);
			timers.clear();
			await Promise.allSettled([...pending].map(captureSession));
		},
		"experimental.chat.system.transform": async (input, output) => {
			const key = input.sessionID ?? "";
			if (!indexBySession.has(key)) {
				const result = await $`python ${context}`.cwd(directory).quiet().nothrow();
				indexBySession.set(key, result.exitCode === 0 ? result.text().trim() : "");
			}
			const index = indexBySession.get(key);
			if (index) output.system.push(index);
		},
		// `satisfies`: a returned object is not checked for extra keys, so a misspelled hook name passed tsc (#46).
	} satisfies Hooks;
};
