// src/ui/tokens.ts
export const ui = {
    appRoot: "h-screen flex flex-col bg-slate-950 text-slate-200",
    appBody: "flex-1 flex overflow-hidden",
    viewerWrap: "flex-1 flex min-h-0 bg-slate-950 overflow-hidden",
    viewerCenter:
        "flex-1 flex min-h-0 items-center justify-center overflow-hidden",
    sidebar: "w-80 border-l border-slate-800 bg-slate-950 flex flex-col h-full",
    pageDataSidebar:
        "w-80 border-l border-slate-800 bg-slate-900/70 flex flex-col overflow-hidden",
    sidebarScroll: "flex-1 overflow-y-auto",
    sidebarTabs: "px-3 py-2 border-b border-slate-800 bg-slate-900/60",
    tabButtonBase: "flex-1 rounded-md px-2 py-1.5 text-xs font-semibold",
    tabButtonActive: "bg-slate-700 text-slate-100",
    tabButtonInactive: "bg-slate-900/60 text-slate-400 hover:bg-slate-800/70",
    sectionHeader:
        "w-full flex items-center justify-between px-4 py-2 text-xs font-semibold text-slate-300 uppercase tracking-wide bg-slate-900/80 hover:bg-slate-800/80",
    sectionWrap: "border-b border-slate-800",
    sectionBody: "p-4 pt-2 space-y-3",
    label: "text-xs font-semibold text-slate-400 w-28 shrink-0",
    labelSmall: "text-[11px] text-slate-400",
    panel: "flex-1 flex flex-col overflow-hidden p-4 bg-slate-900/70",
    panelHeader: "mb-3 flex items-center justify-between",
    panelTitle: "text-xs font-semibold text-slate-400 uppercase tracking-wide",
    panelToggle:
        "rounded-md border border-slate-700 px-2 py-1 text-[10px] text-slate-300 hover:bg-slate-800",
    panelList:
        "flex-1 overflow-y-auto text-xs text-slate-300 space-y-2 pb-6",
    card: "border border-slate-800 rounded-md p-2 bg-slate-900/70 space-y-2",
    cardHeader: "flex items-center justify-between mb-1",
    cardIndex: "text-[11px] font-semibold text-slate-200",
    select: "min-w-0 flex-1 truncate bg-slate-900 border border-slate-700 text-xs px-2 py-1 rounded-md",
    selectCompact:
        "flex-1 min-w-0 bg-slate-900 border border-slate-700 text-xs px-1 py-1 rounded-md text-slate-100",
    input:
        "w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-100",
    textarea:
        "w-full resize-none bg-slate-900 border border-slate-700 text-xs px-2 py-1 rounded-md text-slate-100",
    textareaSmall:
        "w-full text-xs bg-slate-900 border border-slate-700 rounded-md px-2 py-1 resize-none overflow-hidden leading-4",
    mutedTextXs: "text-xs text-slate-500",
    mutedTextSm: "text-sm text-slate-400",
    mutedTextTiny: "text-[11px] text-slate-500",
    mutedTextMicro: "text-[10px] text-slate-500",
    metaMicro: "text-[10px] text-slate-400",
    textBodySm: "text-slate-300",
    warningTextTiny: "text-[11px] text-amber-300",
    emptyBox:
        "rounded-md border border-dashed border-slate-800 bg-slate-950/50 flex items-center justify-center text-xs text-slate-500",
    progressTrack: "h-1.5 rounded-full bg-slate-800 overflow-hidden",
    progressFill: "h-full bg-sky-500",
    modalOverlay:
        "fixed inset-0 z-50 flex items-center justify-center bg-black/60",
    modalPanel:
        "w-full max-w-sm rounded-lg border border-slate-700 bg-slate-900 p-4 shadow-xl",
    modalTitle: "text-sm font-semibold text-slate-100",
    modalText: "mt-2 text-[11px] text-slate-400",
    modalActions: "mt-4 flex justify-end gap-2",
    errorText: "text-sm text-red-400",
    errorTextXs: "text-xs text-red-400",
    canvasWrap:
        "relative w-full h-full min-h-0 flex items-center justify-center bg-slate-900 overflow-hidden",
    canvasNavBase:
        "w-16 flex items-center justify-center select-none text-3xl font-semibold",
    canvasNavEnabled: "cursor-pointer hover:bg-slate-800/40 text-slate-200",
    canvasNavDisabled: "cursor-not-allowed text-slate-600",
    layerPanel:
        "absolute top-3 left-3 z-10 rounded-md border border-slate-800 bg-slate-950/80 p-2 text-[11px] text-slate-200 shadow-lg backdrop-blur",
    layerTitle: "text-[10px] uppercase tracking-wide text-slate-400",
    layerGroup: "mt-1 flex flex-col gap-1",
    layerOption: "flex items-center gap-2 text-[11px] text-slate-200",
    emptyState: "text-slate-400 text-sm",
    emptyStateSub: "mt-2 text-xs text-slate-500",
    listText: "text-xs text-slate-200",
    sectionDivider: "space-y-1 pt-2 border-t border-slate-800/60",
    topNav: "border-b border-slate-800 bg-slate-950/90 backdrop-blur",
    topNavInner: "flex items-center justify-between px-4 py-2",
    topNavTitle: "text-sm font-semibold tracking-wide text-slate-100",
    topNavSegment:
        "inline-flex rounded-lg border border-slate-800 bg-slate-900/70 p-1",
    topNavSegmentButton:
        "px-3 py-1 text-xs font-medium rounded-md transition",
    topNavSegmentActive: "bg-slate-200 text-slate-900",
    topNavSegmentInactive: "text-slate-300 hover:bg-slate-800/70",
    jobsPanel:
        "w-72 border-r border-slate-800 bg-slate-900/70 flex flex-col",
    jobsHeader: "flex items-center justify-between mb-2",
    jobsTitle: "text-xs font-semibold text-slate-400 uppercase tracking-wide",
    jobsList: "space-y-2 text-xs",
    jobsCard: "border border-slate-800 rounded-md px-2 py-1.5 bg-slate-900/80",
    jobsDetail: "text-[10px] text-slate-400 truncate",
    jobsMessage: "mt-1 text-[10px] text-slate-300 truncate",
    jobsMeta: "text-[10px] text-slate-400",
    jobsType: "font-medium text-slate-100",
    statusBadgeBase: "px-1.5 py-0.5 rounded-full text-[10px] uppercase",
    statusBadgeFinished: "bg-emerald-600 text-white",
    statusBadgeFailed: "bg-red-600 text-white",
    statusBadgeCanceled: "bg-amber-600 text-white",
    statusBadgeRunning: "bg-slate-700 text-slate-100",
    jobsButtonSmall:
        "text-[10px] px-2 py-0.5 rounded-md border border-slate-700 text-slate-200 hover:bg-slate-800",
    jobsButtonTiny:
        "text-[10px] px-1.5 py-0.5 rounded-md border border-slate-700 text-slate-200 hover:bg-slate-800",
    trainingMain: "flex-1 overflow-y-auto p-6 space-y-6",
    trainingTabs:
        "flex flex-wrap gap-2 rounded-lg border border-slate-800 bg-slate-900/60 p-2",
    trainingTab:
        "rounded-md px-3 py-2 text-sm font-semibold transition",
    trainingTabActive: "bg-emerald-500/20 text-emerald-100",
    trainingTabInactive: "text-slate-300 hover:bg-slate-800/60",
    trainingSection: "rounded-lg border border-slate-800 bg-slate-900/60 p-4",
    trainingSectionCompact:
        "rounded-lg border border-slate-800 bg-slate-900/70 p-3",
    trainingSectionHeader: "flex items-center justify-between mb-3",
    trainingSectionTitle: "text-sm font-semibold text-slate-100",
    trainingSectionMeta: "text-xs text-slate-500",
    trainingSubTitle:
        "text-xs font-semibold text-slate-200 uppercase tracking-wide",
    trainingItemTitle: "text-sm font-medium text-slate-100",
    trainingLogStatus: "text-xs text-slate-100",
    trainingLogMetrics: "text-[11px] text-slate-300",
    trainingLogLine:
        "text-[11px] text-slate-200 font-mono whitespace-pre-wrap",
    trainingStatValue: "text-lg font-semibold text-slate-100",
    trainingButton:
        "text-[11px] px-2 py-1 rounded-md border border-slate-700 text-slate-200 hover:bg-slate-800",
    trainingInput:
        "mt-1 w-full rounded-md border border-slate-800 bg-slate-950/60 px-2 py-1 text-xs text-slate-100",
    trainingCard:
        "rounded-md border border-slate-800 bg-slate-950/60 p-3",
    trainingCardCompact:
        "rounded-md border border-slate-800 bg-slate-950/60 p-2",
    trainingTag:
        "text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full border border-slate-700 text-slate-300",
    trainingBody: "text-xs text-slate-300",
    trainingList: "space-y-2 text-xs text-slate-300",
    trainingListTight: "space-y-1 text-[11px] text-slate-300",
    trainingLabelSmall: "text-[11px] text-slate-500",
    trainingLabelTiny: "text-[10px] text-slate-500",
    trainingMetaSmall: "text-[11px] text-slate-400",
    trainingMeta: "text-xs text-slate-400",
    trainingHintSmall: "text-slate-500",
    trainingHelp: "text-xs text-slate-500",
    trainingError: "text-xs text-red-400",
    trainingWarning: "text-xs text-amber-400",
    trainingWarningSmall: "text-[11px] text-amber-300",
    trainingPrimaryButton:
        "mt-3 w-full text-xs px-3 py-2 rounded-md border border-slate-700 text-slate-200 hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed",
    trainingPrimaryButtonTight:
        "mt-1 w-full text-xs px-3 py-2 rounded-md border border-slate-700 text-slate-200 hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed",
    trainingPreset:
        "rounded-full border border-slate-800 px-2 py-0.5 text-[10px] text-slate-400 hover:border-slate-600 hover:text-slate-200",
    trainingLogBadge:
        "rounded-full border border-slate-800 px-2 py-0.5 text-[10px] uppercase tracking-wide text-slate-400",
    trainingLogBox:
        "h-56 rounded-md border border-slate-800 bg-slate-950/60 overflow-auto",
    button: {
        actionIndigo:
            "flex-1 px-2 py-1.5 rounded-md text-xs font-medium bg-indigo-500 hover:bg-indigo-400 text-black disabled:opacity-60",
        actionAmber:
            "flex-1 px-2 py-1.5 rounded-md text-xs font-medium bg-amber-500 hover:bg-amber-400 text-black",
        actionEmerald:
            "flex-1 px-2 py-1.5 rounded-md text-xs font-medium bg-emerald-600 hover:bg-emerald-500 text-white",
        actionSlate:
            "flex-1 px-2 py-1.5 rounded-md text-xs font-medium bg-slate-700 hover:bg-slate-600 text-slate-100",
        actionRed:
            "flex-1 px-2 py-1.5 rounded-md text-xs font-medium bg-red-700 hover:bg-red-600 text-white",
        actionDangerSmall:
            "px-2 py-1 rounded-md text-xs font-semibold bg-red-700 hover:bg-red-600 text-white",
        actionSlateSmall:
            "flex-1 px-2 py-1.5 rounded-md text-[11px] font-medium bg-slate-700 hover:bg-slate-600 text-slate-100",
        jobsStop:
            "text-[10px] px-1.5 py-0.5 rounded-md border border-amber-500 text-amber-200 hover:bg-amber-500/20",
        navBase: "px-2 py-1 rounded-md text-xs border border-slate-700",
        navEnabled: "bg-slate-800 hover:bg-slate-700",
        navDisabled: "opacity-40 cursor-not-allowed bg-slate-900",
        insertBase:
            "rounded-md border border-slate-700 px-2 py-1 text-[11px]",
        insertEnabled: "bg-slate-800 text-slate-200 hover:bg-slate-700",
        insertDisabled:
            "opacity-40 cursor-not-allowed bg-slate-900 text-slate-500",
        cancel:
            "rounded-md border border-slate-700 px-2 py-1 text-[11px] text-slate-200 hover:bg-slate-800",
        deleteBase:
            "rounded-md border border-red-900 px-2 py-1 text-[11px]",
        deleteEnabled: "bg-red-900/70 text-red-100 hover:bg-red-900",
        deleteDisabled:
            "opacity-40 cursor-not-allowed bg-slate-900 text-slate-500 border-slate-700",
        icon:
            "w-7 h-7 flex items-center justify-center rounded-md text-xs border border-slate-700 bg-slate-800 hover:bg-slate-700",
        iconDisabled: "opacity-40 cursor-not-allowed bg-slate-900",
        ghostSmall:
            "rounded-md border border-slate-700 px-2 py-1 text-[11px] text-slate-200 hover:bg-slate-800 disabled:opacity-60",
        modalCancel:
            "rounded-md border border-slate-700 px-3 py-1 text-xs text-slate-200 hover:bg-slate-800",
        modalPrimary:
            "rounded-md bg-emerald-500 px-3 py-1 text-xs font-semibold text-emerald-950 hover:bg-emerald-400 disabled:opacity-60",
        modalWarning:
            "rounded-md bg-amber-400 px-3 py-1 text-xs font-semibold text-amber-950 hover:bg-amber-300 disabled:opacity-60",
        modalDanger:
            "rounded-md bg-red-600 px-3 py-1 text-xs font-semibold text-white hover:bg-red-500",
        miniMoveEnabled:
            "px-1.5 py-0.5 rounded text-[10px] border border-slate-600 text-slate-200 hover:bg-slate-700",
        miniMoveDisabled:
            "px-1.5 py-0.5 rounded text-[10px] border border-slate-800 text-slate-600 cursor-not-allowed",
        miniAmber:
            "px-2 py-0.5 rounded-md text-[10px] font-semibold bg-amber-500 hover:bg-amber-400 text-black",
        miniEmerald:
            "px-2 py-0.5 rounded-md text-[10px] font-semibold bg-emerald-600 hover:bg-emerald-500 text-white",
        miniRed:
            "px-2 py-0.5 rounded-md text-[10px] font-semibold bg-red-700 hover:bg-red-600 text-white",
        miniIcon:
            "w-4 h-4 flex items-center justify-center border border-slate-700 rounded text-[9px] text-slate-300 hover:bg-slate-800 disabled:opacity-40",
        miniIconSmall:
            "w-4 h-4 flex items-center justify-center border border-slate-700 rounded text-[10px] text-slate-300 hover:bg-slate-800",
    },
};
