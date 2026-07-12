# -*- coding: utf-8 -*-
"""
Captura frames da janela do cliente — mesmo invisivel ou coberta.

Por que PrintWindow e nao screenshot da tela (mss/pyautogui/OBS)?
- Screenshot da tela captura o que esta VISIVEL no monitor. Com a
  opacidade em 1, a janela nao aparece na tela -> a captura viria vazia.
- PrintWindow pede pro proprio Windows renderizar o conteudo da janela
  direto num buffer nosso, ignorando opacidade, foco e sobreposicao.
  Assim o bot roda com o cliente escondido enquanto voce usa o PC.

O frame sai como array numpy (altura x largura x 3) em BGR — o formato
padrao do OpenCV, pronto pra analise de pixels.
"""
import ctypes

import numpy as np
import win32gui
import win32ui

# PW_CLIENTONLY: so a area do jogo, sem borda/titulo da janela.
# PW_RENDERFULLCONTENT: obrigatorio p/ janelas renderizadas por GPU (DirectX/OpenGL).
PW_CLIENTONLY = 0x00000001
PW_RENDERFULLCONTENT = 0x00000002


def capture(hwnd: int) -> np.ndarray:
    """Captura a area cliente da janela e retorna um frame BGR (numpy)."""
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    width, height = right - left, bottom - top
    if width == 0 or height == 0:
        raise RuntimeError("Janela minimizada ou sem area cliente.")

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    save_dc = mfc_dc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(mfc_dc, width, height)
    save_dc.SelectObject(bmp)

    ok = ctypes.windll.user32.PrintWindow(
        hwnd, save_dc.GetSafeHdc(), PW_CLIENTONLY | PW_RENDERFULLCONTENT
    )

    raw = bmp.GetBitmapBits(True)  # BGRA
    frame = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 4)[:, :, :3]
    frame = frame.copy()  # frombuffer e read-only; copia libera o bitmap

    win32gui.DeleteObject(bmp.GetHandle())
    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwnd_dc)

    if not ok:
        raise RuntimeError("PrintWindow falhou para esta janela.")
    return frame


def pixel(frame: np.ndarray, x: int, y: int) -> tuple[int, int, int]:
    """Cor (B, G, R) do pixel na posicao (x, y) do frame."""
    b, g, r = frame[y, x]
    return int(b), int(g), int(r)
