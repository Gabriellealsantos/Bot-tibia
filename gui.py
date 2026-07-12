# -*- coding: utf-8 -*-
"""
Interface do bot — Tkinter (ja vem com o Python, zero dependencia extra),
com tema escuro estilizado.

Abas:
  GERAL     -> start/stop, status (HP/mana/monstros), toggles dos modulos,
               hotkeys globais (panico + liga/desliga attack/spell/cavebot), log
  COMBATE   -> presets + combo de magias/runas (Nome/Tecla/Mana%/Criaturas)
  CURA      -> cura por magia, cura por potion, mana potion (por preset)
  CAVEBOT   -> gestao de rota: arquivo, waypoints (lista/editar/gravar), espera

A GUI nao decide nada: edita os presets/settings (presets.PresetStore),
manda o BotRunner aplicar (apply_preset/apply_settings) e mostra o estado.
Toda a logica de decisao continua em combat.py/healbot.py/cavebot.py.

Thread-safety: as threads do bot escrevem em runner.status e no stdout; a
GUI le num timer (root.after) na thread principal do Tk — nunca mexemos em
widgets a partir das threads do bot. Trocas de preset/settings partem sempre
da thread do Tk e trocam listas/dicts por inteiro (nunca in-place).
"""
import copy
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

import config
from cavebot import load_waypoints, save_waypoints
from game_state import BotRunner
from inputs import VK
from window import find_window, list_windows, set_opacity

# ---------------------------------------------------------------- paleta
BG = "#23272e"        # fundo geral
PANEL = "#2c313a"     # frames elevados / botoes
INPUT_BG = "#1b1e24"  # campos e tabelas
FG = "#d7dae0"        # texto
MUTED = "#8b93a1"     # texto secundario
ACCENT = "#4f8cff"    # azul (destaque)
OK = "#3fb950"        # verde (rodando)
DANGER = "#e5534b"    # vermelho (HP / parar)
BORDER = "#3a4048"

COMBAT_FIELDS = [
    ("name", "Nome", "str"),
    ("key", "Tecla", "key"),
    ("min_monsters", "Criaturas mínimas", "int"),
    ("mana_pct", "Mana % mínima", "int"),
    ("cooldown", "Cooldown (s)", "float"),
]
HEAL_TIER_FIELDS = [
    ("name", "Nome", "str"),
    ("key", "Tecla", "key"),
    ("hp_below_pct", "HP abaixo de %", "int"),
    ("cooldown", "Cooldown (s)", "float"),
]


def _spin_range(key: str) -> tuple[float, float, float]:
    """Faixa/step de Spinbox pro campo, deduzida pelo nome da chave."""
    if key.endswith("_pct"):
        return (0, 100, 1)
    if key == "cooldown":
        return (0, 60, 0.5)
    if key == "min_monsters":
        return (0, 20, 1)
    return (0, 999, 1)


class LogRedirector:
    """Captura os print() dos modulos e entrega pra GUI via fila."""

    def __init__(self):
        self.lines: queue.Queue[str] = queue.Queue()
        self._stdout = sys.stdout

    def write(self, text):
        self._stdout.write(text)
        if text.strip():
            self.lines.put(text.strip())

    def flush(self):
        self._stdout.flush()


