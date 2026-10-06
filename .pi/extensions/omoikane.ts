/**
 * Omoikane session hooks for Pi, the counterpart of .claude/settings.json.
 *
 * - session_start / before_agent_start: the wiki index (omoikane/bin/session-context.py) is appended to the
 *   system prompt of every prompt in the session; computed once per session, like Claude Code's SessionStart.
 * - agent_end / session_shutdown: the session file is captured into omoikane/raw/inbox/sessions/
 *   (omoikane/bin/session-capture.py --harness pi), like Claude Code's Stop and SessionEnd.
 *
 * Both scripts print one line and exit 0 on any failure, and do nothing when OMOIKANE_NO_CAPTURE is set, so
 * this file needs no error handling of its own. Pi loads .pi/extensions/*.ts once the project is trusted
 * (docs/extensions.md of @earendil-works/pi-coding-agent, "Extension Locations").
 */
import { join } from "node:path";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

const CAPTURE = join("omoikane", "bin", "session-capture.py");
const CONTEXT = join("omoikane", "bin", "session-context.py");

export default function omoikane(pi: ExtensionAPI) {
	// Same guard as the scripts: a headless run started by wiki-ingest.ps1 is Omoikane maintaining itself.
	if (process.env.OMOIKANE_NO_CAPTURE) return;

	let index: string | undefined;
	let inFlight: Promise<void> | undefined;

	// agent_end and session_shutdown can fire back to back; one capture at a time, the second call reuses it.
	function capture(ctx: ExtensionContext): Promise<void> {
		const file = ctx.sessionManager.getSessionFile();
		if (!file) return Promise.resolve(); // --no-session: nothing on disk to read
		if (inFlight) return inFlight;
		const args = [join(ctx.cwd, CAPTURE), "--harness", "pi", "--transcript", file, "--session-id", ctx.sessionManager.getSessionId()];
		inFlight = pi
			.exec("python", args, { cwd: ctx.cwd, timeout: 15_000 })
			.then(() => undefined)
			.finally(() => {
				inFlight = undefined;
			});
		return inFlight;
	}

	pi.on("session_start", async () => {
		index = undefined;
	});

	pi.on("before_agent_start", async (event, ctx) => {
		if (index === undefined) {
			const result = await pi.exec("python", [join(ctx.cwd, CONTEXT)], { cwd: ctx.cwd, timeout: 10_000 });
			index = result.code === 0 ? result.stdout.trim() : "";
		}
		if (!index) return;
		return { systemPrompt: `${event.systemPrompt}\n\n${index}` };
	});

	pi.on("agent_end", async (_event, ctx) => capture(ctx));
	pi.on("session_shutdown", async (_event, ctx) => capture(ctx));
}
