(function (deckyFrontendLib, React) {
    'use strict';

    function _interopDefaultLegacy (e) { return e && typeof e === 'object' && 'default' in e ? e : { 'default': e }; }

    var React__default = /*#__PURE__*/_interopDefaultLegacy(React);

    var _manifest = {"name":"DeckVoice","version":"0.1.0","author":"DeckVoice","flags":["_root"],"api_version":1,"publish":{"tags":["voice","dictation","speech-to-text","input","chat","gaming","accessibility"],"description":"GPU push-to-talk voice input for Steam Deck with live preview and game profiles.","image":""}};

    const manifest = _manifest;
    const API_VERSION = 2;
    if (!manifest?.name) {
        throw new Error('[@decky/api]: Failed to find plugin manifest.');
    }
    const internalAPIConnection = window.__DECKY_SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED_deckyLoaderAPIInit;
    if (!internalAPIConnection) {
        throw new Error('[@decky/api]: Failed to connect to the loader as as the loader API was not initialized. This is likely a bug in Decky Loader.');
    }
    let api;
    try {
        api = internalAPIConnection.connect(API_VERSION, manifest.name);
    }
    catch {
        api = internalAPIConnection.connect(1, manifest.name);
        console.warn(`[@decky/api] Requested API version ${API_VERSION} but the running loader only supports version 1. Some features may not work.`);
    }
    if (api._version != API_VERSION) {
        console.warn(`[@decky/api] Requested API version ${API_VERSION} but the running loader only supports version ${api._version}. Some features may not work.`);
    }
    api.call;
    const callable = api.callable;
    api.addEventListener;
    api.removeEventListener;
    api.routerHook;
    const toaster = api.toaster;
    api.openFilePicker;
    api.executeInTab;
    api.injectCssIntoTab;
    api.removeCssFromTab;
    api.fetchNoCors;
    api.getExternalResourceURL;
    api.useQuickAccessVisible;

    var DefaultContext = {
      color: undefined,
      size: undefined,
      className: undefined,
      style: undefined,
      attr: undefined
    };
    var IconContext = React__default["default"].createContext && React__default["default"].createContext(DefaultContext);

    var __assign = window && window.__assign || function () {
      __assign = Object.assign || function (t) {
        for (var s, i = 1, n = arguments.length; i < n; i++) {
          s = arguments[i];
          for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p)) t[p] = s[p];
        }
        return t;
      };
      return __assign.apply(this, arguments);
    };
    var __rest = window && window.__rest || function (s, e) {
      var t = {};
      for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p) && e.indexOf(p) < 0) t[p] = s[p];
      if (s != null && typeof Object.getOwnPropertySymbols === "function") for (var i = 0, p = Object.getOwnPropertySymbols(s); i < p.length; i++) {
        if (e.indexOf(p[i]) < 0 && Object.prototype.propertyIsEnumerable.call(s, p[i])) t[p[i]] = s[p[i]];
      }
      return t;
    };
    function Tree2Element(tree) {
      return tree && tree.map(function (node, i) {
        return React__default["default"].createElement(node.tag, __assign({
          key: i
        }, node.attr), Tree2Element(node.child));
      });
    }
    function GenIcon(data) {
      // eslint-disable-next-line react/display-name
      return function (props) {
        return React__default["default"].createElement(IconBase, __assign({
          attr: __assign({}, data.attr)
        }, props), Tree2Element(data.child));
      };
    }
    function IconBase(props) {
      var elem = function (conf) {
        var attr = props.attr,
          size = props.size,
          title = props.title,
          svgProps = __rest(props, ["attr", "size", "title"]);
        var computedSize = size || conf.size || "1em";
        var className;
        if (conf.className) className = conf.className;
        if (props.className) className = (className ? className + " " : "") + props.className;
        return React__default["default"].createElement("svg", __assign({
          stroke: "currentColor",
          fill: "currentColor",
          strokeWidth: "0"
        }, conf.attr, attr, svgProps, {
          className: className,
          style: __assign(__assign({
            color: props.color || conf.color
          }, conf.style), props.style),
          height: computedSize,
          width: computedSize,
          xmlns: "http://www.w3.org/2000/svg"
        }), title && React__default["default"].createElement("title", null, title), props.children);
      };
      return IconContext !== undefined ? React__default["default"].createElement(IconContext.Consumer, null, function (conf) {
        return elem(conf);
      }) : elem(DefaultContext);
    }

    // THIS FILE IS AUTO GENERATED
    function FaMicrophone (props) {
      return GenIcon({"tag":"svg","attr":{"viewBox":"0 0 352 512"},"child":[{"tag":"path","attr":{"d":"M176 352c53.02 0 96-42.98 96-96V96c0-53.02-42.98-96-96-96S80 42.98 80 96v160c0 53.02 42.98 96 96 96zm160-160h-16c-8.84 0-16 7.16-16 16v48c0 74.8-64.49 134.82-140.79 127.38C96.71 376.89 48 317.11 48 250.3V208c0-8.84-7.16-16-16-16H16c-8.84 0-16 7.16-16 16v40.16c0 89.64 63.97 169.55 152 181.69V464H96c-8.84 0-16 7.16-16 16v16c0 8.84 7.16 16 16 16h160c8.84 0 16-7.16 16-16v-16c0-8.84-7.16-16-16-16h-56v-33.77C285.71 418.47 352 344.9 352 256v-48c0-8.84-7.16-16-16-16z"}}]})(props);
    }

    const getStatus = callable("get_status");
    const getButtonConfig = callable("get_button_config");
    const getPresets = callable("get_presets");
    const getWhisperLanguages = callable("get_whisper_languages");
    const setEnabledRpc = callable("set_enabled");
    const setActivePresetRpc = callable("set_active_preset");
    const setWhisperModelRpc = callable("set_whisper_model");
    const setWhisperLanguageRpc = callable("set_whisper_language");
    const setButtonConfig = callable("set_button_config");
    const BUTTON_NAMES = ["L1", "R1", "L2", "R2", "L4", "R4", "L5", "R5", "A", "B", "X", "Y"];
    const BUTTON_ROWS = [
        ["L1", "R1", "L2", "R2"],
        ["L4", "R4", "L5", "R5"],
        ["A", "B", "X", "Y"],
    ];
    const MODEL_LABELS = {
        tiny: "Tiny (fastest)",
        base: "Base",
        "small-q5_1": "Small",
        "medium-q5_0": "Medium",
    };
    function friendlyStatus(status) {
        if (!status?.success)
            return "Unavailable";
        if (!status.enabled)
            return "Off";
        if (status.model_loading)
            return "Starting…";
        if (status.status === "error" || status.model_load_error)
            return "Failed to start";
        if (status.recording)
            return "Listening";
        if (status.server_ready || status.status === "listening")
            return "Ready";
        if (status.status === "loading")
            return "Starting…";
        return "Off";
    }
    class DeckVoiceLogic {
        constructor() {
            this.enabled = false;
            this.prevRecordingStartCount = 0;
            this.lastToastId = -1;
            this.lastPreview = "";
            this.notify = async (title, body, duration = 4000) => {
                const id = window.NotificationStore
                    ? window.NotificationStore.m_nNextTestNotificationID++
                    : 0;
                const toastData = {
                    nNotificationID: id,
                    bNewIndicator: false,
                    rtCreated: Date.now(),
                    eType: 43,
                    eSource: 1,
                    nToastDurationMS: duration,
                    data: { title, body, duration, critical: false },
                    decky: true,
                };
                const info = {
                    showToast: true,
                    sound: 6,
                    playSound: false,
                    eFeature: 0,
                    toastDurationMS: duration,
                    bCritical: false,
                    fnTray: (_t, tray) => {
                        tray.unshift({ eType: 31, notifications: [toastData] });
                    },
                };
                try {
                    window.NotificationStore.ProcessNotification(info, toastData, 0);
                }
                catch (_e) {
                    toaster.toast({ title, body, duration, critical: false });
                }
                return id;
            };
            this.dismissNotification = (id) => {
                try {
                    const toastData = {
                        nNotificationID: id,
                        bNewIndicator: false,
                        rtCreated: Date.now(),
                        eType: 43,
                        eSource: 1,
                        nToastDurationMS: 1,
                        data: { title: "", body: "", duration: 1, critical: false },
                        decky: true,
                    };
                    const info = {
                        showToast: true,
                        sound: 6,
                        playSound: false,
                        eFeature: 0,
                        toastDurationMS: 1,
                        bCritical: false,
                        fnTray: (_t, tray) => {
                            tray.unshift({ eType: 31, notifications: [toastData] });
                        },
                    };
                    window.NotificationStore.ProcessNotification(info, toastData, 0);
                }
                catch (_e) { }
            };
            this.poll = async () => {
                if (!this.enabled)
                    return;
                try {
                    const status = await getStatus();
                    if (!status?.success)
                        return;
                    if (status.recording_start_count > this.prevRecordingStartCount) {
                        this.prevRecordingStartCount = status.recording_start_count;
                        this.lastPreview = "";
                        if (this.lastToastId >= 0)
                            this.dismissNotification(this.lastToastId);
                        this.lastToastId = await this.notify("DeckVoice", "Listening…", 60000);
                    }
                    if (status.recording) {
                        const preview = (status.preview_text || "").trim();
                        if (preview && preview !== this.lastPreview) {
                            this.lastPreview = preview;
                            if (this.lastToastId >= 0)
                                this.dismissNotification(this.lastToastId);
                            this.lastToastId = await this.notify("DeckVoice", preview, 60000);
                        }
                    }
                    else if (this.lastToastId >= 0 && !status.recording) {
                        this.dismissNotification(this.lastToastId);
                        this.lastToastId = -1;
                        this.lastPreview = "";
                    }
                }
                catch (_e) { }
            };
        }
    }
    const logic = new DeckVoiceLogic();
    function nextCombo(current, name) {
        const next = current.includes(name)
            ? current.filter((b) => b !== name)
            : [...current, name];
        if (next.length < 1 || next.length > 5)
            return current;
        return BUTTON_NAMES.filter((b) => next.includes(b));
    }
    const ComboChip = ({ name, on, onToggle, }) => (React__default["default"].createElement(deckyFrontendLib.Focusable, { onActivate: onToggle, onClick: onToggle, style: {
            flex: 1,
            textAlign: "center",
            padding: "8px 0",
            borderRadius: 3,
            background: on ? "rgba(255,255,255,0.16)" : "rgba(255,255,255,0.04)",
            fontSize: 14,
            fontWeight: on ? 600 : 400,
            opacity: on ? 1 : 0.55,
        } }, name));
    const StatusLine = ({ label, preview, failed, }) => (React__default["default"].createElement("div", { style: { padding: "4px 0 8px" } },
        React__default["default"].createElement("div", { style: {
                fontSize: "14px",
                opacity: failed ? 1 : 0.85,
                color: failed ? "#ff8a8a" : undefined,
            } }, label),
        preview ? (React__default["default"].createElement("div", { style: {
                marginTop: "6px",
                fontSize: "15px",
                lineHeight: 1.35,
                opacity: 0.95,
            } },
            "\u201C",
            preview,
            "\u201D")) : null,
        failed ? (React__default["default"].createElement("div", { style: { marginTop: "4px", fontSize: "12px", opacity: 0.65 } }, "See /tmp/deckvoice.log")) : null));
    const DeckVoicePanel = () => {
        const [enabled, setEnabled] = React.useState(false);
        const [busy, setBusy] = React.useState(false);
        const [statusLabel, setStatusLabel] = React.useState("Off");
        const [preview, setPreview] = React.useState("");
        const [failed, setFailed] = React.useState(false);
        const [buttons, setButtons] = React.useState(["L1", "R1"]);
        const [game, setGame] = React.useState("wow");
        const [presets, setPresets] = React.useState({});
        const [whisperModel, setWhisperModel] = React.useState("base");
        const [whisperLanguage, setWhisperLanguage] = React.useState("auto");
        const [modelOptions, setModelOptions] = React.useState([]);
        const [languageOptions, setLanguageOptions] = React.useState([]);
        const applyStatus = (status) => {
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
            if (status?.success)
                applyStatus(status);
            if (presetResp?.success)
                setPresets(presetResp.presets || {});
            if (langResp?.success) {
                setModelOptions((langResp.models || []).map((m) => ({
                    data: m,
                    label: MODEL_LABELS[m] || m,
                })));
                setLanguageOptions((langResp.languages || []).map((code) => ({
                    data: code,
                    label: code === "auto" ? "Auto-detect" : langResp.names?.[code] || code,
                })));
            }
        };
        React.useEffect(() => {
            refresh();
            const id = setInterval(async () => {
                try {
                    const status = await getStatus();
                    if (status?.success)
                        applyStatus(status);
                }
                catch (_e) { }
            }, 1000);
            return () => clearInterval(id);
        }, []);
        const onToggleEnabled = async (value) => {
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
            if (!preset?.channels || game !== "wow")
                return null;
            const parts = Object.entries(preset.channels)
                .filter(([name]) => name !== "type")
                .map(([name, prefix]) => `${name} → ${String(prefix).trim() || "raw"}`);
            return (React__default["default"].createElement(deckyFrontendLib.PanelSectionRow, null,
                React__default["default"].createElement("div", { style: { fontSize: "12px", opacity: 0.7, lineHeight: 1.45 } },
                    "Say a channel first: ",
                    parts.slice(0, 4).join(", "),
                    ", \u2026")));
        };
        const presetOptions = Object.entries(presets).map(([key, value]) => ({
            data: key,
            label: value?.name || key,
        }));
        return (React__default["default"].createElement(React__default["default"].Fragment, null,
            React__default["default"].createElement(deckyFrontendLib.PanelSection, { title: "DeckVoice" },
                React__default["default"].createElement(deckyFrontendLib.PanelSectionRow, null,
                    React__default["default"].createElement(deckyFrontendLib.ToggleField, { label: "Enable", description: busy ? "Please wait…" : "GPU Whisper. Off frees VRAM.", checked: enabled, disabled: busy, onChange: onToggleEnabled })),
                React__default["default"].createElement(deckyFrontendLib.PanelSectionRow, null,
                    React__default["default"].createElement(StatusLine, { label: statusLabel, preview: preview, failed: failed }))),
            React__default["default"].createElement(deckyFrontendLib.PanelSection, { title: "Recognition" },
                React__default["default"].createElement(deckyFrontendLib.PanelSectionRow, null,
                    React__default["default"].createElement(deckyFrontendLib.DropdownItem, { label: "Model", rgOptions: modelOptions, selectedOption: whisperModel, disabled: busy, onChange: async (option) => {
                            const value = String(option.data);
                            setWhisperModel(value);
                            await setWhisperModelRpc(value);
                            await refresh();
                        } })),
                React__default["default"].createElement(deckyFrontendLib.PanelSectionRow, null,
                    React__default["default"].createElement(deckyFrontendLib.DropdownItem, { label: "Language", rgOptions: languageOptions, selectedOption: whisperLanguage, disabled: busy, onChange: async (option) => {
                            const value = String(option.data);
                            setWhisperLanguage(value);
                            await setWhisperLanguageRpc(value);
                            await refresh();
                        } }))),
            React__default["default"].createElement(deckyFrontendLib.PanelSection, { title: "Profile" },
                React__default["default"].createElement(deckyFrontendLib.PanelSectionRow, null,
                    React__default["default"].createElement(deckyFrontendLib.DropdownItem, { label: "Game", rgOptions: presetOptions, selectedOption: game, disabled: busy, onChange: async (option) => {
                            const value = String(option.data);
                            setGame(value);
                            await setActivePresetRpc(value);
                            await refresh();
                        } })),
                channelSummary()),
            React__default["default"].createElement(deckyFrontendLib.PanelSection, { title: "Trigger combo" },
                React__default["default"].createElement(deckyFrontendLib.PanelSectionRow, null,
                    React__default["default"].createElement("div", { style: { fontSize: "12px", opacity: 0.7, marginBottom: "8px" } },
                        "Hold ",
                        buttons.join(" + "))),
                React__default["default"].createElement(deckyFrontendLib.PanelSectionRow, null,
                    React__default["default"].createElement(deckyFrontendLib.Focusable, { style: { display: "flex", flexDirection: "column", gap: 6 } }, BUTTON_ROWS.map((row) => (React__default["default"].createElement(deckyFrontendLib.Focusable, { key: row.join(), style: { display: "flex", gap: 6 }, "flow-children": "row" }, row.map((name) => (React__default["default"].createElement(ComboChip, { key: name, name: name, on: buttons.includes(name), onToggle: async () => {
                            const next = nextCombo(buttons, name);
                            if (next === buttons)
                                return;
                            setButtons(next);
                            await setButtonConfig(next);
                        } })))))))))));
    };
    var index = deckyFrontendLib.definePlugin(() => {
        const interval = setInterval(() => {
            logic.poll();
        }, 800);
        return {
            title: React__default["default"].createElement("div", null, "DeckVoice"),
            content: React__default["default"].createElement(DeckVoicePanel, null),
            icon: React__default["default"].createElement(FaMicrophone, null),
            onDismount() {
                clearInterval(interval);
            },
        };
    });

    return index;

})(DFL, SP_REACT);
