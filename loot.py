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
    def __init__(self, game_area: dict | None = None, radius: int | None = None,
                 delay: float | None = None, settle: float | None = None):
        self._fighting = False
        self.game_area = game_area or config.GAME_AREA
        self.radius = config.LOOT_RADIUS if radius is None else radius
        self.delay = config.LOOT_DELAY if delay is None else delay
        self.settle = config.LOOT_SETTLE if settle is None else settle

    def set_config(self, radius=None, delay=None, settle=None, game_area=None) -> None:
        """Atualiza os parametros ao vivo (a GUI chama via apply_settings)."""
        if radius is not None:
            self.radius = radius
        if delay is not None:
            self.delay = delay
        if settle is not None:
            self.settle = settle
        if game_area:
            self.game_area = game_area

    def tick(self, frame, send_click) -> None:
        """`send_click(x, y, right)` clica na coordenada da janela.

        Gatilho robusto: marca que ESTAVA numa luta (viu a moldura de
        ataque) e so lóota quando a battle list ZERA — assim nao lóota por
        causa de um flicker no meio do combate e cobre AoE (mata varios de
        uma vez). Espera o char PARAR (settle) antes de clicar."""
        attacking = vision.is_attacking(frame)
        monsters = vision.monster_count(frame)

        if attacking:
            self._fighting = True
        if not (self._fighting and monsters == 0):
            return
        self._fighting = False

        print("[loot] fim da luta -> abrindo corpos ao redor")
        if self.settle > 0:
            time.sleep(self.settle)  # deixa o char parar antes de clicar
        ga = self.game_area
        # varre um quadrado (2*raio+1) de SQMs centrado no personagem
        for dy in range(-self.radius, self.radius + 1):
            for dx in range(-self.radius, self.radius + 1):
                x = ga["player_x"] + dx * ga["sqm_size"]
                y = ga["player_y"] + dy * ga["sqm_size"]
                send_click(x, y, True)
                time.sleep(self.delay)


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
