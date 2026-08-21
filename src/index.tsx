import {
	definePlugin,
	PanelSection,
	PanelSectionRow,
	ToggleField,
	DropdownItem,
	DropdownOption,
	Focusable,
	gamepadDialogClasses,
	Router,
} from "decky-frontend-lib";

import { callable } from "@decky/api";

import React, { VFC, useEffect, useState } from "react";
import { FaMicrophone } from "react-icons/fa";

type RpcResponse = { success: boolean; error?: string; [key: string]: any };

const getStatus = callable<[], RpcResponse>("get_status");
const getButtonConfig = callable<[], RpcResponse>("get_button_config");
const getPresets = callable<[], RpcResponse>("get_presets");
const getWhisperLanguages = callable<[], RpcResponse>("get_whisper_languages");
const setEnabledRpc = callable<[enabled: boolean], RpcResponse>("set_enabled");
const setActivePresetRpc = callable<[game: string], RpcResponse>("set_active_preset");
const setWhisperModelRpc = callable<[model: string], RpcResponse>("set_whisper_model");
const setWhisperLanguageRpc = callable<[language: string], RpcResponse>("set_whisper_language");
const setButtonConfig = callable<[buttons: string[]], RpcResponse>("set_button_config");
const setActiveAppRpc = callable<[app_id: string, name: string], RpcResponse>("set_active_app");

const BUTTON_NAMES = ["L1", "R1", "L2", "R2", "L4", "R4", "L5", "R5", "A", "B", "X", "Y"];
const BUTTON_ROWS = [
	["L1", "R1", "L2", "R2"],
	["L4", "R4", "L5", "R5"],
	["A", "B", "X", "Y"],
];

const MODEL_LABELS: Record<string, string> = {
	tiny: "Tiny (42 MB)",
	base: "Base (78 MB)",
	"small-q5_1": "Small (181 MB)",
	"medium-q5_0": "Medium (514 MB)",
	"large-q5_0": "Large (1031 MB)",
};

const STATUS = {
	off: { color: "rgba(255,255,255,0.28)", hint: "Off", pulse: false },
	loading: { color: "#f5c14a", hint: "Loading model…", pulse: true },
	ready: { color: "#3dd68c", hint: "Ready", pulse: false },
	recording: { color: "#1a9fff", hint: "Listening", pulse: true },
	sending: { color: "#1a9fff", hint: "Sending…", pulse: true },
	error: { color: "#ff6b6b", hint: "Failed to start. See /tmp/deckvoice.log", pulse: false },
	unavailable: { color: "#ff6b6b", hint: "Unavailable", pulse: false },
} as const;

type StatusKind = keyof typeof STATUS;

function statusKind(status: RpcResponse | null, loading: boolean): StatusKind {
	if (loading) return "loading";
	if (!status?.success) return "unavailable";
	if (status.model_loading || status.status === "loading") return "loading";
	if (status.status === "error" || status.model_load_error) return "error";
	if (status.recording) return "recording";
	if (status.status === "transcribing") return "sending";
	if (status.server_ready || status.status === "listening") return "ready";
	return "off";
}

function nextCombo(current: string[], name: string): string[] {
	const next = current.includes(name)
		? current.filter((b) => b !== name)
		: [...current, name];
	if (next.length < 1 || next.length > 5) return current;
	return BUTTON_NAMES.filter((b) => next.includes(b));
}

function readRunningApp(): { appId: string; appName: string } {
	const app = Router.MainRunningApp;
	if (!app?.appid) return { appId: "", appName: "" };
	return {
		appId: String(app.appid),
		appName: String(app.display_name || ""),
	};
}

async function syncActiveApp() {
	const { appId, appName } = readRunningApp();
	try {
		await setActiveAppRpc(appId, appName);
	} catch (_e) {}
}

const CHIP_FOCUS = [
	"dv-chip-focus",
	gamepadDialogClasses["ItemFocusAnim-darkGrey"],
	gamepadDialogClasses.focusAnimation,
]
	.filter(Boolean)
	.join(" ");

const ComboChip: VFC<{ name: string; on: boolean; locked: boolean; onToggle: () => void }> = ({
	name,
	on,
	locked,
	onToggle,
}) => (
	<Focusable
		onActivate={locked ? undefined : onToggle}
		onClick={locked ? undefined : onToggle}
		focusClassName={CHIP_FOCUS}
		style={{
			flex: 1,
			textAlign: "center",
			padding: "8px 0",
			borderRadius: 3,
			background: on ? "rgba(255,255,255,0.16)" : "rgba(255,255,255,0.04)",
			fontSize: 14,
			fontWeight: on ? 600 : 400,
			opacity: locked ? 0.35 : on ? 1 : 0.55,
		}}
	>
		{name}
	</Focusable>
);

