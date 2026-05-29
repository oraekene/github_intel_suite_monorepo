#!/usr/bin/env python3
"""
GitHub Intelligence Suite — GUI  v3
Premium redesign: sidebar nav, card layout, progressive disclosure.
Requires: Python 3.10+  (tkinter built-in)
"""
from __future__ import annotations
import os, sys, subprocess, threading, queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_manager import ConfigManager, PLATFORM_SOURCES, GH_SOURCES_ALL, cfg as _cfg

HERE         = Path(__file__).resolve().parent
EXTRACTOR    = HERE / "github_extractor_v2.py"
PLATFORM     = HERE / "platform_extractor.py"
VIEWER       = HERE / "github_viewer_v2.py"
PIA_DIR      = HERE / "pia"
PIA_PIPELINE = PIA_DIR / "scheduler" / "run_pipeline.py"
PIA_CONFIG   = PIA_DIR / "config.yaml"
PYTHON       = sys.executable

# ── Palette ───────────────────────────────────────────────────────────────────
C_BG0  = "#08080e"   # window bg
C_BG1  = "#0e0e18"   # sidebar
C_BG2  = "#12121c"   # page bg
C_BG3  = "#191926"   # card surface
C_BG4  = "#20202e"   # input / hover
C_BG5  = "#282838"   # strong hover
C_SEP  = "#1c1c2a"   # subtle separator
C_SEP2 = "#2a2a3e"   # visible border

C_T0   = "#eeeef6"   # primary text
C_T1   = "#9595ae"   # secondary
C_T2   = "#4e4e68"   # muted

C_ACC  = "#6366f1"   # indigo accent
C_ACC2 = "#4f46e5"   # pressed
C_ACCL = "#818cf8"   # light/active
C_OK   = "#22c55e"
C_WARN = "#f59e0b"
C_ERR  = "#ef4444"
C_CYAN = "#22d3ee"
C_CON  = "#050510"   # console bg

if sys.platform == "win32":
    FUI, FMONO = "Segoe UI", "Consolas"
elif sys.platform == "darwin":
    FUI, FMONO = "SF Pro Display", "Menlo"
else:
    FUI, FMONO = "Ubuntu", "Ubuntu Mono"

def F(sz=10, w="normal"): return (FUI,  sz, w)
def FM(sz=10):             return (FMONO, sz)


# ── Widget components ─────────────────────────────────────────────────────────

class NavItem(tk.Frame):
    """Sidebar navigation entry with active + hover states."""
    def __init__(self, parent, icon: str, label: str, command, **kw):
        super().__init__(parent, bg=C_BG1, cursor="hand2", **kw)
        self._active = False; self._cmd = command

        self._bar = tk.Frame(self, bg=C_BG1, width=3)
        self._bar.pack(side="left", fill="y")

        body = tk.Frame(self, bg=C_BG1)
        body.pack(side="left", fill="both", expand=True, padx=(10,14), pady=11)

        self._ico = tk.Label(body, text=icon,  bg=C_BG1, fg=C_T1, font=F(13))
        self._ico.pack(side="left")
        self._lbl = tk.Label(body, text=label, bg=C_BG1, fg=C_T1, font=F(9))
        self._lbl.pack(side="left", padx=(10, 0))

        self._widgets = [self, body, self._ico, self._lbl, self._bar]
        for w in self._widgets:
            w.bind("<Button-1>", lambda e: command())
            w.bind("<Enter>",    lambda e: self._hover(e))
            w.bind("<Leave>",    lambda e: self._leave(e))

    def _all_bg(self, bg):
        for w in self._widgets: w.config(bg=bg)

    def _hover(self, _):
        if not self._active: self._all_bg(C_BG4)

    def _leave(self, _):
        if not self._active: self._all_bg(C_BG1)

    def set_active(self, v: bool):
        self._active = v
        if v:
            self._bar.config(bg=C_ACC); self._all_bg(C_BG3)
            self._ico.config(fg=C_ACCL); self._lbl.config(fg=C_T0, font=F(9,"bold"))
        else:
            self._bar.config(bg=C_BG1); self._all_bg(C_BG1)
            self._ico.config(fg=C_T1);  self._lbl.config(fg=C_T1, font=F(9))


class PillToggle(tk.Label):
    """Toggleable pill button bound to a BooleanVar."""
    def __init__(self, parent, text: str, var: tk.BooleanVar, **kw):
        super().__init__(parent, text=text, cursor="hand2",
                         font=F(9), padx=11, pady=5, relief="flat", bd=0, **kw)
        self._var = var; self._ref()
        self.bind("<Button-1>", lambda _: var.set(not var.get()))
        var.trace_add("write", lambda *_: self._ref())

    def _ref(self):
        self.config(bg=C_ACC, fg="white") if self._var.get() else \
            self.config(bg=C_BG4, fg=C_T1)


class Segment(tk.Frame):
    """Segmented control bound to a StringVar."""
    def __init__(self, parent, opts: list[str], var: tk.StringVar, **kw):
        super().__init__(parent, bg=C_BG4,
                         highlightthickness=1, highlightbackground=C_SEP2, **kw)
        self._var = var; self._btns: dict[str,tk.Label] = {}
        for opt in opts:
            lbl = tk.Label(self, text=opt, cursor="hand2",
                           font=F(9), padx=14, pady=6, relief="flat", bd=0)
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda e, o=opt: var.set(o))
            self._btns[opt] = lbl
        var.trace_add("write", lambda *_: self._ref())
        self._ref()

    def _ref(self):
        v = self._var.get()
        for opt, lbl in self._btns.items():
            lbl.config(bg=C_ACC, fg="white") if opt == v else \
                lbl.config(bg=C_BG4, fg=C_T1)


class Expander(tk.Frame):
    """Disclosure section: header click expands/collapses body."""
    def __init__(self, parent, title: str, open_: bool = False, **kw):
        super().__init__(parent, bg=C_BG2, **kw)
        self._open = open_

        hdr = tk.Frame(self, bg=C_BG3, cursor="hand2",
                       highlightthickness=1, highlightbackground=C_SEP)
        hdr.pack(fill="x")
        self._arrow = tk.Label(hdr, text="▾" if open_ else "▸",
                               bg=C_BG3, fg=C_T2, font=F(8))
        self._arrow.pack(side="left", padx=(14,6), pady=9)
        tk.Label(hdr, text=title, bg=C_BG3, fg=C_T1,
                 font=F(9,"bold")).pack(side="left")

        self.body = tk.Frame(self, bg=C_BG2, padx=20, pady=12)
        if open_: self.body.pack(fill="x")

        for w in [hdr] + list(hdr.winfo_children()):
            w.bind("<Button-1>", self._toggle)
        hdr.bind("<Enter>", lambda _: hdr.config(bg=C_BG5))
        hdr.bind("<Leave>", lambda _: hdr.config(bg=C_BG3))

    def _toggle(self, _=None):
        self._open = not self._open
        if self._open: self.body.pack(fill="x"); self._arrow.config(text="▾")
        else:          self.body.pack_forget();  self._arrow.config(text="▸")


