# -*- coding: utf-8 -*-
"""
Interface do bot — Tkinter (ja vem com o Python, zero dependencia extra).

Responsabilidades separadas em blocos visuais:
  STATUS    -> o que o bot esta ENXERGANDO (HP, mana, monstros, alvo)
  MODULOS   -> liga/desliga cada comportamento individualmente
  LOG       -> o que o bot esta DECIDINDO (os prints dos modulos)

A GUI nao decide nada: ela so mostra o estado do BotRunner e liga/
desliga flags. Toda a logica continua nos modulos — se amanha voce
quiser trocar Tkinter por web, nada do bot muda.

Thread-safety: as threads do bot escrevem em runner.status e no stdout;
a GUI le isso num timer (root.after) na thread principal do Tkinter —
nunca mexemos em widgets a partir das threads do bot.
"""
import queue
import sys
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

import config
from game_state import BotRunner


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
        self.root.geometry("420x560")
        self.root.resizable(False, False)

        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("HP.Horizontal.TProgressbar", background="#c0392b")
        style.configure("Mana.Horizontal.TProgressbar", background="#2980b9")

        self._build_header()
        self._build_status()
        self._build_modules()
        self._build_log()

        self.root.after(200, self._refresh)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------ layout
    def _build_header(self):
        frame = ttk.Frame(self.root, padding=10)
        frame.pack(fill="x")
        self.btn = ttk.Button(frame, text="▶  Iniciar bot", command=self._toggle)
        self.btn.pack(side="left")
        self.conn_label = ttk.Label(frame, text="parado", foreground="gray")
        self.conn_label.pack(side="left", padx=10)
        ttk.Label(frame, text=f"panico: {config.PAUSE_KEY}", foreground="gray").pack(side="right")

    def _build_status(self):
        frame = ttk.LabelFrame(self.root, text=" Status (o que o bot enxerga) ", padding=10)
        frame.pack(fill="x", padx=10, pady=5)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="HP").grid(row=0, column=0, sticky="w")
        self.hp_bar = ttk.Progressbar(frame, style="HP.Horizontal.TProgressbar", maximum=100)
        self.hp_bar.grid(row=0, column=1, sticky="ew", padx=6)
        self.hp_label = ttk.Label(frame, text="--%", width=5)
        self.hp_label.grid(row=0, column=2)

        ttk.Label(frame, text="Mana").grid(row=1, column=0, sticky="w", pady=4)
        self.mana_bar = ttk.Progressbar(frame, style="Mana.Horizontal.TProgressbar", maximum=100)
        self.mana_bar.grid(row=1, column=1, sticky="ew", padx=6, pady=4)
        self.mana_label = ttk.Label(frame, text="--%", width=5)
        self.mana_label.grid(row=1, column=2)

        self.info_label = ttk.Label(frame, text="monstros: 0    alvo: nao")
        self.info_label.grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))

    def _build_modules(self):
        frame = ttk.LabelFrame(self.root, text=" Módulos (liga/desliga individual) ", padding=10)
        frame.pack(fill="x", padx=10, pady=5)
        self.vars: dict[str, tk.BooleanVar] = {}
        labels = {
            "heal": "Healbot — cura e potions por % de HP/mana",
            "combat": "Combate EK — targeting + exori/exori gran por nº de monstros",
            "loot": "Auto-loot — abre corpos ao redor quando o alvo morre",
            "cavebot": "Cavebot — anda pelos waypoints do minimapa",
        }
        for name, text in labels.items():
            var = tk.BooleanVar(value=True)
            var.trace_add("write",
                lambda *_, n=name, v=var: self.runner.enabled.__setitem__(n, v.get()))
            ttk.Checkbutton(frame, text=text, variable=var).pack(anchor="w")
            self.vars[name] = var

    def _build_log(self):
        frame = ttk.LabelFrame(self.root, text=" Log (o que o bot decide) ", padding=6)
        frame.pack(fill="both", expand=True, padx=10, pady=(5, 10))
        self.log_box = ScrolledText(frame, height=10, state="disabled",
                                    font=("Consolas", 9), background="#1e1e1e",
                                    foreground="#d4d4d4")
        self.log_box.pack(fill="both", expand=True)

    # ------------------------------------------------------------ acoes
    def _toggle(self):
        if self.runner.running.is_set():
            self.runner.stop()
            print("[gui] bot parado")
        else:
            if self.runner.start():
                print("[gui] bot iniciado")
            else:
                print(f"[gui] janela nao encontrada — o cliente ('{config.WINDOW_TITLE}') "
                      f"e o projetor do OBS ('{config.CAPTURE_WINDOW_TITLE}') "
                      "precisam estar abertos!")

    def _refresh(self):
        """Timer da GUI: espelha o estado do runner nos widgets (~5x/s)."""
        running = self.runner.running.is_set()
        self.btn.config(text="⏸  Parar bot" if running else "▶  Iniciar bot")
        self.conn_label.config(text="rodando" if running else "parado",
                               foreground="#27ae60" if running else "gray")

        s = self.runner.status
        self.hp_bar["value"] = s["hp"]
        self.hp_label.config(text=f"{s['hp']:.0f}%")
        self.mana_bar["value"] = s["mana"]
        self.mana_label.config(text=f"{s['mana']:.0f}%")
        self.info_label.config(
            text=f"monstros: {s['monsters']}    alvo: {'sim' if s['attacking'] else 'nao'}")

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


def main():
    BotGUI().run()


if __name__ == "__main__":
    main()
