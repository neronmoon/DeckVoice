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
	tiny: "Tiny (fastest)",
	base: "Base",
	"small-q5_1": "Small",
	"medium-q5_0": "Medium",
};

function friendlyStatus(status: RpcResponse | null): string {
	if (!status?.success) return "Unavailable";
	if (!status.enabled) return "Off";
	if (status.model_loading) return "Starting…";
	if (status.status === "error" || status.model_load_error) return "Failed to start";
	if (status.recording) return "Listening";
	if (status.status === "transcribing") return "Sending…";
	if (status.server_ready || status.status === "listening") return "Ready";
	if (status.status === "loading") return "Starting…";
	return "Off";
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

const ComboChip: VFC<{ name: string; on: boolean; onToggle: () => void }> = ({
	name,
	on,
	onToggle,
}) => (
	<Focusable
		onActivate={onToggle}
		onClick={onToggle}
		focusClassName={CHIP_FOCUS}
		style={{
			flex: 1,
			textAlign: "center",
			padding: "8px 0",
			borderRadius: 3,
			background: on ? "rgba(255,255,255,0.16)" : "rgba(255,255,255,0.04)",
			fontSize: 14,
			fontWeight: on ? 600 : 400,
			opacity: on ? 1 : 0.55,
		}}
	>
		{name}
	</Focusable>
);

const StatusLine: VFC<{ label: string; preview: string; failed: boolean }> = ({
	label,
	preview,
	failed,
}) => (
	<div style={{ padding: "4px 0 8px" }}>
		<div
			style={{
				fontSize: "14px",
				opacity: failed ? 1 : 0.85,
				color: failed ? "#ff8a8a" : undefined,
			}}
		>
			{label}
		</div>
		{preview ? (
			<div
				style={{
					marginTop: "6px",
					fontSize: "15px",
					lineHeight: 1.35,
					opacity: 0.95,
				}}
			>
				“{preview}”
			</div>
		) : null}
		{failed ? (
			<div style={{ marginTop: "4px", fontSize: "12px", opacity: 0.65 }}>
				See /tmp/deckvoice.log
			</div>
		) : null}
	</div>
);

const DeckVoicePanel: VFC = () => {
	const [enabled, setEnabled] = useState(false);
	const [busy, setBusy] = useState(false);
	const [statusLabel, setStatusLabel] = useState("Off");
	const [preview, setPreview] = useState("");
	const [failed, setFailed] = useState(false);
	const [buttons, setButtons] = useState<string[]>(["L1", "R1"]);
	const [game, setGame] = useState("wow");
	const [presets, setPresets] = useState<Record<string, any>>({});
	const [whisperModel, setWhisperModel] = useState("base");
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
		setWhisperModel(cfg.whisperModel || "base");
		setWhisperLanguage(cfg.whisperLanguage || "auto");
		setAppId(cfg.appId || "");
		setAppName(cfg.appName || "");
	};

	const applyStatus = (status: RpcResponse) => {
		setStatusLabel(friendlyStatus(status));
		setPreview((status.preview_text || "").trim());
		setFailed(!!status.enabled && (!!status.model_load_error || status.status === "error"));
		if (status.profileEnabled !== undefined) {
			setEnabled(!!status.profileEnabled);
		} else {
			setEnabled(!!status.enabled);
		}
		const nextAppId = status.appId || "";
		const nextAppName = status.appName || "";
		if (status.appId !== undefined) setAppId(nextAppId);
		if (status.appName !== undefined) setAppName(nextAppName);
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

	const onToggleEnabled = async (value: boolean) => {
		if (!inGame) return;
		setBusy(true);
		setFailed(false);
		setEnabled(value);
		setStatusLabel(value ? "Starting…" : "Off");
		const res = await setEnabledRpc(value);
		if (!res?.success) {
			setFailed(true);
			setStatusLabel("Failed to start");
			setEnabled(false);
		}
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
			<PanelSection title="DeckVoice">
				<PanelSectionRow>
					<div style={{ fontSize: "13px", opacity: 0.8, marginBottom: "6px" }}>
						{inGame ? appName || `App ${appId}` : "No game"}
					</div>
				</PanelSectionRow>
				<PanelSectionRow>
					<ToggleField
						label="Enable"
						description={
							busy
								? "Please wait…"
								: inGame
									? "GPU Whisper. Off frees VRAM."
									: "Launch a game to enable"
						}
						checked={enabled}
						disabled={busy || !inGame}
						onChange={onToggleEnabled}
					/>
				</PanelSectionRow>
				<PanelSectionRow>
					<StatusLine label={statusLabel} preview={preview} failed={failed} />
				</PanelSectionRow>
			</PanelSection>

			<PanelSection title="Recognition">
				<PanelSectionRow>
					<DropdownItem
						label="Model"
						rgOptions={modelOptions}
						selectedOption={whisperModel}
						disabled={busy}
						onChange={async (option: DropdownOption) => {
							const value = String(option.data);
							setWhisperModel(value);
							await setWhisperModelRpc(value);
							await refresh();
						}}
					/>
				</PanelSectionRow>
				<PanelSectionRow>
					<DropdownItem
						label="Language"
						rgOptions={languageOptions}
						selectedOption={whisperLanguage}
						disabled={busy}
						onChange={async (option: DropdownOption) => {
							const value = String(option.data);
							setWhisperLanguage(value);
							await setWhisperLanguageRpc(value);
							await refresh();
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
						disabled={busy}
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
				<style>{`.dv-chip-focus{background:#1a9fff!important;color:#fff!important;opacity:1!important;font-weight:600}`}</style>
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
										onToggle={async () => {
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