const StatusDot: VFC<{ color: string; pulse?: boolean }> = ({ color, pulse }) => (
	<div className={pulse ? "dv-dot dv-dot-pulse" : "dv-dot"} style={{ background: color }} />
);

const DeckVoicePanel: VFC = () => {
	const [enabled, setEnabled] = useState(false);
	const [busy, setBusy] = useState(false);
	const [status, setStatus] = useState<RpcResponse | null>(null);
	const [buttons, setButtons] = useState<string[]>(["L1", "R1"]);
	const [game, setGame] = useState("wow");
	const [presets, setPresets] = useState<Record<string, any>>({});
	const [whisperModel, setWhisperModel] = useState("small-q5_1");
	const [whisperLanguage, setWhisperLanguage] = useState("auto");
	const [modelOptions, setModelOptions] = useState<DropdownOption[]>([]);
	const [languageOptions, setLanguageOptions] = useState<DropdownOption[]>([]);
	const [appId, setAppId] = useState("");
	const [appName, setAppName] = useState("");

	const applyConfig = (cfg: any) => {
		if (!cfg) return;
		setEnabled(!!cfg.enabled);
		setButtons(cfg.buttons || ["L1", "R1"]);
		setGame(cfg.game || "wow");
		setWhisperModel(cfg.whisperModel || "small-q5_1");
		setWhisperLanguage(cfg.whisperLanguage || "auto");
		setAppId(cfg.appId || "");
		setAppName(cfg.appName || "");
	};

	const applyStatus = (next: RpcResponse) => {
		setStatus(next);
		if (next.profileEnabled !== undefined) {
			setEnabled(!!next.profileEnabled);
		} else {
			setEnabled(!!next.enabled);
		}
		const nextAppId = next.appId || "";
		const nextAppName = next.appName || "";
		if (next.appId !== undefined) setAppId(nextAppId);
		if (next.appName !== undefined) setAppName(nextAppName);
		return nextAppId;
	};

	const refresh = async () => {
		const [cfg, status, presetResp, langResp] = await Promise.all([
			getButtonConfig(),
			getStatus(),
			getPresets(),
			getWhisperLanguages(),
		]);
		if (cfg?.success && cfg.config) applyConfig(cfg.config);
		if (status?.success) applyStatus(status);
		if (presetResp?.success) setPresets(presetResp.presets || {});
		if (langResp?.success) {
			setModelOptions(
				(langResp.models || []).map((m: string) => ({
					data: m,
					label: MODEL_LABELS[m] || m,
				}))
			);
			setLanguageOptions(
				(langResp.languages || []).map((code: string) => ({
					data: code,
					label: code === "auto" ? "Auto-detect" : langResp.names?.[code] || code,
				}))
			);
		}
	};

	useEffect(() => {
		refresh();
		const id = setInterval(async () => {
			try {
				const status = await getStatus();
				if (!status?.success) return;
				const nextAppId = applyStatus(status);
				if (nextAppId !== appId) {
					const cfg = await getButtonConfig();
					if (cfg?.success && cfg.config) applyConfig(cfg.config);
				}
			} catch (_e) {}
		}, 1000);
		return () => clearInterval(id);
	}, [appId]);

	const inGame = !!appId;
	const kind = statusKind(status, busy);
	const view = STATUS[kind];
	const locked = kind === "loading";

	const onToggleEnabled = async (value: boolean) => {
		if (!inGame || locked) return;
		setBusy(value);
		setEnabled(value);
		const res = await setEnabledRpc(value);
		if (!res?.success) setEnabled(false);
		await refresh();
		setBusy(false);
	};

	const channelSummary = () => {
		const preset = presets[game];
		if (!preset?.channels || game !== "wow") return null;
		const parts = Object.entries(preset.channels)
			.filter(([name]) => name !== "type")
			.map(([name, prefix]) => `${name} → ${String(prefix).trim() || "raw"}`);
		return (
			<PanelSectionRow>
				<div style={{ fontSize: "12px", opacity: 0.7, lineHeight: 1.45 }}>
					Say a channel first: {parts.slice(0, 4).join(", ")}, …
				</div>
			</PanelSectionRow>
		);
	};

	const presetOptions: DropdownOption[] = Object.entries(presets).map(([key, value]) => ({
		data: key,
		label: (value as { name?: string })?.name || key,
	}));

	return (
		<>
			<style>{`.dv-chip-focus{background:#1a9fff!important;color:#fff!important;opacity:1!important;font-weight:600}.dv-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}.dv-dot-pulse{animation:dv-pulse 1s ease-in-out infinite}@keyframes dv-pulse{50%{opacity:.35}}`}</style>
			<PanelSection title="DeckVoice">
				<PanelSectionRow>
					<div style={{ fontSize: "13px", opacity: 0.8, marginBottom: "6px" }}>
						{inGame ? appName || `App ${appId}` : "No game"}
					</div>
				</PanelSectionRow>
				<PanelSectionRow>
					<ToggleField
						label="Enable"
						icon={<StatusDot color={view.color} pulse={view.pulse} />}
						tooltip={view.hint}
						description={
							kind === "loading"
								? view.hint
								: kind === "error"
									? view.hint
									: inGame
										? "GPU Whisper. Off frees VRAM."
										: "Launch a game to enable"
						}
						checked={enabled}
						disabled={locked || !inGame}
						onChange={onToggleEnabled}
					/>
				</PanelSectionRow>
			</PanelSection>

			<PanelSection title="Recognition">
				<PanelSectionRow>
					<DropdownItem
						label="Model"
						rgOptions={modelOptions}
						selectedOption={whisperModel}
						disabled={locked}
						onChange={async (option: DropdownOption) => {
							const value = String(option.data);
							setWhisperModel(value);
							if (enabled) setBusy(true);
							await setWhisperModelRpc(value);
							await refresh();
							setBusy(false);
						}}
					/>
				</PanelSectionRow>
				<PanelSectionRow>
					<DropdownItem
						label="Language"
						rgOptions={languageOptions}
						selectedOption={whisperLanguage}
						disabled={locked}
						onChange={async (option: DropdownOption) => {
							const value = String(option.data);
							setWhisperLanguage(value);
							if (enabled) setBusy(true);
							await setWhisperLanguageRpc(value);
							await refresh();
							setBusy(false);
						}}
					/>
				</PanelSectionRow>
			</PanelSection>

			<PanelSection title="Profile">
				<PanelSectionRow>
					<DropdownItem
						label="Chat"
						rgOptions={presetOptions}
						selectedOption={game}
						disabled={locked}
						onChange={async (option: DropdownOption) => {
							const value = String(option.data);
							setGame(value);
							await setActivePresetRpc(value);
							await refresh();
						}}
					/>
				</PanelSectionRow>
				{channelSummary()}
			</PanelSection>

			<PanelSection title="Trigger combo">
				<PanelSectionRow>
					<div style={{ fontSize: "12px", opacity: 0.7, marginBottom: "8px" }}>
						Hold {buttons.join(" + ")}
					</div>
				</PanelSectionRow>
				<PanelSectionRow>
					<Focusable style={{ display: "flex", flexDirection: "column", gap: 6 }} noFocusRing={true}>
						{BUTTON_ROWS.map((row) => (
							<Focusable
								key={row.join()}
								style={{ display: "flex", gap: 6 }}
								flow-children="row"
								noFocusRing={true}
							>
								{row.map((name) => (
									<ComboChip
										key={name}
										name={name}
										on={buttons.includes(name)}
										locked={locked}
										onToggle={async () => {
											if (locked) return;
											const next = nextCombo(buttons, name);
											if (next === buttons) return;
											setButtons(next);
											await setButtonConfig(next);
										}}
									/>
								))}
							</Focusable>
						))}
					</Focusable>
				</PanelSectionRow>
			</PanelSection>
		</>
	);
};

export default definePlugin(() => {
	syncActiveApp();
	const pollId = setInterval(syncActiveApp, 2000);
	let unregister: (() => void) | undefined;
	try {
		const handle = (SteamClient as any).GameSessions?.RegisterForAppLifetimeNotifications?.(
			() => {
				syncActiveApp();
			}
		);
		unregister = handle?.unregister;
	} catch (_e) {}

	return {
		title: <div>DeckVoice</div>,
		content: <DeckVoicePanel />,
		icon: <FaMicrophone />,
		onDismount() {
			clearInterval(pollId);
			try {
				unregister?.();
			} catch (_e) {}
		},
	};
});
