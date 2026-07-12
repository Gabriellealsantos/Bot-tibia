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

import config
import vision


class HealBot:
    def __init__(self):
        self._last_spell = 0.0
        self._last_potion = 0.0
        self._last_mana_potion = 0.0

    def tick(self, frame, send) -> None:
        """Decide cura pra 1 frame. `send(key)` envia a tecla pro cliente."""
        now = time.time()
        heal = config.HEAL
        hp = vision.hp_percent(frame)
        mana = vision.mana_percent(frame)

        # emergencia primeiro: potion nao depende de mana
        if hp < heal["potion_below_pct"] and now - self._last_potion >= heal["potion_cooldown"]:
            send(heal["potion_key"])
            self._last_potion = now
            print(f"[heal] HP {hp:.0f}% -> POTION")
            return

        if hp < heal["spell_below_pct"] and now - self._last_spell >= heal["spell_cooldown"]:
            send(heal["spell_key"])
            self._last_spell = now
            print(f"[heal] HP {hp:.0f}% -> magia de cura")
            return

        if mana < heal["mana_below_pct"] and now - self._last_mana_potion >= heal["potion_cooldown"]:
            send(heal["mana_potion_key"])
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
