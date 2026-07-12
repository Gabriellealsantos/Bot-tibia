# -*- coding: utf-8 -*-
"""
Ferramenta de calibracao — rode ANTES de tudo: `python calibrate.py`

Abre uma janela mostrando o que o bot enxerga do cliente (mesmo com
opacidade 1!). Ai voce descobre as coordenadas e cores pro config.py:

  - mover o mouse  -> mostra (x, y) e cor BGR do pixel sob o cursor
  - clique esquerdo -> imprime no console a linha pronta pra copiar
  - tecla S         -> salva screenshot.png pra inspecionar com calma
  - tecla Q/ESC     -> sai

Dica de calibracao das barras: passe o mouse no COMECO da barra de HP
(anote x_start), no FIM (x_end), no meio da altura (y) e clique em cima
da parte vermelha pra pegar a cor BGR cheia. Repita pra mana.
"""
import cv2

import config
from capture import capture
from window import find_window

_last = {"x": 0, "y": 0}


def _on_mouse(event, x, y, flags, param):
    _last["x"], _last["y"] = x, y
    if event == cv2.EVENT_LBUTTONDOWN:
        frame = param["frame"]
        b, g, r = frame[y, x]
        print(f'x={x}, y={y}, cor BGR=({b}, {g}, {r})')


def main() -> None:
    # Calibra sobre o PROJETOR do OBS — a mesma fonte de frames do bot.
    hwnd = find_window(config.CAPTURE_WINDOW_TITLE)
    if not hwnd:
        print(f"Janela '{config.CAPTURE_WINDOW_TITLE}' nao encontrada. "
              "Abra o projetor no OBS (botao direito na fonte > Projetor de fontes).")
        return

    print(__doc__)
    state = {"frame": capture(hwnd)}
    cv2.namedWindow("calibrate")
    cv2.setMouseCallback("calibrate", _on_mouse, state)

    while True:
        state["frame"] = capture(hwnd)
        view = state["frame"].copy()
        x, y = _last["x"], _last["y"]
        if 0 <= y < view.shape[0] and 0 <= x < view.shape[1]:
            b, g, r = view[y, x]
            cv2.putText(view, f"({x},{y}) BGR=({b},{g},{r})", (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.imshow("calibrate", view)

        key = cv2.waitKey(66) & 0xFF  # ~15 fps
        if key in (ord("q"), 27):
            break
        if key == ord("s"):
            cv2.imwrite("screenshot.png", state["frame"])
            print("screenshot.png salvo.")

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
