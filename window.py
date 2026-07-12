# -*- coding: utf-8 -*-
"""
Localiza a janela do cliente e controla a opacidade.

A opacidade e por janela (WS_EX_LAYERED + SetLayeredWindowAttributes).
Com opacidade 1 a janela fica invisivel na tela, mas o conteudo dela
continua sendo renderizado — e por isso que o PrintWindow (capture.py)
consegue "enxergar" o jogo mesmo com a janela escondida.
"""
import ctypes

import win32gui

from config import CAPTURE_WINDOW_TITLE, WINDOW_TITLE

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
LWA_ALPHA = 0x00000002


def enable_dpi_awareness() -> None:
    """Torna o processo ciente de DPI ANTES de qualquer captura.

    Sem isso, num monitor com zoom (ex.: notebook a 125%) o Windows MENTE
    o tamanho das janelas (reporta 1536 quando o real e 1920) e o
    PrintWindow captura so um pedaco — barras/battle list ficam fora do
    frame. Com DPI awareness, os tamanhos sao os pixels REAIS e a captura
    funciona igual em qualquer PC/tela. Chamar 1x, logo no inicio.
    """
    try:
        # PER_MONITOR_AWARE_V2 (-4) — precisa de c_void_p, senao nao aplica.
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()  # system-aware (fallback antigo)
            except Exception:
                pass


def find_window(title: str = WINDOW_TITLE) -> int:
    """Retorna o HWND (handle) da janela do cliente, ou 0 se nao achou.

    O HWND e o "endereco" da janela no Windows: todas as APIs
    (captura, envio de teclas, opacidade) trabalham em cima dele.
    """
    def _enum(hwnd, result):
        if title.lower() in win32gui.GetWindowText(hwnd).lower():
            result.append(hwnd)

    matches: list[int] = []
    win32gui.EnumWindows(_enum, matches)
    return matches[0] if matches else 0


def list_windows() -> list[str]:
    """Titulos de todas as janelas visiveis (com titulo), para o usuario
    escolher na GUI qual e o cliente e qual e o projetor do OBS — em vez
    de deixar os titulos hardcoded no config."""
    def _enum(hwnd, acc):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title.strip():
                acc.append(title)

    titles: list[str] = []
    win32gui.EnumWindows(_enum, titles)
    # sem duplicatas, preservando ordem
    return list(dict.fromkeys(titles))


def find_capture_window() -> int:
    """HWND da janela que o bot ENXERGA (projetor do OBS), ou 0.

    Captura e input usam janelas diferentes: os frames vem do projetor
    do OBS (o cliente pode bloquear/renderizar preto no PrintWindow),
    mas teclas e cliques continuam indo pro cliente (find_window).
    """
    return find_window(CAPTURE_WINDOW_TITLE)


def set_opacity(hwnd: int, opacity: int) -> None:
    """opacity: 0 (invisivel) a 255 (opaco)."""
    ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_LAYERED)
    ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0, opacity, LWA_ALPHA)


if __name__ == "__main__":
    import sys

    hwnd = find_window()
    if not hwnd:
        print(f"Janela '{WINDOW_TITLE}' nao encontrada. O cliente esta aberto?")
        sys.exit(1)

    value = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    set_opacity(hwnd, value)
    print(f"Opacidade da janela {hwnd} ajustada para {value}.")
