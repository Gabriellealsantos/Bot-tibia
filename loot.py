# -*- coding: utf-8 -*-
"""
Auto-loot: quando um alvo morre, clica com o botao direito nos 8 SQMs
ao redor do personagem (+ o proprio SQM), onde os corpos caem.

Como detecta a morte? Maquina de estados simples:
  - via frame N:   estava atacando (moldura vermelha na battle list)
  - via frame N+1: nao esta mais atacando -> alguem morreu -> lootear
Isso evita lootear a toa a cada tick.

As coordenadas dos SQMs vem do config.GAME_AREA: pixel central do char
+ tamanho do SQM. Ex.: o tile a esquerda = (player_x - sqm_size, player_y).

Obs: como o servidor e SEU, voce pode facilitar: em canary/tfs da pra
configurar loot direto na bag ao abrir o corpo, ai o clique ja basta.
"""
import time

import config
import vision


class Loot:
    def __init__(self):
        self._was_attacking = False

    def tick(self, frame, send_click) -> None:
        """`send_click(x, y, right)` clica na coordenada da janela."""
        attacking = vision.is_attacking(frame)
        target_died = self._was_attacking and not attacking
        self._was_attacking = attacking

        if not target_died:
            return

        print("[loot] alvo morreu -> abrindo corpos ao redor")
        ga = config.GAME_AREA
        # 9 posicoes: o SQM do char e os 8 vizinhos
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                x = ga["player_x"] + dx * ga["sqm_size"]
                y = ga["player_y"] + dy * ga["sqm_size"]
                send_click(x, y, True)
                time.sleep(config.LOOT_DELAY)


if __name__ == "__main__":
    from capture import capture
    from inputs import click
    from window import find_capture_window, find_window

    hwnd = find_window()                 # cliente: recebe os cliques
    cap_hwnd = find_capture_window()     # projetor do OBS: fonte dos frames
    if not hwnd or not cap_hwnd:
        print("Cliente ou projetor do OBS nao encontrado.")
        raise SystemExit(1)

    bot = Loot()
    print("Loot rodando: mate um monstro que voce esteja atacando (Ctrl+C para parar)...")
    while True:
        frame = capture(cap_hwnd)
        bot.tick(frame, lambda x, y, right: click(hwnd, x, y, right=right))
        time.sleep(0.15)
