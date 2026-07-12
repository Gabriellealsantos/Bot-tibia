# -*- coding: utf-8 -*-
"""
Ponto de entrada do bot: `python main.py` abre a interface.

Fluxo de uso:
  1. Abra o cliente do jogo e logue com o char.
  2. `python calibrate.py`  -> descubra coordenadas/cores e preencha config.py
  3. `python cavebot.py record` -> grave a rota da hunt (opcional)
  4. `python main.py`       -> interface: iniciar bot e ligar os modulos
  5. (opcional) `python window.py 1` -> deixa o cliente invisivel
     `python window.py 255` traz de volta.

Cada modulo tambem roda sozinho pra teste: python healbot.py, etc.
"""
from gui import main

if __name__ == "__main__":
    main()
