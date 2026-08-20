import {
	definePlugin,
	PanelSection,
	PanelSectionRow,
	ToggleField,
	DropdownItem,
	DropdownOption,
	Focusable,
	gamepadDialogClasses,
} from "decky-frontend-lib";

import { callable, toaster } from "@decky/api";

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

class DeckVoiceLogic {
	enabled = false;
	prevRecordingStartCount = 0;
	toast: { dismiss: () => void } | null = null;
	lastPreview = "";
	pollInFlight = false;
	hideTimer: ReturnType<typeof setTimeout> | null = null;

	show(body: string) {
		this.hide();
		try {
			this.toast = toaster.toast({
				title: "DeckVoice",
				body,
				duration: 60000,
				critical: false,
				playSound: false,
			});
		} catch (_e) {}
	}

	hide() {
		this.clearHideTimer();
		try {
			this.toast?.dismiss();
		} catch (_e) {}
		this.toast = null;
	}

	clearHideTimer() {
		if (this.hideTimer) {
			clearTimeout(this.hideTimer);
			this.hideTimer = null;
		}
	}

	poll = async () => {
		if (!this.enabled || this.pollInFlight) return;
		this.pollInFlight = true;
		try {
			const status = await getStatus();
			if (!status?.success) return;

			if (status.recording_start_count > this.prevRecordingStartCount) {
				this.prevRecordingStartCount = status.recording_start_count;
				this.lastPreview = "";
				this.show("Listening…");
			}

			const busy = !!(status.recording || status.status === "transcribing");
			const preview = (status.preview_text || "").trim();
			if (preview && preview !== this.lastPreview) {
				this.lastPreview = preview;
				this.show(preview);
			}

			if (busy) {
				this.clearHideTimer();
			} else if (this.toast && !this.hideTimer) {
				this.hideTimer = setTimeout(() => {
					this.hideTimer = null;
					this.hide();
					this.lastPreview = "";
				}, 1500);
			}
		} catch (_e) {
		} finally {
			this.pollInFlight = false;
		}
	};
}

const logic = new DeckVoiceLogic();

function nextCombo(current: string[], name: string): string[] {
	const next = current.includes(name)
		? current.filter((b) => b !== name)
		: [...current, name];
	if (next.length < 1 || next.length > 5) return current;
	return BUTTON_NAMES.filter((b) => next.includes(b));
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

	const applyStatus = (status: RpcResponse) => {
		setStatusLabel(friendlyStatus(status));
		setPreview((status.preview_text || "").trim());
		setFailed(!!status.enabled && (!!status.model_load_error || status.status === "error"));
		setEnabled(!!status.enabled);
		logic.enabled = !!status.enabled;
	};

	const refresh = async () => {
		const [cfg, status, presetResp, langResp] = await Promise.all([
			getButtonConfig(),
			getStatus(),
			getPresets(),
			getWhisperLanguages(),
		]);
		if (cfg?.success && cfg.config) {
			setEnabled(!!cfg.config.enabled);
			logic.enabled = !!cfg.config.enabled;
			setButtons(cfg.config.buttons || ["L1", "R1"]);
			setGame(cfg.config.game || "wow");
			setWhisperModel(cfg.config.whisperModel || "base");
			setWhisperLanguage(cfg.config.whisperLanguage || "auto");
		}
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
				if (status?.success) applyStatus(status);
			} catch (_e) {}
		}, 1000);
		return () => clearInterval(id);
	}, []);

	const onToggleEnabled = async (value: boolean) => {
		setBusy(true);
		setFailed(false);
		setEnabled(value);
		logic.enabled = value;
		setStatusLabel(value ? "Starting…" : "Off");
		const res = await setEnabledRpc(value);
		if (!res?.success) {
			setFailed(true);
			setStatusLabel("Failed to start");
			setEnabled(false);
			logic.enabled = false;
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
					<ToggleField
						label="Enable"
						description={busy ? "Please wait…" : "GPU Whisper. Off frees VRAM."}
						checked={enabled}
						disabled={busy}
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
						label="Game"
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
	getStatus().then((status) => {
		if (!status?.success) return;
		logic.prevRecordingStartCount = status.recording_start_count || 0;
		logic.enabled = !!status.enabled;
	});
	const interval = setInterval(() => {
		logic.poll();
	}, 50);

	return {
		title: <div>DeckVoice</div>,
		content: <DeckVoicePanel />,
		icon: <FaMicrophone />,
		onDismount() {
			clearInterval(interval);
			logic.hide();
		},
	};
});