class ScrolledPage(tk.Frame):
    """Canvas-backed scrollable page frame."""
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=C_BG2, **kw)
        c = tk.Canvas(self, bg=C_BG2, highlightthickness=0, bd=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=c.yview)
        self.inner = tk.Frame(c, bg=C_BG2)
        win = c.create_window((0,0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: c.configure(scrollregion=c.bbox("all")))
        c.bind("<Configure>", lambda e: c.itemconfig(win, width=e.width))
        c.configure(yscrollcommand=sb.set)
        c.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._canvas = c

    def bind_scroll(self):
        self._canvas.bind_all("<MouseWheel>",
            lambda e: self._canvas.yview_scroll(-int(e.delta/120), "units"))


def card(parent, pad=14) -> tk.Frame:
    f = tk.Frame(parent, bg=C_BG3, padx=pad, pady=pad,
                 highlightthickness=1, highlightbackground=C_SEP2)
    return f

def hline(parent):
    tk.Frame(parent, bg=C_SEP, height=1).pack(fill="x", pady=10)

def page_title(parent, title: str, sub: str = ""):
    tk.Label(parent, text=title, bg=C_BG2, fg=C_T0,
             font=F(17,"bold"), anchor="w").pack(fill="x", pady=(0,3))
    if sub:
        tk.Label(parent, text=sub, bg=C_BG2, fg=C_T1,
                 font=F(10), anchor="w").pack(fill="x", pady=(0,18))

def label_row(parent, text: str, widget: tk.Widget, hint: str = "",
              bg: str = C_BG2):
    row = tk.Frame(parent, bg=bg); row.pack(fill="x", pady=4)
    tk.Label(row, text=text, bg=bg, fg=C_T1,
             font=F(9), anchor="w", width=24).pack(side="left")
    widget.pack(in_=row, side="left", fill="x", expand=True, padx=(0,4))
    if hint:
        tk.Label(row, text=hint, bg=bg, fg=C_T2, font=F(8)).pack(side="left")
    return row

def card_label(parent, text: str, bg: str = C_BG3):
    tk.Label(parent, text=text, bg=bg, fg=C_T2,
             font=F(8,"bold"), anchor="w").pack(fill="x", pady=(0,6))

def pri_btn(parent, text: str, cmd, w=None) -> tk.Button:
    b = tk.Button(parent, text=text, command=cmd, bg=C_ACC, fg="white",
                  font=F(10,"bold"), relief="flat", cursor="hand2",
                  padx=22, pady=10, bd=0, width=w or 0)
    b.bind("<Enter>", lambda _: b.config(bg=C_ACC2))
    b.bind("<Leave>", lambda _: b.config(bg=C_ACC))
    return b

def sec_btn(parent, text: str, cmd, w=None) -> tk.Button:
    b = tk.Button(parent, text=text, command=cmd, bg=C_BG4, fg=C_T0,
                  font=F(9), relief="flat", cursor="hand2",
                  padx=14, pady=8, bd=0, width=w or 0)
    b.bind("<Enter>", lambda _: b.config(bg=C_BG5))
    b.bind("<Leave>", lambda _: b.config(bg=C_BG4))
    return b

def danger_btn(parent, text: str, cmd) -> tk.Button:
    b = tk.Button(parent, text=text, command=cmd, bg="#1e1010",
                  fg=C_ERR, font=F(9), relief="flat",
                  cursor="hand2", padx=14, pady=8, bd=0)
    b.bind("<Enter>", lambda _: b.config(bg="#2e1818"))
    b.bind("<Leave>", lambda _: b.config(bg="#1e1010"))
    return b

def mk_entry(parent, var, show="", bg=C_BG4) -> ttk.Entry:
    return ttk.Entry(parent, textvariable=var, show=show)


# ── Process runner ─────────────────────────────────────────────────────────────
class SubprocessManager:
    def __init__(self, on_line, on_done):
        self.on_line = on_line; self.on_done = on_done; self._proc = None

    @property
    def running(self):
        return self._t.is_alive() if hasattr(self, "_t") else False

    def start(self, cmd, cwd=HERE):
        if self.running: return False
        self._t = threading.Thread(target=self._run, args=(cmd,cwd), daemon=True)
        self._t.start(); return True

    def _run(self, cmd, cwd):
        try:
            self._proc = subprocess.Popen(
                [str(c) for c in cmd], stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, cwd=str(cwd),
                env={**os.environ, "EXPORT_DIR": _cfg.output_dir()}, bufsize=1)
            for line in self._proc.stdout:
                self.on_line(line.rstrip())
            self._proc.wait(); self.on_done(self._proc.returncode)
        except Exception as e:
            self.on_line(f"[ERROR] {e}"); self.on_done(1)

    def stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()


# ══════════════════════════════════════════════════════════════════════════════
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GitHub Intelligence Suite")
        self.geometry("1240x820"); self.minsize(920, 660)
        self.configure(bg=C_BG0)

        self._cfg          = ConfigManager()
        self._q            = queue.Queue()
        self._save_pending = False
        self._proc         = SubprocessManager(self._enq, self._on_done)
        self._vars: dict   = {}
        self._pages: dict[str, tk.Frame]   = {}
        self._navs:  dict[str, NavItem]    = {}
        self._cur_page = ""
        self._faq_match_indices: list = []
        self._faq_match_cursor  = -1
        self._status_dots: dict[str, tk.Label] = {}

        self._build_styles()
        self._build_ui()
        self._load_vars_from_cfg()
        self._poll_log()
        self._check_status()

    # ── ttk styles ────────────────────────────────────────────────────────────
    def _build_styles(self):
        s = ttk.Style(); s.theme_use("clam")
        s.configure("TScrollbar", background=C_BG3, troughcolor=C_BG2,
                    arrowcolor=C_T2, bordercolor=C_BG2, relief="flat")
        s.configure("TEntry", fieldbackground=C_BG4, foreground=C_T0,
                    insertcolor=C_T0, bordercolor=C_SEP2,
                    lightcolor=C_SEP2, darkcolor=C_SEP2)
        s.configure("TSpinbox", fieldbackground=C_BG4, foreground=C_T0,
                    insertcolor=C_T0, arrowcolor=C_T1,
                    bordercolor=C_SEP2)
        s.configure("TCombobox", fieldbackground=C_BG4, foreground=C_T0,
                    selectbackground=C_ACC, selectforeground="white",
                    arrowcolor=C_T1, bordercolor=C_SEP2)
        s.map("TCombobox", fieldbackground=[("readonly", C_BG4)])
        s.configure("TCheckbutton", background=C_BG3, foreground=C_T0,
                    focuscolor=C_BG3)
        s.map("TCheckbutton", background=[("active", C_BG3)])
        s.configure("TProgressbar", troughcolor=C_BG3,
                    background=C_ACC, bordercolor=C_BG3)

    # ── top-level layout ──────────────────────────────────────────────────────
    def _build_ui(self):
        # ── status bar (bottom) ──
        bar = tk.Frame(self, bg=C_BG1, height=28)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self._status_var = tk.StringVar(value="Ready")
        tk.Label(bar, textvariable=self._status_var, bg=C_BG1, fg=C_T2,
                 font=F(8), anchor="w", padx=14).pack(side="left", fill="y")
        self._pb = ttk.Progressbar(bar, mode="indeterminate", length=120)
        self._pb.pack(side="right", padx=12, pady=6)

        # ── main horizontal pane ──
        main = tk.Frame(self, bg=C_BG0)
        main.pack(fill="both", expand=True)

        # sidebar
        self._sidebar = tk.Frame(main, bg=C_BG1, width=192)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)
        self._build_sidebar()

        # thin separator
        tk.Frame(main, bg=C_SEP, width=1).pack(side="left", fill="y")

        # content area
        self._content = tk.Frame(main, bg=C_BG2)
        self._content.pack(side="left", fill="both", expand=True)

        # console panel
        self._console_frame = tk.Frame(main, bg=C_BG1, width=320)
        self._console_frame.pack(side="right", fill="y")
        self._console_frame.pack_propagate(False)
        self._build_console()

        # thin separator
        tk.Frame(main, bg=C_SEP, width=1).pack(side="right", fill="y")

        # build all pages (hidden until activated)
        self._build_page_overview()
        self._build_page_extract()
        self._build_page_discover()
        self._build_page_browse()
        self._build_page_analyse()
        self._build_page_settings()
        self._build_page_docs()

    def _build_sidebar(self):
        # logo
        logo = tk.Frame(self._sidebar, bg=C_BG1, pady=22)
        logo.pack(fill="x")
        tk.Label(logo, text="◈", bg=C_BG1, fg=C_ACC, font=F(18)).pack()
        tk.Label(logo, text="GH Intelligence", bg=C_BG1, fg=C_T0,
                 font=F(9,"bold")).pack()
        tk.Label(logo, text="Suite  v3", bg=C_BG1, fg=C_T2, font=F(8)).pack()
        tk.Frame(self._sidebar, bg=C_SEP, height=1).pack(fill="x")

        # nav items
        nav_items = [
            ("overview",  "⊹",  "Overview"),
            ("extract",   "↓",  "Extract"),
            ("discover",  "⋯",  "Discover"),
            ("browse",    "⌕",  "Browse"),
            ("analyse",   "✦",  "Analyse (PIA)"),
            ("docs",      "◎",  "Docs & FAQ"),
        ]
        nav_frame = tk.Frame(self._sidebar, bg=C_BG1)
        nav_frame.pack(fill="x", pady=(8, 0))

        for key, icon, label in nav_items:
            item = NavItem(nav_frame, icon, label,
                           lambda k=key: self._show_page(k))
            item.pack(fill="x")
            self._navs[key] = item

        # settings at bottom
        tk.Frame(self._sidebar, bg=C_SEP, height=1).pack(
            fill="x", side="bottom", pady=(0,0))
        settings_item = NavItem(self._sidebar, "⚙", "Settings",
                                lambda: self._show_page("settings"))
        settings_item.pack(fill="x", side="bottom")
        self._navs["settings"] = settings_item

    def _build_console(self):
        hdr = tk.Frame(self._console_frame, bg=C_BG1, padx=14, pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Console", bg=C_BG1, fg=C_T1,
                 font=F(9,"bold")).pack(side="left")

        btns = tk.Frame(hdr, bg=C_BG1)
        btns.pack(side="right")
        sec_btn(btns, "Clear", self._clear_log).pack(side="left", padx=(0,4))
        danger_btn(btns, "⏹", self._stop_proc).pack(side="left")

        tk.Frame(self._console_frame, bg=C_SEP, height=1).pack(fill="x")

        self._log = tk.Text(
            self._console_frame, wrap="word", bg=C_CON, fg=C_T0,
            font=FM(9), insertbackground=C_T0, state="disabled",
            padx=12, pady=10, relief="flat", bd=0,
            selectbackground=C_ACC, selectforeground="white")
        sb = ttk.Scrollbar(self._console_frame, orient="vertical",
                           command=self._log.yview)
        self._log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._log.pack(side="left", fill="both", expand=True)

        for tag, fg in [("ok",C_OK),("err",C_ERR),("warn",C_WARN),
                        ("cmd",C_CYAN),("dim",C_T2)]:
            self._log.tag_config(tag, foreground=fg)

    def _show_page(self, key: str):
        if self._cur_page:
            self._pages[self._cur_page].pack_forget()
            if self._cur_page in self._navs:
                self._navs[self._cur_page].set_active(False)
        self._cur_page = key
        self._pages[key].pack(fill="both", expand=True)
        if key in self._navs:
            self._navs[key].set_active(True)

    # ── PAGE: Overview ────────────────────────────────────────────────────────
    def _build_page_overview(self):
        sp = ScrolledPage(self._content)
        self._pages["overview"] = sp
        p = sp.inner
        p.config(padx=32, pady=28)

        page_title(p, "Overview", "System status and quick launch")

        # status cards row
        status_row = tk.Frame(p, bg=C_BG2)
        status_row.pack(fill="x", pady=(0, 20))

        items = [
            ("extractor", "↓", "GitHub\nExtractor", EXTRACTOR),
            ("platform",  "⋯", "Platform\nExtractor", PLATFORM),
            ("viewer",    "⌕", "Data\nViewer",    VIEWER),
            ("pia",       "✦", "PIA\nPipeline",   PIA_DIR),
            ("output",    "◫", "Output\nFolder",  None),
        ]
        status_row.columnconfigure(list(range(len(items))), weight=1)
        for col, (key, icon, label, path) in enumerate(items):
            c = card(status_row, pad=16)
            c.grid(row=0, column=col, padx=(0,10), sticky="ew")
            tk.Label(c, text=icon, bg=C_BG3, fg=C_T2, font=F(20)).pack()
            tk.Label(c, text=label, bg=C_BG3, fg=C_T1, font=F(8),
                     justify="center").pack(pady=(4,6))
            dot = tk.Label(c, text="●  checking…", bg=C_BG3, fg=C_T2, font=F(8))
            dot.pack()
            self._status_dots[key] = dot

        # quick launch cards
        tk.Label(p, text="Quick Launch", bg=C_BG2, fg=C_T0,
                 font=F(13,"bold"), anchor="w").pack(fill="x", pady=(8,12))

        ql_row = tk.Frame(p, bg=C_BG2)
        ql_row.pack(fill="x")
        ql_row.columnconfigure([0,1,2,3], weight=1)

        launches = [
            ("↓  Extract GitHub",     "#1a1a30", C_ACCL, lambda: self._show_page("extract")),
            ("⋯  Discover Platforms", "#1a2020", C_CYAN, lambda: self._show_page("discover")),
            ("⌕  Browse Data",        "#1a1e2a", "#a78bfa", lambda: self._show_page("browse")),
            ("✦  Run PIA Analysis",   "#1e1a2a", "#f472b6", lambda: self._show_page("analyse")),
        ]
        for col, (lbl, bg, fg, cmd) in enumerate(launches):
            f = tk.Frame(ql_row, bg=bg, cursor="hand2",
                         highlightthickness=1, highlightbackground=C_SEP2)
            f.grid(row=0, column=col, padx=(0,10), ipady=18, sticky="ew")
            tk.Label(f, text=lbl, bg=bg, fg=fg, font=F(10,"bold"),
                     cursor="hand2").pack(pady=4)
            f.bind("<Button-1>", lambda e, c=cmd: c())
            for w in f.winfo_children(): w.bind("<Button-1>", lambda e, c=cmd: c())
            f.bind("<Enter>", lambda e, fr=f, b=bg: fr.config(bg=b))

        # recent activity hint
        hline(p)
        output_path = Path(self._cfg.output_dir() if hasattr(self._cfg, 'output_dir') else "github_export")
        idx = output_path / "_index.json"
        if idx.exists():
            try:
                import json
                data = json.loads(idx.read_text(encoding="utf-8"))
                info = f"Last extraction: {data.get('extracted_at','?')[:16].replace('T',' ')}  ·  " \
                       f"{len(data.get('repos',[]))} repos  ·  user @{data.get('github_user','?')}"
            except Exception:
                info = f"Output directory: {output_path}"
        else:
            info = "No extraction data found yet. Run Extract to get started."
        tk.Label(p, text=info, bg=C_BG2, fg=C_T2, font=F(9), anchor="w").pack(fill="x")

    # ── PAGE: Extract ─────────────────────────────────────────────────────────
    def _build_page_extract(self):
        sp = ScrolledPage(self._content)
        self._pages["extract"] = sp
        p = sp.inner
        p.config(padx=32, pady=28)

        page_title(p, "Extract", "Pull repositories, docs and issues from GitHub")

        # primary CTA
        cta_row = tk.Frame(p, bg=C_BG2)
        cta_row.pack(fill="x", pady=(0,24))
        pri_btn(cta_row, "▶   Run Extraction", self._run_github).pack(side="left")
        sec_btn(cta_row, "▶   Run Both  (GitHub + Platform)", self._run_both
                ).pack(side="left", padx=(10,0))

        # sources card
        src_card = card(p)
        src_card.pack(fill="x", pady=(0,12))
        card_label(src_card, "SOURCES")
        pill_row = tk.Frame(src_card, bg=C_BG3)
        pill_row.pack(fill="x", pady=(0,4))
        src_labels = {"owned":"Owned","forks":"Forks","starred":"Starred",
                      "trending":"Trending","collections":"Collections"}
        for s in GH_SOURCES_ALL:
            PillToggle(pill_row, src_labels[s],
                       self._v_bool("github_extractor", f"src_{s}")).pack(
                side="left", padx=(0,6), pady=2)
        tk.Label(src_card, text="Select which GitHub sources to pull from.",
                 bg=C_BG3, fg=C_T2, font=F(8)).pack(anchor="w", pady=(4,0))

        # advanced options
        adv = Expander(p, "Advanced options")
        adv.pack(fill="x", pady=(0,8))
        b = adv.body
        b.config(bg=C_BG2)

        # single repo
        sr_frame = tk.Frame(b, bg=C_BG2)
        sr_frame.pack(fill="x", pady=(0,10))
        tk.Label(sr_frame, text="Single repo override", bg=C_BG2, fg=C_T1,
                 font=F(9,"bold")).pack(anchor="w")
        tk.Label(sr_frame, text="Bypasses sources above — extracts only this repo.",
                 bg=C_BG2, fg=C_T2, font=F(8)).pack(anchor="w", pady=(0,4))
        e = mk_entry(sr_frame, self._v("github_extractor","repo"))
        e.pack(fill="x")
        tk.Label(sr_frame, text="Format: owner/repo", bg=C_BG2, fg=C_T2,
                 font=F(8)).pack(anchor="w")

        hline(b)

        # trending langs + collections full
        tl_frame = tk.Frame(b, bg=C_BG2)
        tl_frame.pack(fill="x", pady=(0,10))
        tk.Label(tl_frame, text="Trending language filter", bg=C_BG2, fg=C_T1,
                 font=F(9,"bold")).pack(anchor="w")
        e2 = mk_entry(tl_frame, self._v("github_extractor","trending_langs"))
        e2.pack(fill="x", pady=(4,0))
        tk.Label(tl_frame, text="e.g. python,rust,go  (blank = all languages)",
                 bg=C_BG2, fg=C_T2, font=F(8)).pack(anchor="w")

        ttk.Checkbutton(b, text="Collections full — fetch each collection's repo list (slower)",
                        variable=self._v_bool("github_extractor","collections_full")
                        ).pack(anchor="w", pady=(8,0))

        hline(b)

        # content toggles
        tk.Label(b, text="Content extraction", bg=C_BG2, fg=C_T1,
                 font=F(9,"bold")).pack(anchor="w", pady=(0,4))
        ttk.Checkbutton(b, text="Skip text files  (tree + metadata + issues only — fastest)",
                        variable=self._v_bool("github_extractor","skip_text_files")
                        ).pack(anchor="w")
        ttk.Checkbutton(b, text="Skip issues  (2–3× faster)",
                        variable=self._v_bool("github_extractor","skip_issues")
                        ).pack(anchor="w", pady=(4,0))

        ext_r = tk.Frame(b, bg=C_BG2); ext_r.pack(fill="x", pady=(8,0))
        tk.Label(ext_r, text="Extra extensions:", bg=C_BG2, fg=C_T1,
                 font=F(9), width=20, anchor="w").pack(side="left")
        mk_entry(ext_r, self._v("github_extractor","text_extensions")).pack(
            side="left", fill="x", expand=True)
        tk.Label(ext_r, text="e.g. .graphql,.proto", bg=C_BG2, fg=C_T2,
                 font=F(8)).pack(side="left", padx=6)

        hline(b)

        # schedule + resume
        tk.Label(b, text="Scheduling", bg=C_BG2, fg=C_T1,
                 font=F(9,"bold")).pack(anchor="w", pady=(0,4))
        ttk.Checkbutton(b, text="Resume  — skip repos already extracted (safe for re-runs)",
                        variable=self._v_bool("github_extractor","resume")
                        ).pack(anchor="w")
        sch_r = tk.Frame(b, bg=C_BG2); sch_r.pack(fill="x", pady=(8,0))
        tk.Label(sch_r, text="Repeat schedule:", bg=C_BG2, fg=C_T1,
                 font=F(9), width=20, anchor="w").pack(side="left")
        mk_entry(sch_r, self._v("github_extractor","schedule")).pack(
            side="left", fill="x", expand=True)
        tk.Label(sch_r, text="e.g. 6h · 1d · 30m  (blank = once)",
                 bg=C_BG2, fg=C_T2, font=F(8)).pack(side="left", padx=6)

        hline(b)

        # chain + SearXNG
        tk.Label(b, text="After extraction", bg=C_BG2, fg=C_T1,
                 font=F(9,"bold")).pack(anchor="w", pady=(0,4))
        ttk.Checkbutton(b, text="Chain to Platform Extractor after completion",
                        variable=self._v_bool("github_extractor","chain_platform")
                        ).pack(anchor="w")

        pfr = tk.Frame(b, bg=C_BG2); pfr.pack(fill="x", pady=(6,0))
        tk.Label(pfr, text="Platform source filter:", bg=C_BG2, fg=C_T1,
                 font=F(9), width=22, anchor="w").pack(side="left")
        mk_entry(pfr, self._v("github_extractor","platform_sources_filter")).pack(
            side="left", fill="x", expand=True)
        tk.Label(pfr, text="blank = all", bg=C_BG2, fg=C_T2, font=F(8)).pack(side="left",padx=6)

        sfr = tk.Frame(b, bg=C_BG2); sfr.pack(fill="x", pady=(6,0))
        tk.Label(sfr, text="SearXNG URL:", bg=C_BG2, fg=C_T1,
                 font=F(9), width=22, anchor="w").pack(side="left")
        mk_entry(sfr, self._v("github_extractor","searxng_url")).pack(
            side="left", fill="x", expand=True)

    # ── PAGE: Discover ────────────────────────────────────────────────────────
    def _build_page_discover(self):
        sp = ScrolledPage(self._content)
        self._pages["discover"] = sp
        p = sp.inner
        p.config(padx=32, pady=28)

        page_title(p, "Discover", "Find GitHub repos via 10 external platform plugins")

        # CTA
        cta_row = tk.Frame(p, bg=C_BG2); cta_row.pack(fill="x", pady=(0,24))
        pri_btn(cta_row, "▶   Run Discovery", self._run_platform).pack(side="left")
        sec_btn(cta_row, "List plugins", self._plat_list_sources).pack(side="left", padx=(10,0))
        sec_btn(cta_row, "Health check", self._plat_health_check).pack(side="left", padx=(6,0))

        # mode
        mode_card = card(p); mode_card.pack(fill="x", pady=(0,12))
        card_label(mode_card, "CRAWL MODE")
        Segment(mode_card,
                ["forward", "lookback", "both"],
                self._v("platform_extractor","mode")).pack(anchor="w", pady=(0,6))
        tk.Label(mode_card,
                 text="forward — new items only    ·    lookback — historical deep-scan    ·    both",
                 bg=C_BG3, fg=C_T2, font=F(8)).pack(anchor="w")

        # plugins card
        plug_card = card(p); plug_card.pack(fill="x", pady=(0,12))
        card_label(plug_card, "PLUGINS")
        plug_row = tk.Frame(plug_card, bg=C_BG3); plug_row.pack(fill="x")
        for src in PLATFORM_SOURCES:
            PillToggle(plug_row, src, self._v_bool("platform_extractor",f"src_{src}")
                       ).pack(side="left", padx=(0,6), pady=2)
        sel_row = tk.Frame(plug_card, bg=C_BG3); sel_row.pack(anchor="w", pady=(8,0))
        sec_btn(sel_row, "All",  self._plat_select_all).pack(side="left")
        sec_btn(sel_row, "None", self._plat_select_none).pack(side="left", padx=6)

        # advanced
        adv = Expander(p, "Advanced options")
        adv.pack(fill="x", pady=(0,8))
        b = adv.body; b.config(bg=C_BG2)

        # schedule + floor date
        tk.Label(b, text="Scheduling", bg=C_BG2, fg=C_T1,
                 font=F(9,"bold")).pack(anchor="w", pady=(0,6))
        fr1 = tk.Frame(b, bg=C_BG2); fr1.pack(fill="x", pady=(0,6))
        tk.Label(fr1, text="Repeat schedule:", bg=C_BG2, fg=C_T1,
                 font=F(9), width=22, anchor="w").pack(side="left")
        mk_entry(fr1, self._v("platform_extractor","schedule")).pack(
            side="left", fill="x", expand=True)
        tk.Label(fr1, text="e.g. 1d  (blank = once)", bg=C_BG2, fg=C_T2,
                 font=F(8)).pack(side="left", padx=6)

        fr2 = tk.Frame(b, bg=C_BG2); fr2.pack(fill="x", pady=(0,6))
        tk.Label(fr2, text="Lookback floor date:", bg=C_BG2, fg=C_T1,
                 font=F(9), width=22, anchor="w").pack(side="left")
        mk_entry(fr2, self._v("platform_extractor","floor_date")).pack(
            side="left")
        tk.Label(fr2, text="YYYY-MM-DD  — don't go further back",
                 bg=C_BG2, fg=C_T2, font=F(8)).pack(side="left", padx=6)

        fr3 = tk.Frame(b, bg=C_BG2); fr3.pack(fill="x", pady=(0,12))
        tk.Label(fr3, text="Lookback batch size:", bg=C_BG2, fg=C_T1,
                 font=F(9), width=22, anchor="w").pack(side="left")
        ttk.Spinbox(fr3, textvariable=self._v("platform_extractor","lookback_batch"),
                    from_=1, to=500, width=8).pack(side="left")
        tk.Label(fr3, text="pages per run (default 50)", bg=C_BG2, fg=C_T2,
                 font=F(8)).pack(side="left", padx=6)

        hline(b)

        tk.Label(b, text="Config overrides", bg=C_BG2, fg=C_T1,
                 font=F(9,"bold")).pack(anchor="w", pady=(0,6))
        fr4 = tk.Frame(b, bg=C_BG2); fr4.pack(fill="x", pady=(0,6))
        tk.Label(fr4, text="Custom config.yaml:", bg=C_BG2, fg=C_T1,
                 font=F(9), width=22, anchor="w").pack(side="left")
        mk_entry(fr4, self._v("platform_extractor","config_yaml")).pack(
            side="left", fill="x", expand=True)
        sec_btn(fr4, "Browse",
                lambda: self._browse_file("platform_extractor","config_yaml")
                ).pack(side="left", padx=6)

        fr5 = tk.Frame(b, bg=C_BG2); fr5.pack(fill="x")
        tk.Label(fr5, text="SearXNG URL:", bg=C_BG2, fg=C_T1,
                 font=F(9), width=22, anchor="w").pack(side="left")
        mk_entry(fr5, self._v("platform_extractor","searxng_url")).pack(
            side="left", fill="x", expand=True)

    # ── PAGE: Browse ──────────────────────────────────────────────────────────
    def _build_page_browse(self):
        sp = ScrolledPage(self._content)
        self._pages["browse"] = sp
        p = sp.inner
        p.config(padx=32, pady=28)

        page_title(p, "Browse", "Explore extracted repos, trending, and platform discoveries")

        # search bar
        search_card = card(p, pad=16); search_card.pack(fill="x", pady=(0,16))
        card_label(search_card, "SEARCH REPOS")
        sr = tk.Frame(search_card, bg=C_BG3); sr.pack(fill="x")
        self._search_var = tk.StringVar()
        se = mk_entry(sr, self._search_var)
        se.pack(side="left", fill="x", expand=True, ipady=4)
        se.bind("<Return>", lambda e: self._view(["search", self._search_var.get()]))
        pri_btn(sr, "Search", lambda: self._view(["search", self._search_var.get()])
                ).pack(side="left", padx=(8,0))

        # quick action grid
        qa = card(p, pad=16); qa.pack(fill="x", pady=(0,12))
        card_label(qa, "QUICK ACTIONS")
        grid = tk.Frame(qa, bg=C_BG3); grid.pack(fill="x")
        for col in range(5): grid.columnconfigure(col, weight=1)
        actions = [
            ("📊 Stats",        ["stats"]),
            ("📋 List repos",   ["list"]),
            ("📈 Ext summary",  ["ext-summary"]),
            ("📚 Collections",  ["collections"]),
            ("🔗 Sources",      ["sources"]),
        ]
        for col, (lbl, cmd) in enumerate(actions):
            sec_btn(grid, lbl, lambda c=cmd: self._view(c)).grid(
                row=0, column=col, padx=(0,6), sticky="ew", ipady=3)

        # open folder
        sec_btn(qa, "📁  Open output folder", self._open_output_folder
                ).pack(anchor="w", pady=(10,0))

        # trending
        tr_card = card(p, pad=16); tr_card.pack(fill="x", pady=(0,12))
        card_label(tr_card, "TRENDING")
        tr_row = tk.Frame(tr_card, bg=C_BG3); tr_row.pack(fill="x")
        tk.Label(tr_row, text="Period", bg=C_BG3, fg=C_T1,
                 font=F(9), width=8, anchor="w").pack(side="left")
        Segment(tr_row, ["daily","weekly","monthly"],
                self._v("viewer","trending_period")).pack(side="left", padx=(4,16))
        tk.Label(tr_row, text="Language", bg=C_BG3, fg=C_T1,
                 font=F(9), width=10, anchor="w").pack(side="left")
        mk_entry(tr_row, self._v("viewer","trending_lang")).pack(
            side="left", fill="x", expand=True, padx=4)
        tk.Label(tr_row, text="blank = all", bg=C_BG3, fg=C_T2,
                 font=F(8)).pack(side="left", padx=4)
        sec_btn(tr_row, "▶ View", self._view_trending).pack(side="left", padx=(8,0))

        # inspect repo
        repo_card = card(p, pad=16); repo_card.pack(fill="x", pady=(0,12))
        card_label(repo_card, "INSPECT A REPO")
        tk.Label(repo_card, text="Use owner__repo format (double underscore)",
                 bg=C_BG3, fg=C_T2, font=F(8)).pack(anchor="w", pady=(0,6))
        self._repo_var = tk.StringVar()
        rr = tk.Frame(repo_card, bg=C_BG3); rr.pack(fill="x")
        mk_entry(rr, self._repo_var).pack(side="left", fill="x", expand=True, ipady=3)
        for lbl, cmd in [("Detail","show"),("Issues","issues"),
                          ("Tree","tree"),("READMEs","readmes")]:
            sec_btn(rr, lbl,
                    lambda c=cmd: self._view([c, self._repo_var.get()])
                    ).pack(side="left", padx=(6,0))

        ext_row = tk.Frame(repo_card, bg=C_BG3); ext_row.pack(fill="x", pady=(8,0))
        tk.Label(ext_row, text="Text file extension filter:", bg=C_BG3, fg=C_T1,
                 font=F(9), width=26, anchor="w").pack(side="left")
        mk_entry(ext_row, self._v("viewer","text_ext_filter")).pack(
            side="left", fill="x", expand=True)
        tk.Label(ext_row, text="e.g. .py (blank=all)", bg=C_BG3, fg=C_T2,
                 font=F(8)).pack(side="left", padx=6)
        sec_btn(ext_row, "View text files",
                lambda: self._view(["text", self._repo_var.get(),
                                    self._v("viewer","text_ext_filter").get()])
                ).pack(side="left", padx=(6,0))

        # external + discoveries
        ext_card = card(p, pad=16); ext_card.pack(fill="x", pady=(0,12))
        card_label(ext_card, "EXTERNAL PLATFORM SOURCES")
        ex_r = tk.Frame(ext_card, bg=C_BG3); ex_r.pack(fill="x")
        tk.Label(ex_r, text="Source:", bg=C_BG3, fg=C_T1,
                 font=F(9), width=10, anchor="w").pack(side="left")
        mk_entry(ex_r, self._v("viewer","external_source")).pack(
            side="left", fill="x", expand=True, padx=4)
        tk.Label(ex_r, text="Date:", bg=C_BG3, fg=C_T1,
                 font=F(9), width=6, anchor="w").pack(side="left")
        mk_entry(ex_r, self._v("viewer","external_date")).pack(
            side="left", padx=4)
        sec_btn(ex_r, "▶ Browse", self._view_external).pack(side="left", padx=(6,0))

        hline(ext_card)
        card_label(ext_card, "DISCOVERIES")
        disc_r = tk.Frame(ext_card, bg=C_BG3); disc_r.pack(fill="x")
        self._disc_kw = tk.StringVar()
        tk.Label(disc_r, text="Keyword:", bg=C_BG3, fg=C_T1,
                 font=F(9), width=10, anchor="w").pack(side="left")
        mk_entry(disc_r, self._disc_kw).pack(side="left", fill="x", expand=True, padx=4)
        tk.Label(disc_r, text="Source:", bg=C_BG3, fg=C_T1,
                 font=F(9), width=8, anchor="w").pack(side="left")
        mk_entry(disc_r, self._v("viewer","discoveries_source")).pack(
            side="left", padx=4)
        sec_btn(disc_r, "▶ Search", self._view_discoveries).pack(side="left", padx=(6,0))

        disc_r2 = tk.Frame(ext_card, bg=C_BG3); disc_r2.pack(fill="x", pady=(6,0))
        tk.Label(disc_r2, text="Min score:", bg=C_BG3, fg=C_T1,
                 font=F(9), width=12, anchor="w").pack(side="left")
        ttk.Spinbox(disc_r2, textvariable=self._v("viewer","discoveries_min_score"),
                    from_=0, to=9999, width=8).pack(side="left")
        ttk.Checkbutton(disc_r2, text="Use historical lookback data",
                        variable=self._v_bool("viewer","discoveries_history")
                        ).pack(side="left", padx=16)

    # ── PAGE: Analyse (PIA) ───────────────────────────────────────────────────
    def _build_page_analyse(self):
        sp = ScrolledPage(self._content)
        self._pages["analyse"] = sp
        p = sp.inner
        p.config(padx=32, pady=28)

        page_title(p, "Analyse", "AI code review — Project Intelligence Analyst")

        # mode selector + CTA
        mode_row = tk.Frame(p, bg=C_BG2); mode_row.pack(fill="x", pady=(0,20))

        mode_card = card(mode_row, pad=16)
        mode_card.pack(side="left", fill="x", expand=True, padx=(0,16))
        card_label(mode_card, "PIPELINE MODE")
        self._pia_mode_var = tk.StringVar(value="full")
        Segment(mode_card, ["Full Pipeline","Ingest only","Scan only"],
                self._pia_mode_var).pack(anchor="w", pady=(0,6))
        mode_hints = {
            "Full Pipeline": "Ingest KB → Scan projects → Retrieve → Analyse → Report",
            "Ingest only":   "Rebuild knowledge base only (after adding new exported repos)",
            "Scan only":     "Skip ingest — re-analyse projects only (faster)",
        }
        self._pia_mode_hint = tk.Label(mode_card, text=mode_hints["Full Pipeline"],
                                        bg=C_BG3, fg=C_T2, font=F(8))
        self._pia_mode_hint.pack(anchor="w")
        def _update_hint(*_):
            self._pia_mode_hint.config(text=mode_hints.get(self._pia_mode_var.get(),""))
        self._pia_mode_var.trace_add("write", _update_hint)

        cta_col = tk.Frame(mode_row, bg=C_BG2)
        cta_col.pack(side="left")
        pri_btn(cta_col, "▶   Run Analysis", self._run_pia_from_mode).pack(fill="x")
        sec_btn(cta_col, "📁  Open Reports", self._open_reports).pack(
            fill="x", pady=(8,0))

        # project scope
        scope_card = card(p, pad=16); scope_card.pack(fill="x", pady=(0,12))
        card_label(scope_card, "PROJECT SCOPE")
        tk.Label(scope_card, text="Leave blank to analyse all discovered projects.",
                 bg=C_BG3, fg=C_T2, font=F(8)).pack(anchor="w", pady=(0,8))
        proj_r = tk.Frame(scope_card, bg=C_BG3); proj_r.pack(fill="x", pady=(0,6))
        tk.Label(proj_r, text="Project filter:", bg=C_BG3, fg=C_T1,
                 font=F(9), width=18, anchor="w").pack(side="left")
        mk_entry(proj_r, self._v("pia","project")).pack(
            side="left", fill="x", expand=True)
        tk.Label(proj_r, text="partial name match", bg=C_BG3, fg=C_T2,
                 font=F(8)).pack(side="left", padx=6)
        fe_r = tk.Frame(scope_card, bg=C_BG3); fe_r.pack(fill="x")
        tk.Label(fe_r, text="Force eligible:", bg=C_BG3, fg=C_T1,
                 font=F(9), width=18, anchor="w").pack(side="left")
        mk_entry(fe_r, self._v("pia","force_eligible")).pack(
            side="left", fill="x", expand=True)
        tk.Label(fe_r, text="bypass benchmarking check", bg=C_BG3, fg=C_T2,
                 font=F(8)).pack(side="left", padx=6)

        # advanced
        adv = Expander(p, "Advanced options")
        adv.pack(fill="x", pady=(0,8))
        b = adv.body; b.config(bg=C_BG2)

        tk.Label(b, text="Analysis toggles", bg=C_BG2, fg=C_T1,
                 font=F(9,"bold")).pack(anchor="w", pady=(0,4))
        for key, text in [
            ("no_intent",      "Skip intent gap analysis  (saves API cost)"),
            ("no_compare",     "Skip comparison engine    (saves API cost)"),
            ("skip_benchmark", "Skip Phase 1.5 benchmarking"),
        ]:
            ttk.Checkbutton(b, text=text, variable=self._v_bool("pia",key)
                            ).pack(anchor="w", pady=2)

        hline(b)

        tk.Label(b, text="Comparison targeting", bg=C_BG2, fg=C_T1,
                 font=F(9,"bold")).pack(anchor="w", pady=(0,6))
        ct_r = tk.Frame(b, bg=C_BG2); ct_r.pack(fill="x", pady=(0,6))
        tk.Label(ct_r, text="Compare topic:", bg=C_BG2, fg=C_T1,
                 font=F(9), width=20, anchor="w").pack(side="left")
        mk_entry(ct_r, self._v("pia","compare_topic")).pack(
            side="left", fill="x", expand=True)
        tk.Label(ct_r, text='e.g. "rate limiting"', bg=C_BG2, fg=C_T2,
                 font=F(8)).pack(side="left", padx=6)

        cr_r = tk.Frame(b, bg=C_BG2); cr_r.pack(fill="x")
        tk.Label(cr_r, text="Pin compare repos:", bg=C_BG2, fg=C_T1,
                 font=F(9), width=20, anchor="w").pack(side="left")
        mk_entry(cr_r, self._v("pia","compare_repos")).pack(
            side="left", fill="x", expand=True)
        tk.Label(cr_r, text="comma-separated KB names", bg=C_BG2, fg=C_T2,
                 font=F(8)).pack(side="left", padx=6)

        hline(b)

        tk.Label(b, text="Config override", bg=C_BG2, fg=C_T1,
                 font=F(9,"bold")).pack(anchor="w", pady=(0,6))
        cf_r = tk.Frame(b, bg=C_BG2); cf_r.pack(fill="x", pady=(0,8))
        tk.Label(cf_r, text="Custom config.yaml:", bg=C_BG2, fg=C_T1,
                 font=F(9), width=20, anchor="w").pack(side="left")
        mk_entry(cf_r, self._v("pia","config_yaml")).pack(
            side="left", fill="x", expand=True)
        sec_btn(cf_r, "Browse",
                lambda: self._browse_file("pia","config_yaml")
                ).pack(side="left", padx=6)

        hline(b)

        # destructive zone
        danger_zone = tk.Frame(b, bg="#140808",
                               highlightthickness=1, highlightbackground="#3a1818")
        danger_zone.pack(fill="x", pady=(4,0), ipady=4)
        tk.Label(danger_zone, text="⚠  Danger zone", bg="#140808", fg=C_ERR,
                 font=F(9,"bold")).pack(anchor="w", padx=14, pady=(8,4))
        dz_row = tk.Frame(danger_zone, bg="#140808")
        dz_row.pack(fill="x", padx=14, pady=(0,8))
        ttk.Checkbutton(dz_row,
                        text="Clear knowledge base before run  (wipes the entire vector store)",
                        variable=self._v_bool("pia","clear_kb")).pack(side="left")

    # ── PAGE: Settings ────────────────────────────────────────────────────────
    def _build_page_settings(self):
        sp = ScrolledPage(self._content)
        self._pages["settings"] = sp
        p = sp.inner
        p.config(padx=32, pady=28)

        page_title(p, "Settings", "Credentials, paths and environment setup")

        # github token
        tok_card = card(p, pad=20); tok_card.pack(fill="x", pady=(0,14))
        card_label(tok_card, "GITHUB CREDENTIALS")
        tk.Label(tok_card, text="Personal Access Token",
                 bg=C_BG3, fg=C_T0, font=F(10,"bold")).pack(anchor="w")
        tk.Label(tok_card,
                 text="Required for owned / forks / starred sources. "
                      "Get one at github.com → Settings → Developer Settings → Tokens",
                 bg=C_BG3, fg=C_T2, font=F(8), wraplength=560, justify="left"
                 ).pack(anchor="w", pady=(2,10))
        tok_row = tk.Frame(tok_card, bg=C_BG3); tok_row.pack(fill="x")
        self._token_entry = mk_entry(tok_row, self._v("github_extractor","token"), show="*")
        self._token_entry.pack(side="left", fill="x", expand=True, ipady=4)
        sec_btn(tok_row, "Show/hide", self._toggle_token_show).pack(side="left", padx=(8,0))

        # output dir
        path_card = card(p, pad=20); path_card.pack(fill="x", pady=(0,14))
        card_label(path_card, "OUTPUT DIRECTORY")
        tk.Label(path_card,
                 text="Shared by both extractors. All JSON data is written here.",
                 bg=C_BG3, fg=C_T2, font=F(8)).pack(anchor="w", pady=(0,8))
        dir_row = tk.Frame(path_card, bg=C_BG3); dir_row.pack(fill="x")
        mk_entry(dir_row, self._v("global","output_dir")).pack(
            side="left", fill="x", expand=True, ipady=4)
        sec_btn(dir_row, "Browse",
                lambda: self._browse_dir("global","output_dir")
                ).pack(side="left", padx=(8,0))
        sec_btn(dir_row, "Open folder",
                self._open_output_folder).pack(side="left", padx=6)

        # pia config
        pia_card = card(p, pad=20); pia_card.pack(fill="x", pady=(0,14))
        card_label(pia_card, "PIA CONFIGURATION")
        tk.Label(pia_card,
                 text="Edit pia/config.yaml to set your Anthropic API key, "
                      "knowledge base path, project roots and Colab credentials.",
                 bg=C_BG3, fg=C_T2, font=F(8), wraplength=560, justify="left"
                 ).pack(anchor="w", pady=(0,10))
        sec_btn(pia_card, "Edit pia/config.yaml", self._edit_config).pack(anchor="w")

        # deps
        dep_card = card(p, pad=20); dep_card.pack(fill="x", pady=(0,14))
        card_label(dep_card, "DEPENDENCIES")
        tk.Label(dep_card,
                 text="Installs PyGithub, requests, scrapling, rich, and all PIA "
                      "requirements (chromadb, sentence-transformers, torch CPU).",
                 bg=C_BG3, fg=C_T2, font=F(8), wraplength=560, justify="left"
                 ).pack(anchor="w", pady=(0,10))
        pri_btn(dep_card, "Install all dependencies", self._run_setup).pack(anchor="w")

        # component status
        stat_card = card(p, pad=20); stat_card.pack(fill="x", pady=(0,14))
        card_label(stat_card, "COMPONENT STATUS")
        self._status_dots = {}
        for key, icon, label in [
            ("extractor","↓","github_extractor_v2.py"),
            ("platform", "⋯","platform_extractor.py"),
            ("viewer",   "⌕","github_viewer_v2.py"),
            ("pia",      "✦","pia/ pipeline"),
            ("output",   "◫","output directory"),
        ]:
            row = tk.Frame(stat_card, bg=C_BG3); row.pack(fill="x", pady=3)
            tk.Label(row, text=f"{icon}  {label}", bg=C_BG3, fg=C_T1,
                     font=F(9), width=34, anchor="w").pack(side="left")
            dot = tk.Label(row, text="● checking…", bg=C_BG3, fg=C_T2, font=F(9))
            dot.pack(side="left")
            self._status_dots[key] = dot
        sec_btn(stat_card, "Refresh status", self._check_status).pack(
            anchor="w", pady=(10,0))

    # ── PAGE: Docs (FAQ) ──────────────────────────────────────────────────────
    def _build_page_docs(self):
        outer = tk.Frame(self._content, bg=C_BG2)
        self._pages["docs"] = outer

        FAQ_PATH = HERE / "FAQ.md"

        # toolbar
        tbar = tk.Frame(outer, bg=C_BG1, pady=6)
        tbar.pack(fill="x", side="top")
        tk.Label(tbar, text="  Docs & FAQ", bg=C_BG1, fg=C_T0,
                 font=F(11,"bold")).pack(side="left")

        self._faq_search_var = tk.StringVar()
        se = ttk.Entry(tbar, textvariable=self._faq_search_var, width=26)
        se.pack(side="left", padx=(24,4), ipady=3)
        se.bind("<Return>",       lambda e: self._faq_jump(+1))
        se.bind("<Shift-Return>", lambda e: self._faq_jump(-1))
        self._faq_search_var.trace_add("write", lambda *_: self._faq_do_search())

        self._faq_count_lbl = tk.Label(tbar, text="", bg=C_BG1, fg=C_T2, font=F(8))
        self._faq_count_lbl.pack(side="left")

        sec_btn(tbar, "▲", lambda: self._faq_jump(-1)).pack(side="left", padx=2)
        sec_btn(tbar, "▼", lambda: self._faq_jump(+1)).pack(side="left", padx=2)
        sec_btn(tbar, "✕", self._faq_clear_search).pack(side="left", padx=(2,16))

        # section jump
        tk.Label(tbar, text="Jump:", bg=C_BG1, fg=C_T2, font=F(8)).pack(side="left")
        self._faq_section_combo = ttk.Combobox(tbar, values=[], state="readonly", width=38)
        self._faq_section_combo.pack(side="left", padx=6)
        self._faq_section_combo.bind("<<ComboboxSelected>>", self._faq_jump_to_section)

        sec_btn(tbar, "↗ Open", lambda: self._faq_open_external(FAQ_PATH)
                ).pack(side="right", padx=8)

        tk.Frame(outer, bg=C_SEP, height=1).pack(fill="x")

        # text area
        txt_frame = tk.Frame(outer, bg=C_BG2)
        txt_frame.pack(fill="both", expand=True)
        self._faq_text = tk.Text(
            txt_frame, wrap="word", bg=C_CON, fg=C_T0,
            font=FM(9), state="disabled", padx=20, pady=16,
            relief="flat", bd=0,
            selectbackground=C_ACC, selectforeground="white",
            insertbackground=C_T0)
        fsb = ttk.Scrollbar(txt_frame, orient="vertical", command=self._faq_text.yview)
        self._faq_text.configure(yscrollcommand=fsb.set)
        fsb.pack(side="right", fill="y")
        self._faq_text.pack(side="left", fill="both", expand=True)

        self._faq_text.tag_config("h1",  foreground=C_CYAN,  font=(FUI,14,"bold"))
        self._faq_text.tag_config("h2",  foreground=C_ACCL,  font=(FUI,11,"bold"))
        self._faq_text.tag_config("h3",  foreground=C_WARN,  font=(FUI,10,"bold"))
        self._faq_text.tag_config("code",foreground=C_OK,    font=FM(9),
                                   background="#0a1008")
        self._faq_text.tag_config("bold",foreground=C_T0,    font=(FUI,9,"bold"))
        self._faq_text.tag_config("dim", foreground=C_T2)
        self._faq_text.tag_config("bullet", foreground=C_ACCL)
        self._faq_text.tag_config("hi",  background="#3a3000", foreground=C_T0)
        self._faq_text.tag_config("cur", background=C_WARN,   foreground="#111")

        self._faq_load(FAQ_PATH)

    # ── FAQ helpers ───────────────────────────────────────────────────────────
    def _faq_load(self, path: Path):
        self._faq_text.configure(state="normal")
        self._faq_text.delete("1.0","end")
        sections = []
        if not path.exists():
            self._faq_text.insert("end",
                f"FAQ.md not found at:\n  {path}\n\n"
                "Place FAQ.md alongside gui_app.py.", "dim")
            self._faq_text.configure(state="disabled"); return
        in_code = False
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if raw.startswith("```"):
                in_code = not in_code
                self._faq_text.insert("end", raw+"\n","code"); continue
            if in_code:
                self._faq_text.insert("end", raw+"\n","code"); continue
            if raw.startswith("### "):
                t=raw[4:]; self._faq_text.insert("end","   "+t+"\n","h3")
                sections.append(t); continue
            if raw.startswith("## "):
                t=raw[3:]; self._faq_text.insert("end","\n"+t+"\n","h2")
                sections.append(t); continue
            if raw.startswith("# "):
                t=raw[2:]; self._faq_text.insert("end","\n"+t+"\n","h1")
                sections.append(t); continue
            if raw.strip().startswith("---"):
                self._faq_text.insert("end","─"*72+"\n","dim"); continue
            if raw.startswith("|"):
                self._faq_text.insert("end",raw+"\n","dim"); continue
            s=raw.lstrip()
            if s.startswith(("- ","* ","+ ")):
                self._faq_text.insert("end"," "*(len(raw)-len(s))+"• "+s[2:]+"\n","bullet")
                continue
            if "**" in raw:
                for i,pt in enumerate(raw.split("**")):
                    self._faq_text.insert("end", pt, "bold" if i%2 else "")
                self._faq_text.insert("end","\n"); continue
            self._faq_text.insert("end", raw+"\n")
        self._faq_text.configure(state="disabled")
        self._faq_section_combo.configure(values=sections)

    def _faq_do_search(self):
        self._faq_text.tag_remove("hi","1.0","end")
        self._faq_text.tag_remove("cur","1.0","end")
        self._faq_match_indices=[]; self._faq_match_cursor=-1
        term=self._faq_search_var.get()
        if not term: self._faq_count_lbl.config(text=""); return
        start="1.0"
        while True:
            pos=self._faq_text.search(term,start,stopindex="end",nocase=True)
            if not pos: break
            ep=f"{pos}+{len(term)}c"
            self._faq_text.tag_add("hi",pos,ep)
            self._faq_match_indices.append(pos); start=ep
        n=len(self._faq_match_indices)
        if n: self._faq_count_lbl.config(text=f"{n} match{'es' if n!=1 else ''}"); self._faq_jump(+1)
        else: self._faq_count_lbl.config(text="no matches")

    def _faq_jump(self, d:int):
        if not self._faq_match_indices: return
        if self._faq_match_cursor>=0:
            pos=self._faq_match_indices[self._faq_match_cursor]
            self._faq_text.tag_remove("cur",pos,f"{pos}+{len(self._faq_search_var.get())}c")
        n=len(self._faq_match_indices)
        self._faq_match_cursor=(self._faq_match_cursor+d)%n
        pos=self._faq_match_indices[self._faq_match_cursor]
        t=self._faq_search_var.get()
        self._faq_text.tag_add("cur",pos,f"{pos}+{len(t)}c")
        self._faq_text.see(pos)
        self._faq_count_lbl.config(text=f"{self._faq_match_cursor+1} / {n}")

    def _faq_clear_search(self):
        self._faq_search_var.set("")
        self._faq_text.tag_remove("hi","1.0","end")
        self._faq_text.tag_remove("cur","1.0","end")
        self._faq_count_lbl.config(text="")

    def _faq_jump_to_section(self, _=None):
        h=self._faq_section_combo.get()
        if not h: return
        pos=self._faq_text.search(h,"1.0",stopindex="end",nocase=True)
        if pos: self._faq_text.see(pos); self._faq_text.mark_set("insert",pos)

    def _faq_open_external(self, path:Path):
        if not path.exists():
            messagebox.showwarning("Not found", f"FAQ.md not found at:\n{path}"); return
        try:
            if sys.platform=="win32": os.startfile(str(path))
            elif sys.platform=="darwin": subprocess.Popen(["open",str(path)])
            else: subprocess.Popen([os.environ.get("EDITOR","xdg-open"),str(path)])
        except Exception as e: messagebox.showerror("Error",str(e))

    # ── PIA run helper ────────────────────────────────────────────────────────
    def _run_pia_from_mode(self):
        mode = self._pia_mode_var.get()
        if mode == "Ingest only":   self._run_pia({"ingest_only":True,"scan_only":False})
        elif mode == "Scan only":   self._run_pia({"scan_only":True,"ingest_only":False})
        else:                       self._run_pia_full()

    # ── Var binding ───────────────────────────────────────────────────────────
    def _v(self, sec:str, key:str) -> tk.StringVar:
        ns=self._vars.setdefault(sec,{})
        if key not in ns:
            v=tk.StringVar(); v.trace_add("write",lambda *_: self._schedule_save()); ns[key]=v
        return ns[key]

    def _v_bool(self, sec:str, key:str) -> tk.BooleanVar:
        ns=self._vars.setdefault(sec,{})
        if key not in ns:
            v=tk.BooleanVar(); v.trace_add("write",lambda *_: self._schedule_save()); ns[key]=v
        return ns[key]

    def _v_int(self, sec:str, key:str) -> tk.IntVar:
        ns=self._vars.setdefault(sec,{})
        if key not in ns:
            v=tk.IntVar(); v.trace_add("write",lambda *_: self._schedule_save()); ns[key]=v
        return ns[key]

    def _load_vars_from_cfg(self):
        for sec, data in self._cfg._data.items():
            for key, val in data.items():
                if isinstance(val, bool):
                    self._v_bool(sec,key).set(val)
                elif isinstance(val, int):
                    self._v(sec,key).set(str(val))
                elif isinstance(val, list):
                    if key=="sources" and sec in ("github_extractor","platform_extractor"):
                        all_s = GH_SOURCES_ALL if sec=="github_extractor" else PLATFORM_SOURCES
                        for s in all_s: self._v_bool(sec,f"src_{s}").set(s in val)
                    else:
                        self._v(sec,key).set(",".join(str(v) for v in val))
                else:
                    self._v(sec,key).set(str(val) if val is not None else "")

    def _collect_to_cfg(self):
        self._cfg.set("global","output_dir",self._v("global","output_dir").get())
        ge="github_extractor"
        self._cfg.set(ge,"token",         self._v(ge,"token").get())
        self._cfg.set(ge,"sources",       [s for s in GH_SOURCES_ALL
                                            if self._v_bool(ge,f"src_{s}").get()])
        self._cfg.set(ge,"collections_full",  self._v_bool(ge,"collections_full").get())
        self._cfg.set(ge,"repo",              self._v(ge,"repo").get())
        self._cfg.set(ge,"trending_langs",    self._v(ge,"trending_langs").get())
        self._cfg.set(ge,"skip_text_files",   self._v_bool(ge,"skip_text_files").get())
        self._cfg.set(ge,"text_extensions",   self._v(ge,"text_extensions").get())
        self._cfg.set(ge,"skip_issues",       self._v_bool(ge,"skip_issues").get())
        self._cfg.set(ge,"resume",            self._v_bool(ge,"resume").get())
        self._cfg.set(ge,"schedule",          self._v(ge,"schedule").get())
        self._cfg.set(ge,"searxng_url",       self._v(ge,"searxng_url").get())
        self._cfg.set(ge,"chain_platform",    self._v_bool(ge,"chain_platform").get())
        self._cfg.set(ge,"platform_sources_filter", self._v(ge,"platform_sources_filter").get())

        pe="platform_extractor"
        self._cfg.set(pe,"mode",         self._v(pe,"mode").get())
        self._cfg.set(pe,"schedule",     self._v(pe,"schedule").get())
        self._cfg.set(pe,"floor_date",   self._v(pe,"floor_date").get())
        try: self._cfg.set(pe,"lookback_batch",int(self._v(pe,"lookback_batch").get()))
        except ValueError: pass
        self._cfg.set(pe,"sources",      [s for s in PLATFORM_SOURCES
                                           if self._v_bool(pe,f"src_{s}").get()])
        self._cfg.set(pe,"config_yaml",  self._v(pe,"config_yaml").get())
        self._cfg.set(pe,"searxng_url",  self._v(pe,"searxng_url").get())

        for k in ("project","force_eligible","compare_topic","compare_repos","config_yaml"):
            self._cfg.set("pia",k,self._v("pia",k).get())
        for k in ("ingest_only","scan_only","no_intent","no_compare","skip_benchmark","clear_kb"):
            self._cfg.set("pia",k,self._v_bool("pia",k).get())

        for k in ("discoveries_source","external_source","external_date",
                  "text_ext_filter","trending_period","trending_lang"):
            self._cfg.set("viewer",k,self._v("viewer",k).get())
        self._cfg.set("viewer","discoveries_history",
                      self._v_bool("viewer","discoveries_history").get())
        try: self._cfg.set("viewer","discoveries_min_score",
                           int(self._v("viewer","discoveries_min_score").get()))
        except ValueError: pass

    def _schedule_save(self):
        if not self._save_pending:
            self._save_pending=True; self.after(1400,self._do_save)

    def _do_save(self):
        self._collect_to_cfg(); self._cfg.save(); self._save_pending=False

    # ── Console ───────────────────────────────────────────────────────────────
    def _enq(self, line): self._q.put(line)

    def _poll_log(self):
        try:
            while True: self._write_log(self._q.get_nowait())
        except queue.Empty: pass
        self.after(60, self._poll_log)

    def _write_log(self, line: str):
        self._log.configure(state="normal")
        ll=line.lower()
        tag=("ok"   if any(x in ll for x in ("✓","done","saved","success","complete")) else
             "err"  if any(x in ll for x in ("error","✗","failed","traceback")) else
             "warn" if any(x in ll for x in ("warn","⚠","skip")) else
             "cmd"  if line.lstrip().startswith("$") else "")
        self._log.insert("end", line+"\n", tag)
        self._log.see("end"); self._log.configure(state="disabled")

    def _clear_log(self):
        self._log.configure(state="normal"); self._log.delete("1.0","end")
        self._log.configure(state="disabled")

    def _stop_proc(self):
        self._proc.stop(); self._enq("⏹  Stopped.")

    # ── Process control ───────────────────────────────────────────────────────
    def _busy(self, msg):
        self._status_var.set(f"  ⏳  {msg}"); self._pb.start(12)

    def _idle(self, msg="Ready"):
        self._status_var.set(f"  {msg}"); self._pb.stop()

    def _on_done(self, rc):
        msg="✓  Done" if rc==0 else f"✗  Exited {rc}"
        self.after(0, self._idle, msg)
        self._enq(f"\n{'✓' if rc==0 else '✗'}  Process finished (exit {rc}).\n")

    def _launch(self, cmd, label, cwd=HERE):
        if self._proc.running:
            messagebox.showwarning("Busy","A process is already running.\nStop it first."); return
        self._collect_to_cfg(); self._busy(label)
        self._enq(f"\n{'═'*50}\n  {label}\n{'═'*50}")
        self._enq(f"  $ {' '.join(str(c) for c in cmd)}\n")
        self._proc.start(cmd, cwd=cwd)

    def _check_script(self, path, name):
        if not path.exists():
            messagebox.showerror("Missing",
                f"{name} not found at:\n{path}\n\n"
                "Place the script in the same folder as gui_app.py."); return False
        return True

    # ── Actions ───────────────────────────────────────────────────────────────
    def _run_setup(self):
        req=PIA_DIR/"requirements.txt"
        cmd=[PYTHON,"-m","pip","install","-r",str(req),"PyGithub","requests","scrapling"] \
            if req.exists() else \
            [PYTHON,"-m","pip","install","--upgrade","PyGithub","requests","scrapling","rich"]
        self._launch(cmd,"Installing dependencies")

    def _edit_config(self):
        if not PIA_CONFIG.exists():
            messagebox.showwarning("Not found",f"config.yaml not found at:\n{PIA_CONFIG}"); return
        try:
            if sys.platform=="win32": os.startfile(str(PIA_CONFIG))
            elif sys.platform=="darwin": subprocess.Popen(["open","-e",str(PIA_CONFIG)])
            else: subprocess.Popen([os.environ.get("EDITOR","xdg-open"),str(PIA_CONFIG)])
        except Exception as e: messagebox.showerror("Error",str(e))

    def _run_github(self):
        if not self._check_script(EXTRACTOR,"github_extractor_v2.py"): return
        self._collect_to_cfg()
        self._launch(self._cfg.build_github_cmd(PYTHON,EXTRACTOR),"GitHub Extractor")

    def _run_platform(self):
        if not self._check_script(PLATFORM,"platform_extractor.py"): return
        self._collect_to_cfg()
        self._launch(self._cfg.build_platform_cmd(PYTHON,PLATFORM),"Platform Extractor")

    def _run_both(self):
        if not self._check_script(EXTRACTOR,"github_extractor_v2.py"): return
        self._collect_to_cfg()
        self._cfg._data["github_extractor"]["chain_platform"]=True
        cmd=self._cfg.build_github_cmd(PYTHON,EXTRACTOR)
        self._cfg._data["github_extractor"]["chain_platform"]=\
            self._v_bool("github_extractor","chain_platform").get()
        self._launch(cmd,"Full Extraction  (GitHub → Platform)")

    def _view(self, sub: list[str]):
        if not self._check_script(VIEWER,"github_viewer_v2.py"): return
        args=[a for a in sub if a]
        self._launch([PYTHON,str(VIEWER)]+args,f"Viewer: {' '.join(args)}")

    def _view_trending(self):
        period=self._v("viewer","trending_period").get() or "daily"
        lang=self._v("viewer","trending_lang").get()
        self._view(["trending",period]+([lang] if lang else []))

    def _view_external(self):
        src=self._v("viewer","external_source").get()
        date=self._v("viewer","external_date").get()
        self._view(["external"]+([src] if src else [])+([date] if date else []))

    def _view_discoveries(self):
        kw=self._disc_kw.get()
        disc_args=([kw] if kw else [])+self._cfg.build_discoveries_args()
        self._view(["discoveries"]+disc_args)

    def _run_pia_full(self):
        if not PIA_DIR.exists():
            messagebox.showerror("Missing",f"pia/ not found at:\n{PIA_DIR}"); return
        self._collect_to_cfg()
        if self._cfg.get("pia","clear_kb"):
            if not messagebox.askyesno("⚠ Clear KB",
                "This will WIPE the entire vector store.\nAre you sure?"): return
        self._launch(self._cfg.build_pia_cmd(PYTHON,PIA_PIPELINE),"PIA Full Pipeline",cwd=PIA_DIR)

    def _run_pia(self, overrides:dict):
        if not PIA_DIR.exists():
            messagebox.showerror("Missing","pia/ not found."); return
        self._collect_to_cfg()
        cmd=self._cfg.build_pia_cmd(PYTHON,PIA_PIPELINE,overrides)
        label="PIA — "+("Ingest only" if overrides.get("ingest_only") else "Scan only")
        self._launch(cmd,label,cwd=PIA_DIR)

    def _plat_list_sources(self):
        if not self._check_script(PLATFORM,"platform_extractor.py"): return
        self._launch([PYTHON,str(PLATFORM),"--list-sources"],"Platform — list plugins")

    def _plat_health_check(self):
        if not self._check_script(PLATFORM,"platform_extractor.py"): return
        self._launch([PYTHON,str(PLATFORM),"--check"],"Platform — health check")

    def _plat_select_all(self):
        for s in PLATFORM_SOURCES: self._v_bool("platform_extractor",f"src_{s}").set(True)

    def _plat_select_none(self):
        for s in PLATFORM_SOURCES: self._v_bool("platform_extractor",f"src_{s}").set(False)

    def _open_output_folder(self):
        path=Path(self._cfg.output_dir())
        if not path.is_absolute(): path=HERE/path
        path.mkdir(parents=True,exist_ok=True)
        try:
            if sys.platform=="win32": os.startfile(str(path))
            elif sys.platform=="darwin": subprocess.Popen(["open",str(path)])
            else: subprocess.Popen(["xdg-open",str(path)])
        except Exception as e: messagebox.showerror("Error",str(e))

    def _open_reports(self):
        d=HERE/"reports"
        if not d.exists():
            messagebox.showinfo("Not found","No reports yet — run PIA pipeline first."); return
        try:
            if sys.platform=="win32": os.startfile(str(d))
            elif sys.platform=="darwin": subprocess.Popen(["open",str(d)])
            else: subprocess.Popen(["xdg-open",str(d)])
        except Exception as e: messagebox.showerror("Error",str(e))

    def _browse_dir(self, sec, key):
        d=filedialog.askdirectory(title="Select directory",initialdir=str(HERE))
        if d: self._v(sec,key).set(d)

    def _browse_file(self, sec, key):
        f=filedialog.askopenfilename(title="Select file",
            filetypes=[("YAML","*.yaml *.yml"),("All","*.*")])
        if f: self._v(sec,key).set(f)

    def _toggle_token_show(self):
        cur=self._token_entry.cget("show")
        self._token_entry.config(show="" if cur else "*")

    def _check_status(self):
        output_ok=Path(self._cfg.output_dir()).exists()
        checks = {
            "extractor": EXTRACTOR.exists(),
            "platform":  PLATFORM.exists(),
            "viewer":    VIEWER.exists(),
            "pia":       PIA_DIR.exists() and PIA_PIPELINE.exists(),
            "output":    output_ok,
        }
        for key, ok in checks.items():
            dot = self._status_dots.get(key)
            if dot:
                dot.config(text=("●  Found" if ok else "●  Not found"),
                           fg=(C_OK if ok else C_ERR))


def main():
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    App().mainloop()

if __name__ == "__main__":
    main()
