# -*- coding: utf-8 -*-
"""
Combate do Elite Knight: targeting + rotacao de magias de area.

Como um EK de verdade joga:
  1. Tem monstro e nao estou atacando? -> SPACE (attack next do Tibia).
  2. Estou cercado? -> solta a magia de area MAIS FORTE que:
       (a) tem monstros suficientes pra valer a mana,
       (b) tem mana sobrando (sem roubar a mana da cura!),
       (c) ja saiu do cooldown dela E do exhaust global de ataque.
A tabela de magias esta em config.EK_SPELLS, da mais forte pra mais
fraca — a primeira que passar nos 3 testes e usada.

Teste isolado: `python combat.py` perto de monstros.
"""
import time

import config
import vision


class Combat:
    def __init__(self):
        self._last_attack = 0.0
        self._last_global = 0.0
        self._last_cast = {spell["name"]: 0.0 for spell in config.EK_SPELLS}

    def tick(self, frame, send) -> None:
        now = time.time()
        monsters = vision.monster_count(frame)
        if monsters == 0:
            return

        # 1) targeting: garante que sempre ha um alvo selecionado
        if not vision.is_attacking(frame) and now - self._last_attack >= config.ATTACK_COOLDOWN:
            send(config.ATTACK_KEY)
            self._last_attack = now
            print(f"[combat] {monsters} monstro(s) -> attack next")
            return  # espera o proximo frame confirmar o alvo

        # 2) rotacao de area: mais forte primeiro
        if now - self._last_global < config.SPELL_GLOBAL_COOLDOWN:
            return
        mana = vision.mana_percent(frame)
        for spell in config.EK_SPELLS:
            if monsters < spell["min_monsters"]:
                continue
            if mana < spell["mana_pct"]:
                continue
            if now - self._last_cast[spell["name"]] < spell["cooldown"]:
                continue
            send(spell["key"])
            self._last_cast[spell["name"]] = now
            self._last_global = now
            print(f"[combat] {monsters} monstros, mana {mana:.0f}% -> {spell['name']}")
            return


if __name__ == "__main__":
    from capture import capture
    from inputs import press_key
    from window import find_capture_window, find_window

    hwnd = find_window()                 # cliente: recebe as teclas
    cap_hwnd = find_capture_window()     # projetor do OBS: fonte dos frames
    if not hwnd or not cap_hwnd:
        print("Cliente ou projetor do OBS nao encontrado.")
        raise SystemExit(1)

    bot = Combat()
    print("Combate rodando (Ctrl+C para parar)...")
    while True:
        frame = capture(cap_hwnd)
        bot.tick(frame, lambda key: press_key(hwnd, key))
        time.sleep(0.15)
