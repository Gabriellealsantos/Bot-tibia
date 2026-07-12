# -*- coding: utf-8 -*-
"""
Healbot: a feature mais importante — roda numa thread propria e NUNCA
espera o resto do bot (cura atrasada = char morto).

Logica (igual um jogador atento):
  HP < potion_below_pct  -> potion (emergencia, prioridade maxima)
  HP < spell_below_pct   -> magia de cura
  Mana < mana_below_pct  -> mana potion
Com cooldown proprio pra respeitar o exhaust do servidor — spammar
tecla mais rapido que o exhaust so enche o servidor de pacote inutil.

Teste isolado: `python healbot.py` (cliente aberto, tome dano no jogo).
"""
import time

import presets
import vision


class HealBot:
    def __init__(self, spell_heal: list[dict] | None = None,
                 potion_heal: list[dict] | None = None,
                 mana_potion: dict | None = None):
        self.set_tiers(
            spell_heal if spell_heal is not None else presets.default_spell_heal(),
            potion_heal if potion_heal is not None else presets.default_potion_heal(),
            mana_potion if mana_potion is not None else presets.default_mana_potion(),
        )
        self._last_mana_potion = 0.0

    def set_tiers(self, spell_heal: list[dict], potion_heal: list[dict],
                  mana_potion: dict) -> None:
        """Troca as 3 fontes de cura por inteiro (mesma logica de
        atomicidade de Combat.set_combo)."""
        self._spell_heal = list(spell_heal)
        self._potion_heal = list(potion_heal)
        self._mana_potion = dict(mana_potion) if mana_potion else {}
        self._last_spell_by_name = {t["name"]: 0.0 for t in self._spell_heal}
        self._last_potion_by_name = {t["name"]: 0.0 for t in self._potion_heal}

    def tick(self, frame, send) -> None:
        """Decide cura pra 1 frame. `send(key)` envia a tecla pro cliente."""
        now = time.time()
        hp = vision.hp_percent(frame)
        mana = vision.mana_percent(frame)

        # emergencia primeiro: potion nao depende de mana
        for tier in self._potion_heal:
            if hp < tier["hp_below_pct"] and now - self._last_potion_by_name[tier["name"]] >= tier["cooldown"]:
                send(tier["key"])
                self._last_potion_by_name[tier["name"]] = now
                print(f"[heal] HP {hp:.0f}% -> POTION ({tier['name']})")
                return

        for tier in self._spell_heal:
            if hp < tier["hp_below_pct"] and now - self._last_spell_by_name[tier["name"]] >= tier["cooldown"]:
                send(tier["key"])
                self._last_spell_by_name[tier["name"]] = now
                print(f"[heal] HP {hp:.0f}% -> magia de cura ({tier['name']})")
                return

        mp = self._mana_potion
        if mp and mana < mp["mana_below_pct"] and now - self._last_mana_potion >= mp["cooldown"]:
            send(mp["key"])
            self._last_mana_potion = now
            print(f"[heal] mana {mana:.0f}% -> mana potion")


if __name__ == "__main__":
    from capture import capture
    from inputs import press_key
    from window import find_capture_window, find_window

    hwnd = find_window()                 # cliente: recebe as teclas
    cap_hwnd = find_capture_window()     # projetor do OBS: fonte dos frames
    if not hwnd or not cap_hwnd:
        print("Cliente ou projetor do OBS nao encontrado.")
        raise SystemExit(1)

    bot = HealBot()
    print("Healbot rodando (Ctrl+C para parar)...")
    while True:
        frame = capture(cap_hwnd)
        bot.tick(frame, lambda key: press_key(hwnd, key))
        time.sleep(0.1)  # ~10 checagens/s: mais que suficiente pra reagir