class BotGUI:
    def __init__(self):
        self.runner = BotRunner()
        self.log = LogRedirector()
        sys.stdout = self.log

        self.root = tk.Tk()
        self.root.title("Zegani Bot — Elite Knight")
        # o processo e DPI-aware (pra captura funcionar em telas com zoom);
        # sem escalar, a GUI sairia pequena. Ajusta fontes/tamanho ao DPI real.
        ppi = self.root.winfo_fpixels("1i")
        self._ui_scale = max(1.0, ppi / 96.0)
        self.root.tk.call("tk", "scaling", ppi / 72.0)
        self.root.geometry(f"{int(840 * self._ui_scale)}x{int(760 * self._ui_scale)}")
        self.root.minsize(int(720 * self._ui_scale), int(640 * self._ui_scale))
        self.root.configure(bg=BG)

        self._setup_theme()

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self._build_geral_tab()
        self._build_combate_tab()
        self._build_cura_tab()
        self._build_cavebot_tab()
        self._build_calibrar_tab()

        self._reload_preset_combobox()
        self._refresh_combo_tree()
        self._spell_heal_handlers["refresh"]()
        self._potion_heal_handlers["refresh"]()
        self._refresh_mana_potion_form()
        self._refresh_hotkey_labels()
        self._reload_waypoints_ui()
        self._refresh_cave_config_form()

        self.root.after(200, self._refresh)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------- tema
    def _setup_theme(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure(".", background=BG, foreground=FG, fieldbackground=INPUT_BG,
                        bordercolor=BORDER, font=("Segoe UI", 9))
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure("Header.TLabel", background=BG, foreground=FG,
                        font=("Segoe UI Semibold", 11))
        style.configure("TLabelframe", background=BG, bordercolor=BORDER)
        style.configure("TLabelframe.Label", background=BG, foreground=ACCENT,
                        font=("Segoe UI Semibold", 9))
        style.configure("TCheckbutton", background=BG, foreground=FG)
        style.map("TCheckbutton", background=[("active", BG)],
                  foreground=[("disabled", MUTED)])

        style.configure("TButton", background=PANEL, foreground=FG, bordercolor=BORDER,
                        focuscolor=BG, padding=(10, 5))
        style.map("TButton",
                  background=[("active", "#3a4150"), ("pressed", "#454d5e")])
        style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff",
                        padding=(14, 7), font=("Segoe UI Semibold", 10))
        style.map("Accent.TButton", background=[("active", "#3f78e0"), ("pressed", "#356ad0")])
        style.configure("Small.TButton", padding=(6, 3))

        style.configure("TNotebook", background=BG, bordercolor=BORDER, tabmargins=(4, 4, 0, 0))
        style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(16, 8))
        style.map("TNotebook.Tab",
                  background=[("selected", BG)], foreground=[("selected", FG)])

        style.configure("Treeview", background=INPUT_BG, fieldbackground=INPUT_BG,
                        foreground=FG, bordercolor=BORDER, rowheight=24)
        style.configure("Treeview.Heading", background=PANEL, foreground=FG,
                        relief="flat", font=("Segoe UI Semibold", 9))
        style.map("Treeview.Heading", background=[("active", "#39404b")])
        style.map("Treeview", background=[("selected", ACCENT)],
                  foreground=[("selected", "#ffffff")])

        style.configure("TEntry", fieldbackground=INPUT_BG, foreground=FG,
                        bordercolor=BORDER, insertcolor=FG)
        style.configure("TCombobox", fieldbackground=INPUT_BG, foreground=FG,
                        background=PANEL, bordercolor=BORDER, arrowcolor=FG)
        style.map("TCombobox", fieldbackground=[("readonly", INPUT_BG)],
                  foreground=[("readonly", FG)], background=[("readonly", PANEL)])
        style.configure("TSpinbox", fieldbackground=INPUT_BG, foreground=FG,
                        background=PANEL, bordercolor=BORDER, arrowcolor=FG, insertcolor=FG)

        style.configure("HP.Horizontal.TProgressbar", background=DANGER,
                        troughcolor=INPUT_BG, bordercolor=BORDER, thickness=18)
        style.configure("Mana.Horizontal.TProgressbar", background=ACCENT,
                        troughcolor=INPUT_BG, bordercolor=BORDER, thickness=18)

        # dropdown do Combobox (listbox Tk classica, so estilizavel via option db)
        self.root.option_add("*TCombobox*Listbox.background", INPUT_BG)
        self.root.option_add("*TCombobox*Listbox.foreground", FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    # ============================================================ ABA GERAL
    def _build_geral_tab(self):
        frame = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(frame, text="Geral")
        self._build_windows(frame)
        self._build_header(frame)
        self._build_status(frame)
        self._build_modules(frame)
        self._build_hotkeys(frame)
        self._build_log(frame)

    def _build_windows(self, parent):
        s = self.runner.presets.get_settings()
        frame = ttk.LabelFrame(parent, text=" Janelas (necessário: cliente OT + projetor do OBS) ", padding=12)
        frame.pack(fill="x", pady=(0, 6))
        frame.columnconfigure(1, weight=1)

        # janela de captura (o que o bot enxerga = projetor do OBS)
        ttk.Label(frame, text="Captura (o bot enxerga):").grid(row=0, column=0, sticky="w", pady=3)
        self.capture_win_var = tk.StringVar(value=s.get("capture_window_title", ""))
        self.capture_win_var.trace_add("write",
            lambda *_: self.runner.presets.set_setting("capture_window_title", self.capture_win_var.get()))
        self.capture_combo = ttk.Combobox(frame, textvariable=self.capture_win_var)
        self.capture_combo.grid(row=0, column=1, sticky="ew", padx=8)

        # janela do cliente (recebe teclas/cliques + opacidade)
        ttk.Label(frame, text="Cliente (recebe input):").grid(row=1, column=0, sticky="w", pady=3)
        self.client_win_var = tk.StringVar(value=s.get("client_window_title", ""))
        self.client_win_var.trace_add("write",
            lambda *_: self.runner.presets.set_setting("client_window_title", self.client_win_var.get()))
        self.client_combo = ttk.Combobox(frame, textvariable=self.client_win_var)
        self.client_combo.grid(row=1, column=1, sticky="ew", padx=8)

        ttk.Button(frame, text="Atualizar lista", style="Small.TButton",
                   command=self._refresh_window_lists).grid(row=0, column=2, rowspan=2, padx=4)

        # opacidade da janela do cliente
        opa = ttk.Frame(frame)
        opa.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Label(opa, text="Opacidade do cliente (1 = invisível, 255 = normal):").pack(side="left")
        self.opacity_var = tk.StringVar(value=str(s.get("opacity", 255)))
        self.opacity_var.trace_add("write", self._on_opacity_var)
        ttk.Spinbox(opa, from_=1, to=255, textvariable=self.opacity_var, width=6).pack(side="left", padx=8)
        ttk.Button(opa, text="Aplicar", style="Small.TButton",
                   command=lambda: self._apply_opacity(int(self.opacity_var.get() or 255))).pack(side="left", padx=2)
        ttk.Button(opa, text="Restaurar (255)", style="Small.TButton",
                   command=lambda: (self.opacity_var.set("255"), self._apply_opacity(255))).pack(side="left", padx=2)

        self._refresh_window_lists()

    def _refresh_window_lists(self):
        titles = list_windows()
        # nao lista a propria janela do bot como opcao
        titles = [t for t in titles if "Zegani Bot" not in t]
        self.capture_combo["values"] = titles
        self.client_combo["values"] = titles

    def _on_opacity_var(self, *_):
        try:
            self.runner.presets.set_setting("opacity", int(self.opacity_var.get()))
        except ValueError:
            pass  # campo vazio/incompleto durante digitacao

    def _apply_opacity(self, value):
        from tkinter import messagebox
        value = max(1, min(255, value))
        title = self.client_win_var.get().strip()
        hwnd = find_window(title) if title else 0
        if not hwnd:
            messagebox.showwarning("Opacidade", f"Janela do cliente '{title}' não encontrada.")
            return
        set_opacity(hwnd, value)
        print(f"[gui] opacidade do cliente '{title}' -> {value}")

    def _build_header(self, parent):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=(0, 10))
        self.btn = ttk.Button(frame, text="▶  Iniciar bot", style="Accent.TButton",
                              command=self._toggle)
        self.btn.pack(side="left")
        self.conn_label = ttk.Label(frame, text="● parado", style="Muted.TLabel")
        self.conn_label.pack(side="left", padx=12)
        self.panic_label = ttk.Label(frame, text="pânico: F12", style="Muted.TLabel")
        self.panic_label.pack(side="right")

    def _build_status(self, parent):
        frame = ttk.LabelFrame(parent, text=" Status (o que o bot enxerga) ", padding=12)
        frame.pack(fill="x", pady=6)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="HP").grid(row=0, column=0, sticky="w")
        self.hp_bar = ttk.Progressbar(frame, style="HP.Horizontal.TProgressbar", maximum=100)
        self.hp_bar.grid(row=0, column=1, sticky="ew", padx=8)
        self.hp_label = ttk.Label(frame, text="--%", width=5)
        self.hp_label.grid(row=0, column=2)

        ttk.Label(frame, text="Mana").grid(row=1, column=0, sticky="w", pady=6)
        self.mana_bar = ttk.Progressbar(frame, style="Mana.Horizontal.TProgressbar", maximum=100)
        self.mana_bar.grid(row=1, column=1, sticky="ew", padx=8, pady=6)
        self.mana_label = ttk.Label(frame, text="--%", width=5)
        self.mana_label.grid(row=1, column=2)

        self.info_label = ttk.Label(frame, text="monstros: 0     alvo: não", style="Muted.TLabel")
        self.info_label.grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))

    def _build_modules(self, parent):
        frame = ttk.LabelFrame(parent, text=" Módulos (liga/desliga individual) ", padding=12)
        frame.pack(fill="x", pady=6)
        self.vars: dict[str, tk.BooleanVar] = {}
        labels = {
            "heal": "Healbot — cura e potions por % de HP/mana",
            "attack": "Auto-attack — seleciona e ataca o alvo (targeting)",
            "spell": "Auto-spell — solta o combo de magias/runas",
            "loot": "Auto-loot — abre corpos ao redor quando o alvo morre",
        }
        for name, text in labels.items():
            self._add_module_check(frame, name, text)

    def _add_module_check(self, parent, name, text):
        var = tk.BooleanVar(value=self.runner.enabled.get(name, True))
        var.trace_add("write",
            lambda *_, n=name, v=var: self.runner.enabled.__setitem__(n, v.get()))
        ttk.Checkbutton(parent, text=text, variable=var).pack(anchor="w", pady=1)
        self.vars[name] = var

    def _build_hotkeys(self, parent):
        frame = ttk.LabelFrame(parent, text=" Hotkeys globais (funcionam com o jogo em foco) ", padding=12)
        frame.pack(fill="x", pady=6)
        self.hotkey_labels: dict[str, ttk.Label] = {}
        rows = [
            ("hotkey_panic", "Pânico (parar tudo)"),
            ("hotkey_toggle_attack", "Liga/desliga Auto-attack"),
            ("hotkey_toggle_spell", "Liga/desliga Auto-spell"),
            ("hotkey_toggle_cavebot", "Liga/desliga Cavebot"),
        ]
        for i, (key, label) in enumerate(rows):
            ttk.Label(frame, text=label).grid(row=i, column=0, sticky="w", pady=2)
            val = ttk.Label(frame, text="--", width=8, style="Header.TLabel")
            val.grid(row=i, column=1, padx=12)
            self.hotkey_labels[key] = val
            ttk.Button(frame, text="Definir tecla", style="Small.TButton",
                       command=lambda k=key: self._set_hotkey(k)).grid(row=i, column=2, padx=4)

    def _refresh_hotkey_labels(self):
        s = self.runner.presets.get_settings()
        for key, label in self.hotkey_labels.items():
            label.config(text=s.get(key, "--"))
        self.panic_label.config(text=f"pânico: {s.get('hotkey_panic', 'F12')}")

    def _set_hotkey(self, setting_key):
        def save(name):
            self.runner.presets.set_setting(setting_key, name)
            self._refresh_hotkey_labels()
        self._capture_key(self.root, save)

    def _build_log(self, parent):
        frame = ttk.LabelFrame(parent, text=" Log (o que o bot decide) ", padding=6)
        frame.pack(fill="both", expand=True, pady=(6, 0))
        self.log_box = ScrolledText(frame, height=7, state="disabled",
                                    font=("Consolas", 9), background="#171a1f",
                                    foreground="#c7ccd4", relief="flat", borderwidth=0)
        self.log_box.pack(fill="both", expand=True)

    # =========================================================== ABA COMBATE
    def _build_combate_tab(self):
        frame = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(frame, text="Combate")

        preset_row = ttk.Frame(frame)
        preset_row.pack(fill="x", pady=(0, 10))
        ttk.Label(preset_row, text="Preset:", style="Header.TLabel").pack(side="left")
        self.preset_combo = ttk.Combobox(preset_row, state="readonly", width=20)
        self.preset_combo.pack(side="left", padx=8)
        self.preset_combo.bind("<<ComboboxSelected>>", self._on_preset_selected)
        ttk.Button(preset_row, text="Novo", style="Small.TButton", command=self._new_preset).pack(side="left", padx=2)
        ttk.Button(preset_row, text="Renomear", style="Small.TButton", command=self._rename_preset).pack(side="left", padx=2)
        ttk.Button(preset_row, text="Excluir", style="Small.TButton", command=self._delete_preset).pack(side="left", padx=2)

        ttk.Label(frame, text="Combo de ataque (magias/runas) — prioridade = ordem da lista",
                  style="Muted.TLabel").pack(anchor="w")
        self.combo_tree = ttk.Treeview(frame, columns=("prio", "name", "key", "mana", "mon"),
                                        show="headings", height=10)
        for col, text, w in [("prio", "Prio.", 40), ("name", "Nome", 160), ("key", "Tecla", 70),
                             ("mana", "Mana %", 80), ("mon", "Criaturas", 80)]:
            self.combo_tree.heading(col, text=text)
            self.combo_tree.column(col, width=w, anchor="center")
        self.combo_tree.pack(fill="both", expand=True, pady=6)
        self.combo_tree.bind("<Double-1>", lambda e: self._edit_combo_row())

        btns = ttk.Frame(frame)
        btns.pack(fill="x")
        ttk.Button(btns, text="Adicionar", style="Small.TButton", command=self._add_combo_row).pack(side="left", padx=2)
        ttk.Button(btns, text="Editar", style="Small.TButton", command=self._edit_combo_row).pack(side="left", padx=2)
        ttk.Button(btns, text="Remover", style="Small.TButton", command=self._remove_combo_row).pack(side="left", padx=2)
        ttk.Button(btns, text="▲", width=3, style="Small.TButton", command=lambda: self._move_combo_row(-1)).pack(side="left", padx=2)
        ttk.Button(btns, text="▼", width=3, style="Small.TButton", command=lambda: self._move_combo_row(1)).pack(side="left", padx=2)

        ttk.Label(frame, text="Auto Target: sempre ativo (o bot já seleciona alvo automaticamente)",
                  style="Muted.TLabel").pack(anchor="w", pady=(10, 0))

    def _refresh_combo_tree(self):
        self.combo_tree.delete(*self.combo_tree.get_children())
        for i, spell in enumerate(self.runner.presets.get_combo()):
            self.combo_tree.insert("", "end", iid=str(i),
                values=(i + 1, spell["name"], spell["key"], spell["mana_pct"], spell["min_monsters"]))

    def _commit_combo(self, combo):
        self.runner.presets.set_combo(combo)
        self.runner.apply_preset()
        self._refresh_combo_tree()

    def _selected_index(self, tree) -> int | None:
        sel = tree.selection()
        return int(sel[0]) if sel else None

    def _add_combo_row(self):
        self._open_entry_form("Nova magia/runa", COMBAT_FIELDS, None,
            lambda v: self._commit_combo(self.runner.presets.get_combo() + [v]))

    def _edit_combo_row(self):
        idx = self._selected_index(self.combo_tree)
        if idx is None:
            return
        combo = self.runner.presets.get_combo()
        def save(v):
            combo[idx] = v
            self._commit_combo(combo)
        self._open_entry_form("Editar magia/runa", COMBAT_FIELDS, combo[idx], save)

    def _remove_combo_row(self):
        idx = self._selected_index(self.combo_tree)
        if idx is None:
            return
        combo = self.runner.presets.get_combo()
        combo.pop(idx)
        self._commit_combo(combo)

    def _move_combo_row(self, delta):
        idx = self._selected_index(self.combo_tree)
        if idx is None:
            return
        combo = self.runner.presets.get_combo()
        new_idx = idx + delta
        if 0 <= new_idx < len(combo):
            combo[idx], combo[new_idx] = combo[new_idx], combo[idx]
            self._commit_combo(combo)
            self.combo_tree.selection_set(str(new_idx))

    # ============================================================== ABA CURA
    def _build_cura_tab(self):
        frame = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(frame, text="Cura")

        spell_frame = ttk.LabelFrame(frame, text=" Cura por Magia ", padding=10)
        spell_frame.pack(fill="both", expand=True, pady=(0, 10))
        self._spell_heal_handlers = self._make_heal_handlers(
            spell_frame, "Nova cura por magia", "Editar cura por magia",
            self.runner.presets.get_spell_heal, self.runner.presets.set_spell_heal)

        potion_frame = ttk.LabelFrame(frame, text=" Cura por Potion ", padding=10)
        potion_frame.pack(fill="both", expand=True, pady=(0, 10))
        self._potion_heal_handlers = self._make_heal_handlers(
            potion_frame, "Nova cura por potion", "Editar cura por potion",
            self.runner.presets.get_potion_heal, self.runner.presets.set_potion_heal)

        mana_frame = ttk.LabelFrame(frame, text=" Mana Potion ", padding=10)
        mana_frame.pack(fill="x")
        self.mana_key_var = tk.StringVar()
        self.mana_pct_var = tk.StringVar()
        self.mana_cd_var = tk.StringVar()
        ttk.Label(mana_frame, text="Tecla:").grid(row=0, column=0, padx=4, pady=4, sticky="w")
        ttk.Entry(mana_frame, textvariable=self.mana_key_var, width=8, state="readonly").grid(row=0, column=1, padx=4)
        ttk.Button(mana_frame, text="Definir tecla", style="Small.TButton",
                   command=lambda: self._capture_key(self.root, self.mana_key_var.set)
                   ).grid(row=0, column=2, padx=4)
        ttk.Label(mana_frame, text="Mana abaixo de %:").grid(row=0, column=3, padx=4, sticky="w")
        ttk.Spinbox(mana_frame, from_=0, to=100, textvariable=self.mana_pct_var, width=6).grid(row=0, column=4, padx=4)
        ttk.Label(mana_frame, text="Cooldown (s):").grid(row=0, column=5, padx=4, sticky="w")
        ttk.Spinbox(mana_frame, from_=0, to=60, increment=0.5, textvariable=self.mana_cd_var, width=6).grid(row=0, column=6, padx=4)
        ttk.Button(mana_frame, text="Salvar", style="Small.TButton", command=self._save_mana_potion).grid(row=0, column=7, padx=8)

    def _make_heal_handlers(self, parent, title_add, title_edit, getter, setter) -> dict:
        """Constroi 1 secao de cura (Treeview + botoes) e devolve os
        callbacks; cura-por-magia e cura-por-potion tem a mesma forma
        (name/key/hp_below_pct/cooldown), so muda de onde leem/gravam."""
        tree = ttk.Treeview(parent, columns=("prio", "name", "key", "hp"), show="headings", height=4)
        for col, text, w in [("prio", "Prio.", 40), ("name", "Nome", 160), ("key", "Tecla", 70), ("hp", "HP <", 70)]:
            tree.heading(col, text=text)
            tree.column(col, width=w, anchor="center")
        tree.pack(fill="both", expand=True)

        def refresh():
            tree.delete(*tree.get_children())
            for i, t in enumerate(getter()):
                tree.insert("", "end", iid=str(i), values=(i + 1, t["name"], t["key"], t["hp_below_pct"]))

        def commit(tiers):
            setter(tiers)
            self.runner.apply_preset()
            refresh()

        def selected():
            sel = tree.selection()
            return int(sel[0]) if sel else None

        def add():
            self._open_entry_form(title_add, HEAL_TIER_FIELDS, None, lambda v: commit(getter() + [v]))

        def edit():
            idx = selected()
            if idx is None:
                return
            tiers = getter()
            def save(v):
                tiers[idx] = v
                commit(tiers)
            self._open_entry_form(title_edit, HEAL_TIER_FIELDS, tiers[idx], save)

        def remove():
            idx = selected()
            if idx is None:
                return
            tiers = getter()
            tiers.pop(idx)
            commit(tiers)

        def move(delta):
            idx = selected()
            if idx is None:
                return
            tiers = getter()
            new_idx = idx + delta
            if 0 <= new_idx < len(tiers):
                tiers[idx], tiers[new_idx] = tiers[new_idx], tiers[idx]
                commit(tiers)
                tree.selection_set(str(new_idx))

        tree.bind("<Double-1>", lambda e: edit())
        btns = ttk.Frame(parent)
        btns.pack(fill="x", pady=(6, 0))
        ttk.Button(btns, text="Adicionar", style="Small.TButton", command=add).pack(side="left", padx=2)
        ttk.Button(btns, text="Editar", style="Small.TButton", command=edit).pack(side="left", padx=2)
        ttk.Button(btns, text="Remover", style="Small.TButton", command=remove).pack(side="left", padx=2)
        ttk.Button(btns, text="▲", width=3, style="Small.TButton", command=lambda: move(-1)).pack(side="left", padx=2)
        ttk.Button(btns, text="▼", width=3, style="Small.TButton", command=lambda: move(1)).pack(side="left", padx=2)

        return {"refresh": refresh}

    def _refresh_mana_potion_form(self):
        mp = self.runner.presets.get_mana_potion()
        self.mana_key_var.set(mp.get("key", ""))
        self.mana_pct_var.set(str(mp.get("mana_below_pct", 0)))
        self.mana_cd_var.set(str(mp.get("cooldown", 0)))

    def _save_mana_potion(self):
        from tkinter import messagebox
        key = self.mana_key_var.get().strip()
        if not key:
            messagebox.showwarning("Mana Potion", "Defina uma tecla.")
            return
        try:
            pct = int(float(self.mana_pct_var.get()))
            cd = float(self.mana_cd_var.get())
        except ValueError:
            messagebox.showwarning("Mana Potion", "Valores inválidos.")
            return
        self.runner.presets.set_mana_potion({"key": key, "mana_below_pct": pct, "cooldown": cd})
        self.runner.apply_preset()

    # =========================================================== ABA CAVEBOT
    def _build_cavebot_tab(self):
        frame = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(frame, text="Cavebot")

        # arquivo de rota
        file_row = ttk.Frame(frame)
        file_row.pack(fill="x", pady=(0, 8))
        ttk.Label(file_row, text="Arquivo de rota:", style="Header.TLabel").pack(side="left")
        self.wp_file_var = tk.StringVar()
        ttk.Entry(file_row, textvariable=self.wp_file_var, state="readonly", width=34).pack(side="left", padx=8)
        ttk.Button(file_row, text="Carregar...", style="Small.TButton", command=self._load_route_file).pack(side="left", padx=2)
        ttk.Button(file_row, text="Salvar como...", style="Small.TButton", command=self._save_route_as).pack(side="left", padx=2)

        # ligar cavebot + progresso
        state_row = ttk.Frame(frame)
        state_row.pack(fill="x", pady=(0, 8))
        cave_var = tk.BooleanVar(value=self.runner.enabled.get("cavebot", True))
        cave_var.trace_add("write",
            lambda *_, v=cave_var: self.runner.enabled.__setitem__("cavebot", v.get()))
        ttk.Checkbutton(state_row, text="Cavebot ligado", variable=cave_var).pack(side="left")
        self.vars["cavebot"] = cave_var
        self.cave_progress_label = ttk.Label(state_row, text="Waypoint 0 / 0", style="Muted.TLabel")
        self.cave_progress_label.pack(side="right")

        ttk.Label(frame, text="Waypoints (ordem = sequência da rota no minimapa)",
                  style="Muted.TLabel").pack(anchor="w")
        self.wp_tree = ttk.Treeview(frame, columns=("idx", "x", "y"), show="headings", height=10)
        for col, text, w in [("idx", "#", 50), ("x", "X (minimapa)", 140), ("y", "Y (minimapa)", 140)]:
            self.wp_tree.heading(col, text=text)
            self.wp_tree.column(col, width=w, anchor="center")
        self.wp_tree.pack(fill="both", expand=True, pady=6)

        btns = ttk.Frame(frame)
        btns.pack(fill="x")
        ttk.Button(btns, text="Gravar rota", style="Small.TButton", command=self._record_route).pack(side="left", padx=2)
        ttk.Button(btns, text="Recarregar", style="Small.TButton", command=self._reload_waypoints_ui).pack(side="left", padx=2)
        ttk.Button(btns, text="Remover", style="Small.TButton", command=self._remove_waypoint).pack(side="left", padx=2)
        ttk.Button(btns, text="Limpar tudo", style="Small.TButton", command=self._clear_waypoints).pack(side="left", padx=2)
        ttk.Button(btns, text="▲", width=3, style="Small.TButton", command=lambda: self._move_waypoint(-1)).pack(side="left", padx=2)
        ttk.Button(btns, text="▼", width=3, style="Small.TButton", command=lambda: self._move_waypoint(1)).pack(side="left", padx=2)

        # config do cavebot
        cfg = ttk.LabelFrame(frame, text=" Configuração ", padding=10)
        cfg.pack(fill="x", pady=(10, 0))
        self.cave_wait_var = tk.StringVar()
        self.cave_reckey_var = tk.StringVar()
        self.cave_hotkey_var = tk.StringVar()
        ttk.Label(cfg, text="Espera entre waypoints (s):").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        ttk.Spinbox(cfg, from_=0, to=30, increment=0.5, textvariable=self.cave_wait_var, width=6).grid(row=0, column=1, padx=4)
        ttk.Label(cfg, text="Tecla de gravar:").grid(row=0, column=2, sticky="w", padx=4)
        ttk.Entry(cfg, textvariable=self.cave_reckey_var, width=6, state="readonly").grid(row=0, column=3, padx=4)
        ttk.Button(cfg, text="Definir", style="Small.TButton",
                   command=lambda: self._capture_key(self.root, self.cave_reckey_var.set)).grid(row=0, column=4, padx=4)
        ttk.Label(cfg, text="Hotkey liga/desliga:").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(cfg, textvariable=self.cave_hotkey_var, width=6, state="readonly").grid(row=1, column=1, padx=4)
        ttk.Button(cfg, text="Definir", style="Small.TButton",
                   command=lambda: self._capture_key(self.root, self.cave_hotkey_var.set)).grid(row=1, column=2, padx=4)
        ttk.Button(cfg, text="Salvar config", style="Small.TButton", command=self._save_cave_config).grid(row=1, column=4, padx=4)

        # config do auto-loot
        loot = ttk.LabelFrame(frame, text=" Auto-loot ", padding=10)
        loot.pack(fill="x", pady=(8, 0))
        self.loot_radius_var = tk.StringVar()
        self.loot_settle_var = tk.StringVar()
        self.loot_delay_var = tk.StringVar()
        ttk.Label(loot, text="Raio (1 = 3x3, 2 = 5x5):").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        ttk.Spinbox(loot, from_=1, to=3, textvariable=self.loot_radius_var, width=5).grid(row=0, column=1, padx=4)
        ttk.Label(loot, text="Esperar char parar (s):").grid(row=0, column=2, sticky="w", padx=4)
        ttk.Spinbox(loot, from_=0, to=2, increment=0.1, textvariable=self.loot_settle_var, width=5).grid(row=0, column=3, padx=4)
        ttk.Label(loot, text="Delay entre cliques (s):").grid(row=0, column=4, sticky="w", padx=4)
        ttk.Spinbox(loot, from_=0, to=1, increment=0.05, textvariable=self.loot_delay_var, width=5).grid(row=0, column=5, padx=4)
        ttk.Button(loot, text="Salvar", style="Small.TButton", command=self._save_loot_config).grid(row=0, column=6, padx=8)
        ttk.Label(loot, text="Dica: desligue 'Perseguir Oponente' no Tibia p/ o char ficar parado e os corpos caírem do lado.",
                  style="Muted.TLabel").grid(row=1, column=0, columnspan=7, sticky="w", pady=(4, 0))

    def _refresh_cave_config_form(self):
        s = self.runner.presets.get_settings()
        self.wp_file_var.set(s.get("waypoints_file", ""))
        self.cave_wait_var.set(str(s.get("waypoint_wait", 4.0)))
        self.cave_reckey_var.set(s.get("record_key", ""))
        self.cave_hotkey_var.set(s.get("hotkey_toggle_cavebot", ""))
        self.loot_radius_var.set(str(s.get("loot_radius", 1)))
        self.loot_settle_var.set(str(s.get("loot_settle", 0.4)))
        self.loot_delay_var.set(str(s.get("loot_delay", 0.25)))

    def _save_loot_config(self):
        from tkinter import messagebox
        try:
            radius = int(float(self.loot_radius_var.get()))
            settle = float(self.loot_settle_var.get())
            delay = float(self.loot_delay_var.get())
        except ValueError:
            messagebox.showwarning("Auto-loot", "Valores inválidos.")
            return
        self.runner.presets.set_setting("loot_radius", radius)
        self.runner.presets.set_setting("loot_settle", settle)
        self.runner.presets.set_setting("loot_delay", delay)
        self.runner.apply_settings()

    def _current_route_file(self) -> str:
        return self.runner.presets.get_settings().get("waypoints_file", config.WAYPOINTS_FILE)

    def _reload_waypoints_ui(self):
        """Recarrega a lista de waypoints do arquivo atual pra Treeview e,
        se o bot estiver rodando, manda o cavebot vivo recarregar tambem."""
        self._waypoints = load_waypoints(self._current_route_file())
        self._refresh_wp_tree()
        self.runner.reload_cavebot()

    def _refresh_wp_tree(self):
        self.wp_tree.delete(*self.wp_tree.get_children())
        for i, (x, y) in enumerate(self._waypoints):
            self.wp_tree.insert("", "end", iid=str(i), values=(i + 1, x, y))

    def _commit_waypoints(self):
        save_waypoints(self._current_route_file(), self._waypoints)
        self._refresh_wp_tree()
        self.runner.reload_cavebot()

    def _remove_waypoint(self):
        idx = self._selected_index(self.wp_tree)
        if idx is None:
            return
        self._waypoints.pop(idx)
        self._commit_waypoints()

    def _clear_waypoints(self):
        from tkinter import messagebox
        if not self._waypoints:
            return
        if messagebox.askyesno("Limpar rota", "Apagar TODOS os waypoints desta rota?"):
            self._waypoints = []
            self._commit_waypoints()

    def _move_waypoint(self, delta):
        idx = self._selected_index(self.wp_tree)
        if idx is None:
            return
        new_idx = idx + delta
        if 0 <= new_idx < len(self._waypoints):
            self._waypoints[idx], self._waypoints[new_idx] = self._waypoints[new_idx], self._waypoints[idx]
            self._commit_waypoints()
            self.wp_tree.selection_set(str(new_idx))

    def _load_route_file(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(title="Carregar rota",
            filetypes=[("JSON", "*.json"), ("Todos", "*.*")])
        if not path:
            return
        self.runner.presets.set_setting("waypoints_file", os.path.relpath(path) if _is_subpath(path) else path)
        self.runner.apply_settings()
        self._refresh_cave_config_form()
        self._reload_waypoints_ui()

    def _save_route_as(self):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(title="Salvar rota como", defaultextension=".json",
            filetypes=[("JSON", "*.json")])
        if not path:
            return
        save_waypoints(path, getattr(self, "_waypoints", []))
        self.runner.presets.set_setting("waypoints_file", os.path.relpath(path) if _is_subpath(path) else path)
        self.runner.apply_settings()
        self._refresh_cave_config_form()
        self._reload_waypoints_ui()

    def _record_route(self):
        from tkinter import messagebox
        path = self._current_route_file()
        messagebox.showinfo("Gravar rota",
            "Vai abrir uma janela do minimapa (o projetor do OBS precisa estar aberto).\n\n"
            "Clique nos pontos da rota NA ORDEM e tecle Q para salvar e fechar.\n"
            "Os waypoints atuais deste arquivo serão substituídos.")

        def worker():
            try:
                subprocess.run([sys.executable, "cavebot.py", "record", path])
            except Exception as e:
                print(f"[gui] falha ao gravar rota: {e}")
            finally:
                self.root.after(0, self._reload_waypoints_ui)

        threading.Thread(target=worker, daemon=True).start()

    def _save_cave_config(self):
        from tkinter import messagebox
        try:
            wait = float(self.cave_wait_var.get())
        except ValueError:
            messagebox.showwarning("Cavebot", "Espera inválida.")
            return
        self.runner.presets.set_setting("waypoint_wait", wait)
        if self.cave_reckey_var.get().strip():
            self.runner.presets.set_setting("record_key", self.cave_reckey_var.get().strip())
        if self.cave_hotkey_var.get().strip():
            self.runner.presets.set_setting("hotkey_toggle_cavebot", self.cave_hotkey_var.get().strip())
        self.runner.apply_settings()
        self._refresh_hotkey_labels()

    # ========================================================== ABA CALIBRAR
    def _build_calibrar_tab(self):
        frame = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(frame, text="Calibrar")

        self._cal = copy.deepcopy(self.runner.presets.get_settings().get("calibration", {}))
        self._cal_frame = None      # ultimo frame capturado (numpy, full-res)
        self._cal_view = 1.0        # px de tela por px do frame (zoom desejado)
        self._cal_ratio = 1.0       # razao real aplicada (inteira: zoom/subsample)
        self._cal_photo = None      # ref pro PhotoImage (evita garbage collect)
        self._cal_png = None
        self._cal_mode = None       # qual ponto estamos marcando

        ttk.Label(frame, text="1) Capture o frame do projetor · 2) clique num alvo abaixo · "
                  "3) clique no ponto na imagem · 4) Testar · 5) Salvar",
                  style="Muted.TLabel").pack(anchor="w")

        top = ttk.Frame(frame)
        top.pack(fill="x", pady=6)
        ttk.Button(top, text="Capturar frame", style="Small.TButton",
                   command=self._capture_calib_frame).pack(side="left")
        self.calib_status = ttk.Label(top, text="nenhum frame capturado", style="Muted.TLabel")
        self.calib_status.pack(side="left", padx=10)
        ttk.Button(top, text="Testar leitura", style="Small.TButton",
                   command=self._test_calib_reading).pack(side="right")
        ttk.Button(top, text="Salvar calibração", style="Accent.TButton",
                   command=self._save_calibration).pack(side="right", padx=6)

        # botoes de alvo (o que vamos marcar no proximo clique)
        targets = ttk.Frame(frame)
        targets.pack(fill="x", pady=4)
        target_defs = [
            ("hp_start", "HP: início"), ("hp_end", "HP: fim"),
            ("mana_start", "Mana: início"), ("mana_end", "Mana: fim"),
            ("bl_tl", "Battle List ↖"), ("bl_br", "Battle List ↘"),
            ("ga_center", "Personagem (centro)"), ("ga_sqm", "1 SQM à direita"),
            ("mm_tl", "Minimapa ↖"), ("mm_br", "Minimapa ↘"),
        ]
        for i, (mode, label) in enumerate(target_defs):
            ttk.Button(targets, text=label, style="Small.TButton",
                       command=lambda m=mode: self._set_calib_mode(m)
                       ).grid(row=i // 5, column=i % 5, padx=2, pady=2, sticky="ew")
        for c in range(5):
            targets.columnconfigure(c, weight=1)

        self.calib_hint = ttk.Label(frame, text="Capture um frame para começar.", style="Header.TLabel")
        self.calib_hint.pack(anchor="w", pady=(4, 0))
        self.calib_pos = ttk.Label(frame, text="", style="Muted.TLabel")
        self.calib_pos.pack(anchor="w")
        self.calib_test = ttk.Label(frame, text="", style="Header.TLabel")
        self.calib_test.pack(anchor="w")

        zoom_row = ttk.Frame(frame)
        zoom_row.pack(fill="x", pady=(2, 0))
        ttk.Label(zoom_row, text="Zoom:").pack(side="left")
        ttk.Button(zoom_row, text="−", width=3, style="Small.TButton",
                   command=lambda: self._zoom_calib(1 / 1.5)).pack(side="left", padx=2)
        self.calib_zoom_lbl = ttk.Label(zoom_row, text="100%", width=6, style="Header.TLabel")
        self.calib_zoom_lbl.pack(side="left")
        ttk.Button(zoom_row, text="+", width=3, style="Small.TButton",
                   command=lambda: self._zoom_calib(1.5)).pack(side="left", padx=2)
        ttk.Button(zoom_row, text="Ajustar", style="Small.TButton",
                   command=self._fit_calib).pack(side="left", padx=6)
        ttk.Label(zoom_row, text="(dê zoom e use a rolagem p/ mirar; Ctrl+scroll também dá zoom)",
                  style="Muted.TLabel").pack(side="left", padx=6)

        canvas_wrap = ttk.Frame(frame)
        canvas_wrap.pack(fill="both", expand=True, pady=6)
        canvas_wrap.rowconfigure(0, weight=1)
        canvas_wrap.columnconfigure(0, weight=1)
        self.calib_canvas = tk.Canvas(canvas_wrap, bg=INPUT_BG, highlightthickness=1,
                                      highlightbackground=BORDER, cursor="crosshair")
        xsb = ttk.Scrollbar(canvas_wrap, orient="horizontal", command=self.calib_canvas.xview)
        ysb = ttk.Scrollbar(canvas_wrap, orient="vertical", command=self.calib_canvas.yview)
        self.calib_canvas.configure(xscrollcommand=xsb.set, yscrollcommand=ysb.set)
        self.calib_canvas.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")
        self.calib_canvas.bind("<Button-1>", self._on_calib_click)
        self.calib_canvas.bind("<Motion>", self._on_calib_motion)
        self.calib_canvas.bind("<MouseWheel>",
                               lambda e: self.calib_canvas.yview_scroll(int(-e.delta / 120), "units"))
        self.calib_canvas.bind("<Shift-MouseWheel>",
                               lambda e: self.calib_canvas.xview_scroll(int(-e.delta / 120), "units"))
        self.calib_canvas.bind("<Control-MouseWheel>",
                               lambda e: self._zoom_calib(1.5 if e.delta > 0 else 1 / 1.5))

    def _zoom_calib(self, factor):
        if self._cal_frame is None:
            return
        self._cal_view = max(0.2, min(6.0, self._cal_view * factor))
        self._render_calib_canvas()

    def _fit_calib(self):
        if self._cal_frame is None:
            return
        avail = max(400, self.calib_canvas.winfo_width())
        self._cal_view = min(2.0, avail / self._cal_frame.shape[1])
        self._render_calib_canvas()

    def _set_calib_mode(self, mode):
        if self._cal_frame is None:
            self.calib_hint.config(text="Capture um frame primeiro (botão 'Capturar frame').")
            return
        self._cal_mode = mode
        hints = {
            "hp_start": "Clique no INÍCIO (esquerda) da barra de HP — pega cor e altura.",
            "hp_end": "Clique no FIM (direita) da barra de HP.",
            "mana_start": "Clique no INÍCIO da barra de Mana — pega cor e altura.",
            "mana_end": "Clique no FIM da barra de Mana.",
            "bl_tl": "Clique no canto SUPERIOR-ESQUERDO da Battle List.",
            "bl_br": "Clique no canto INFERIOR-DIREITO da Battle List.",
            "ga_center": "Clique no CENTRO do seu personagem (na área do jogo).",
            "ga_sqm": "Clique 1 quadrado (SQM) à DIREITA do personagem.",
            "mm_tl": "Clique no canto SUPERIOR-ESQUERDO do minimapa.",
            "mm_br": "Clique no canto INFERIOR-DIREITO do minimapa.",
        }
        self.calib_hint.config(text=hints.get(mode, ""))

    def _capture_calib_frame(self):
        from tkinter import messagebox
        title = self.capture_win_var.get().strip()
        hwnd = find_window(title) if title else 0
        if not hwnd:
            messagebox.showwarning("Calibrar", f"Janela de captura '{title}' não encontrada.\n"
                                   "Escolha o projetor na aba Geral primeiro.")
            return
        try:
            from capture import capture
            self._cal_frame = capture(hwnd)
        except Exception as e:
            messagebox.showwarning("Calibrar", f"Falha ao capturar frame: {e}")
            return
        h, w = self._cal_frame.shape[:2]
        import cv2
        import tempfile
        self._cal_png = os.path.join(tempfile.gettempdir(), "zegani_calib.png")
        cv2.imwrite(self._cal_png, self._cal_frame)
        self._cal_view = min(1.0, 950.0 / w)  # comeca vendo o frame inteiro
        self._render_calib_canvas()
        self.calib_status.config(text=f"frame {w}x{h}")
        self.calib_hint.config(text="Frame capturado. Dê zoom (+) na barra, escolha um alvo e clique.")

    def _render_calib_canvas(self):
        if not self._cal_png:
            return
        img = tk.PhotoImage(file=self._cal_png)
        v = self._cal_view
        if v >= 1:                       # ampliar: zoom inteiro
            k = max(1, int(round(v)))
            img = img.zoom(k)
            self._cal_ratio = float(k)
        else:                            # reduzir: subsample inteiro
            k = max(1, int(round(1.0 / v)))
            img = img.subsample(k)
            self._cal_ratio = 1.0 / k
        self._cal_photo = img  # mantem referencia
        self.calib_canvas.delete("all")
        self.calib_canvas.create_image(0, 0, anchor="nw", image=img)
        self.calib_canvas.config(scrollregion=(0, 0, img.width(), img.height()))
        self.calib_zoom_lbl.config(text=f"{self._cal_ratio * 100:.0f}%")
        self._draw_calib_overlay()

    def _draw_calib_overlay(self):
        """Desenha o que ja esta calibrado sobre o frame (na escala do zoom)."""
        r = self._cal_ratio
        c = self.calib_canvas
        cal = self._cal

        def rect(region, color):
            if not region:
                return
            x, y = region.get("x", 0) * r, region.get("y", 0) * r
            w, h = region.get("w", 0) * r, region.get("h", 0) * r
            c.create_rectangle(x, y, x + w, y + h, outline=color, width=2)

        def bar(region, color):
            if not region:
                return
            y = region.get("y", 0) * r
            x0 = region.get("x_start", 0) * r
            x1 = region.get("x_end", 0) * r
            c.create_line(x0, y, x1, y, fill=color, width=3)

        bar(cal.get("hp_bar"), "#ff5555")
        bar(cal.get("mana_bar"), "#5599ff")
        rect(cal.get("battle_list"), "#ffdd55")
        rect(cal.get("minimap"), "#55ffaa")
        ga = cal.get("game_area")
        if ga:
            px, py = ga.get("player_x", 0) * r, ga.get("player_y", 0) * r
            c.create_oval(px - 4, py - 4, px + 4, py + 4, outline="#ff88ff", width=2)

    def _canvas_to_frame(self, event) -> tuple[int, int]:
        """Converte o clique/cursor do canvas (com rolagem e zoom) para o
        pixel real do frame."""
        cx = self.calib_canvas.canvasx(event.x)
        cy = self.calib_canvas.canvasy(event.y)
        return int(cx / self._cal_ratio), int(cy / self._cal_ratio)

    def _on_calib_motion(self, event):
        if self._cal_frame is None:
            return
        x, y = self._canvas_to_frame(event)
        h, w = self._cal_frame.shape[:2]
        if 0 <= y < h and 0 <= x < w:
            b, g, r = (int(v) for v in self._cal_frame[y, x])
            self.calib_pos.config(text=f"cursor ({x},{y})   BGR=({b},{g},{r})")

    def _on_calib_click(self, event):
        if self._cal_frame is None or not self._cal_mode:
            return
        x, y = self._canvas_to_frame(event)
        h, w = self._cal_frame.shape[:2]
        if not (0 <= y < h and 0 <= x < w):
            return
        self._apply_calib_point(self._cal_mode, x, y)
        self._cal_mode = None
        self._render_calib_canvas()
        self.calib_hint.config(text="Ponto marcado. Marque outro alvo, ou 'Testar leitura' / 'Salvar'.")

    def _apply_calib_point(self, mode, x, y):
        cal = self._cal
        b, g, r = (int(v) for v in self._cal_frame[y, x])
        cal.setdefault("hp_bar", {}).setdefault("tolerance", 30)
        cal.setdefault("mana_bar", {}).setdefault("tolerance", 30)
        if mode == "hp_start":
            cal["hp_bar"].update(x_start=x, y=y, color_bgr=[b, g, r])
        elif mode == "hp_end":
            cal["hp_bar"]["x_end"] = x
        elif mode == "mana_start":
            cal["mana_bar"].update(x_start=x, y=y, color_bgr=[b, g, r])
        elif mode == "mana_end":
            cal["mana_bar"]["x_end"] = x
        elif mode == "bl_tl":
            cal.setdefault("battle_list", {}).update(x=x, y=y)
        elif mode == "bl_br":
            bl = cal.setdefault("battle_list", {})
            bl["w"] = max(1, x - bl.get("x", 0))
            bl["h"] = max(1, y - bl.get("y", 0))
            bl.setdefault("entry_height", 22)
        elif mode == "ga_center":
            cal.setdefault("game_area", {}).update(player_x=x, player_y=y)
        elif mode == "ga_sqm":
            ga = cal.setdefault("game_area", {})
            ga["sqm_size"] = max(1, abs(x - ga.get("player_x", 0)))
        elif mode == "mm_tl":
            cal.setdefault("minimap", {}).update(x=x, y=y)
        elif mode == "mm_br":
            mm = cal.setdefault("minimap", {})
            mm["w"] = max(1, x - mm.get("x", 0))
            mm["h"] = max(1, y - mm.get("y", 0))

    def _test_calib_reading(self):
        if self._cal_frame is None:
            self.calib_test.config(text="Capture um frame primeiro.")
            return
        import vision
        vision.set_calibration(self._cal)
        hp = vision.hp_percent(self._cal_frame)
        mana = vision.mana_percent(self._cal_frame)
        mon = vision.monster_count(self._cal_frame)
        atk = vision.is_attacking(self._cal_frame)
        self.calib_test.config(
            text=f"Leitura → HP {hp:.0f}%   Mana {mana:.0f}%   Monstros {mon}   Alvo: {'sim' if atk else 'não'}")

    def _save_calibration(self):
        from tkinter import messagebox
        self.runner.presets.set_setting("calibration", self._cal)
        self.runner.apply_calibration()
        messagebox.showinfo("Calibrar", "Calibração salva e aplicada ao vivo.")

    # ================================================== formulario generico
    def _open_entry_form(self, title, fields, initial, on_save):
        """Modal de 1 linha por campo, usado pelas tabelas de combo e cura.
        `fields`: [(chave, rotulo, tipo)], tipo in {"str","int","float","key"}."""
        top = tk.Toplevel(self.root)
        top.title(title)
        top.configure(bg=BG)
        top.resizable(False, False)
        top.transient(self.root)

        vars_by_key: dict[str, tuple[str, tk.StringVar]] = {}
        for i, (key, label, ftype) in enumerate(fields):
            ttk.Label(top, text=label).grid(row=i, column=0, sticky="w", padx=10, pady=6)
            current = initial.get(key) if initial else None
            if ftype == "key":
                var = tk.StringVar(value=current or "")
                ttk.Entry(top, textvariable=var, width=10, state="readonly").grid(row=i, column=1, padx=4)
                ttk.Button(top, text="Definir tecla", style="Small.TButton",
                           command=lambda v=var: self._capture_key(top, v.set)
                           ).grid(row=i, column=2, padx=4)
            elif ftype in ("int", "float"):
                frm, to, step = _spin_range(key)
                var = tk.StringVar(value=str(current if current is not None else frm))
                ttk.Spinbox(top, from_=frm, to=to, increment=step, textvariable=var, width=10
                            ).grid(row=i, column=1, columnspan=2, sticky="w", padx=4)
            else:
                var = tk.StringVar(value=current or "")
                ttk.Entry(top, textvariable=var, width=22).grid(row=i, column=1, columnspan=2, sticky="w", padx=4)
            vars_by_key[key] = (ftype, var)

        def save():
            from tkinter import messagebox
            result = {}
            for key, (ftype, var) in vars_by_key.items():
                raw = var.get().strip()
                if ftype == "key":
                    if not raw:
                        messagebox.showwarning(title, "Defina uma tecla.", parent=top)
                        return
                    result[key] = raw
                elif ftype == "int":
                    try:
                        result[key] = int(float(raw))
                    except ValueError:
                        messagebox.showwarning(title, f"Valor inválido para '{key}'.", parent=top)
                        return
                elif ftype == "float":
                    try:
                        result[key] = float(raw)
                    except ValueError:
                        messagebox.showwarning(title, f"Valor inválido para '{key}'.", parent=top)
                        return
                else:
                    if not raw:
                        messagebox.showwarning(title, "Preencha o nome.", parent=top)
                        return
                    result[key] = raw
            top.destroy()
            on_save(result)

        btn_row = len(fields)
        ttk.Button(top, text="Salvar", style="Accent.TButton", command=save).grid(row=btn_row, column=1, pady=12)
        ttk.Button(top, text="Cancelar", style="Small.TButton", command=top.destroy).grid(row=btn_row, column=2, pady=12)
        top.grab_set()

    def _capture_key(self, parent, on_captured):
        """Abre um Toplevel modal 'Pressione uma tecla...'; captura o
        proximo KeyPress, valida contra inputs.VK e chama on_captured(nome)."""
        top = tk.Toplevel(parent)
        top.title("Definir tecla")
        top.configure(bg=BG)
        top.geometry("320x120")
        top.resizable(False, False)
        top.transient(parent)
        label = ttk.Label(top, text="Pressione uma tecla no teclado...\n(ESC cancela)",
                          justify="center")
        label.pack(expand=True, padx=20, pady=20)

        def handle(event):
            if event.keysym == "Escape":
                top.destroy()
                return
            name = self._keysym_to_vkname(event.keysym)
            if name:
                on_captured(name)
                top.destroy()
            else:
                label.config(text=f"Tecla '{event.keysym}' não suportada.\nPressione outra (ESC cancela).")

        top.bind("<KeyPress>", handle)
        top.grab_set()
        top.focus_set()

    @staticmethod
    def _keysym_to_vkname(keysym: str) -> str | None:
        special = {"space": "SPACE", "Up": "UP", "Down": "DOWN", "Left": "LEFT", "Right": "RIGHT"}
        name = special.get(keysym, keysym.upper())
        return name if name in VK else None

    # ============================================================= presets
    def _reload_preset_combobox(self, select: str | None = None):
        names = self.runner.presets.names()
        self.preset_combo["values"] = names
        self.preset_combo.set(select or self.runner.presets.active_name())

    def _on_preset_selected(self, event=None):
        self.runner.apply_preset(self.preset_combo.get())
        self._refresh_combo_tree()
        self._spell_heal_handlers["refresh"]()
        self._potion_heal_handlers["refresh"]()
        self._refresh_mana_potion_form()

    def _new_preset(self):
        from tkinter import simpledialog, messagebox
        name = simpledialog.askstring("Novo preset", "Nome do novo preset:", parent=self.root)
        if not name:
            return
        try:
            self.runner.presets.create(name, copy_from=self.runner.presets.active_name())
        except ValueError as e:
            messagebox.showwarning("Novo preset", str(e))
            return
        self._reload_preset_combobox(select=name)
        self._on_preset_selected()

    def _rename_preset(self):
        from tkinter import simpledialog, messagebox
        old = self.runner.presets.active_name()
        new = simpledialog.askstring("Renomear preset", "Novo nome:", initialvalue=old, parent=self.root)
        if not new or new == old:
            return
        try:
            self.runner.presets.rename(old, new)
        except ValueError as e:
            messagebox.showwarning("Renomear preset", str(e))
            return
        self._reload_preset_combobox(select=new)

    def _delete_preset(self):
        from tkinter import messagebox
        if len(self.runner.presets.names()) <= 1:
            messagebox.showwarning("Presets", "É preciso manter pelo menos 1 preset.")
            return
        name = self.runner.presets.active_name()
        if not messagebox.askyesno("Excluir preset", f"Excluir '{name}'?"):
            return
        self.runner.presets.delete(name)
        self._reload_preset_combobox()
        self._on_preset_selected()

    # ------------------------------------------------------------ acoes
    def _toggle(self):
        if self.runner.running.is_set():
            self.runner.stop()
            print("[gui] bot parado")
        else:
            if self.runner.start():
                print("[gui] bot iniciado")
            else:
                print("[gui] nao iniciou — confira os seletores de Captura e Cliente "
                      "na seção 'Janelas' da aba Geral (o log acima diz qual faltou).")

    def _refresh(self):
        """Timer da GUI: espelha o estado do runner nos widgets (~5x/s)."""
        running = self.runner.running.is_set()
        self.btn.config(text="⏸  Parar bot" if running else "▶  Iniciar bot")
        self.conn_label.config(text="● rodando" if running else "● parado",
                               foreground=OK if running else MUTED)

        s = self.runner.status
        self.hp_bar["value"] = s["hp"]
        self.hp_label.config(text=f"{s['hp']:.0f}%")
        self.mana_bar["value"] = s["mana"]
        self.mana_label.config(text=f"{s['mana']:.0f}%")
        self.info_label.config(
            text=f"monstros: {s['monsters']}     alvo: {'sim' if s['attacking'] else 'não'}")

        idx, total = self.runner.cave_progress()
        self.cave_progress_label.config(text=f"Waypoint {idx} / {total}")

        # espelha toggles feitos por hotkey global nos checkboxes
        for name, var in self.vars.items():
            state = self.runner.enabled.get(name, var.get())
            if var.get() != state:
                var.set(state)

        try:
            while True:
                line = self.log.lines.get_nowait()
                self.log_box.config(state="normal")
                self.log_box.insert("end", line + "\n")
                self.log_box.see("end")
                self.log_box.config(state="disabled")
        except queue.Empty:
            pass

        self.root.after(200, self._refresh)

    def _on_close(self):
        self.runner.stop()
        sys.stdout = self.log._stdout
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def _is_subpath(path: str) -> bool:
    """True se `path` esta dentro do diretorio de trabalho (pra guardar
    caminho relativo, que e o que o subprocess de gravacao espera)."""
    try:
        return os.path.commonpath([os.path.abspath(path), os.getcwd()]) == os.getcwd()
    except ValueError:
        return False


def main():
    from window import enable_dpi_awareness
    enable_dpi_awareness()  # idempotente; garante captura correta se rodar gui.py direto
    BotGUI().run()


if __name__ == "__main__":
    main()
