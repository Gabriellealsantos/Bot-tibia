# -*- coding: utf-8 -*-
"""
Percepcao: transforma pixels em ESTADO DE JOGO (numeros que o bot entende).

Tecnica usada: contagem de pixels por cor com tolerancia. A barra de HP
e uma linha horizontal; contamos quantos pixels dela ainda tem a cor
"cheia" -> isso E o percentual. Simples, rapido (numpy vetorizado) e
robusto — nao precisa de OCR nem machine learning.

Para a battle list usamos a mesma ideia: cada criatura na lista tem uma
barrinha de vida; procuramos essas barrinhas dentro da regiao calibrada
e contamos quantas achamos = quantos monstros na tela.
"""
import numpy as np

import config


def _bar_percent(frame: np.ndarray, bar: dict) -> float:
    """Percentual de uma barra horizontal (HP ou mana), 0.0 a 100.0."""
    row = frame[bar["y"], bar["x_start"]:bar["x_end"]].astype(np.int16)
    color = np.array(bar["color_bgr"], dtype=np.int16)
    # pixel "cheio" = todos os 3 canais perto da cor calibrada
    filled = np.all(np.abs(row - color) <= bar["tolerance"], axis=1)
    total = len(filled)
    return 100.0 * int(filled.sum()) / total if total else 0.0


def hp_percent(frame: np.ndarray) -> float:
    return _bar_percent(frame, config.HP_BAR)


def mana_percent(frame: np.ndarray) -> float:
    return _bar_percent(frame, config.MANA_BAR)


# Cores possiveis da barrinha de vida das criaturas na battle list
# (verde cheio, amarelo, laranja, vermelho conforme a vida delas), em BGR.
_CREATURE_BAR_COLORS = np.array([
    (0, 188, 0),     # verde
    (0, 188, 188),   # amarelo
    (0, 128, 240),   # laranja
    (0, 0, 240),     # vermelho
], dtype=np.int16)
_CREATURE_TOL = 60


def monster_count(frame: np.ndarray) -> int:
    """Quantidade de criaturas na battle list.

    Varre a regiao da battle list linha por linha procurando fileiras
    horizontais com muitos pixels de "cor de barrinha de vida". Cada
    grupo de linhas contiguas = 1 criatura.
    """
    bl = config.BATTLE_LIST
    region = frame[bl["y"]:bl["y"] + bl["h"], bl["x"]:bl["x"] + bl["w"]].astype(np.int16)
    if region.size == 0:
        return 0

    # match[y, x] = True se o pixel parece pedaco de barrinha de vida
    match = np.zeros(region.shape[:2], dtype=bool)
    for color in _CREATURE_BAR_COLORS:
        match |= np.all(np.abs(region - color) <= _CREATURE_TOL, axis=2)

    # linha com 10+ pixels de barrinha = linha que cruza uma barra de vida
    bar_rows = match.sum(axis=1) >= 10

    # conta blocos contiguos de linhas True (bordas de subida)
    count = int(np.sum(bar_rows[1:] & ~bar_rows[:-1])) + int(bar_rows[0])
    return count


def is_attacking(frame: np.ndarray) -> bool:
    """True se ha um alvo marcado (moldura vermelha na battle list).

    A moldura de "atacando" e um retangulo vermelho vivo em volta da
    entrada. Procuramos pixels desse vermelho na coluna esquerda da
    battle list (onde fica a borda da moldura).
    """
    bl = config.BATTLE_LIST
    col = frame[bl["y"]:bl["y"] + bl["h"], bl["x"]:bl["x"] + 4].astype(np.int16)
    red = np.array((0, 0, 255), dtype=np.int16)
    hits = np.all(np.abs(col - red) <= 60, axis=2)
    return int(hits.sum()) >= 8


if __name__ == "__main__":
    from capture import capture
    from window import find_capture_window

    hwnd = find_capture_window()
    if not hwnd:
        print("Projetor do OBS nao encontrado.")
    else:
        frame = capture(hwnd)
        print(f"HP:   {hp_percent(frame):5.1f}%")
        print(f"Mana: {mana_percent(frame):5.1f}%")
        print(f"Monstros na battle list: {monster_count(frame)}")
        print(f"Atacando: {is_attacking(frame)}")
        print("\nSe os valores estiverem errados, recalibre o config.py com calibrate.py")
