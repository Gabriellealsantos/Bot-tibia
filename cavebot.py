# -*- coding: utf-8 -*-
"""
Cavebot v1: anda pela hunt clicando no minimapa (map-click do Tibia).

Como funciona:
  GRAVAR ROTA:  `python cavebot.py record`
     Voce joga normalmente; a cada F11 o bot grava um waypoint = um
     ponto DO MINIMAPA correspondente a onde voce quer clicar.
     (clique no minimapa da janela de calibracao que abre)
     Os waypoints vao para waypoints.json.

  REPRODUZIR:   `python cavebot.py`
     O bot clica no waypoint atual do minimapa, espera WAYPOINT_WAIT
     segundos (tempo de andar ate la) e vai pro proximo, em loop.
     So anda quando a battle list esta vazia — matar vem primeiro.

v1 usa espera por tempo (simples e funciona). A v2 confirmaria a
chegada comparando o minimapa com template matching (cv2.matchTemplate)
— fazemos depois que a v1 estiver rodando.
"""
import json
import os
import sys
import time

import config
import vision


def load_waypoints(path: str) -> list[list[int]]:
    """Le a rota do disco; devolve [] se o arquivo nao existir."""
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_waypoints(path: str, waypoints: list[list[int]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(waypoints, f)


class CaveBot:
    def __init__(self, waypoints_file: str | None = None, wait: float | None = None):
        self.waypoints_file = waypoints_file or config.WAYPOINTS_FILE
        self.wait = wait if wait is not None else config.WAYPOINT_WAIT
        self.waypoints: list[list[int]] = []
        self.index = 0
        self._walking_since = 0.0
        self.reload()

    def reload(self) -> None:
        """Recarrega a rota do arquivo atual (chamado pela GUI ao editar
        waypoints ou trocar de arquivo)."""
        self.waypoints = load_waypoints(self.waypoints_file)
        self.index = 0
        self._walking_since = 0.0

    def tick(self, frame, send_click) -> None:
        if not self.waypoints:
            return
        # combate tem prioridade: com monstro na tela, o cavebot para
        if vision.monster_count(frame) > 0:
            self._walking_since = 0.0
            return
        now = time.time()
        if self._walking_since and now - self._walking_since < self.wait:
            return  # ainda andando pro waypoint atual

        x, y = self.waypoints[self.index]
        send_click(x, y, False)  # clique esquerdo no minimapa = andar ate la
        self._walking_since = now
        print(f"[cavebot] waypoint {self.index + 1}/{len(self.waypoints)} -> clique ({x}, {y})")
        self.index = (self.index + 1) % len(self.waypoints)


def record(path: str | None = None) -> None:
    """Gravador de rota: clique nos pontos do minimapa na ordem da rota."""
    import cv2

    from capture import capture
    from window import find_window

    path = path or config.WAYPOINTS_FILE

    # janela de captura e minimapa vem das settings (o que o usuario
    # escolheu/calibrou na GUI) — nada de titulo/regiao hardcoded.
    capture_title = config.CAPTURE_WINDOW_TITLE
    mm = config.MINIMAP
    try:
        from presets import PresetStore
        settings = PresetStore().get_settings()
        capture_title = settings.get("capture_window_title", capture_title)
        mm = settings.get("calibration", {}).get("minimap", mm)
    except Exception:
        pass

    hwnd = find_window(capture_title)
    if not hwnd:
        print(f"Janela de captura '{capture_title}' nao encontrada.")
        return

    waypoints: list[list[int]] = []

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            # converte da janela de preview (so minimapa) p/ coords da janela toda
            wx, wy = mm["x"] + x, mm["y"] + y
            waypoints.append([wx, wy])
            print(f"waypoint {len(waypoints)}: ({wx}, {wy})")

    print("Clique nos pontos da rota NO MINIMAPA (na ordem). Q para salvar e sair.")
    cv2.namedWindow("minimapa")
    cv2.setMouseCallback("minimapa", on_mouse)
    while True:
        frame = capture(hwnd)
        region = frame[mm["y"]:mm["y"] + mm["h"], mm["x"]:mm["x"] + mm["w"]]
        cv2.imshow("minimapa", cv2.resize(region, None, fx=3, fy=3,
                                          interpolation=cv2.INTER_NEAREST))
        if (cv2.waitKey(100) & 0xFF) == ord("q"):
            break
    cv2.destroyAllWindows()

    save_waypoints(path, waypoints)
    print(f"{len(waypoints)} waypoints salvos em {path}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "record":
        record(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        from capture import capture
        from inputs import click
        from window import find_capture_window, find_window

        hwnd = find_window()                 # cliente: recebe os cliques
        cap_hwnd = find_capture_window()     # projetor do OBS: fonte dos frames
        if not hwnd or not cap_hwnd:
            print("Cliente ou projetor do OBS nao encontrado.")
            raise SystemExit(1)

        bot = CaveBot()
        if not bot.waypoints:
            print("Nenhuma rota gravada. Rode: python cavebot.py record")
            raise SystemExit(1)
        print(f"Cavebot com {len(bot.waypoints)} waypoints (Ctrl+C para parar)...")
        while True:
            frame = capture(cap_hwnd)
            bot.tick(frame, lambda x, y, right: click(hwnd, x, y, right=right))
            time.sleep(0.2)
