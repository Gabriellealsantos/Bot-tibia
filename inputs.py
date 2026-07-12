# -*- coding: utf-8 -*-
"""
Envia teclas e cliques DIRETO pra janela do cliente, sem precisar de foco.

Por que PostMessage e nao pyautogui/pynput?
- pyautogui move o mouse REAL e digita no que estiver em foco. Se voce
  estiver usando o PC pra outra coisa, o bot digitaria no lugar errado —
  e nao funciona com a janela invisivel.
- PostMessage coloca a mensagem (ex: WM_KEYDOWN) direto na fila da janela
  alvo, pelo HWND. O cliente processa como se fosse tecla de verdade,
  mesmo sem foco, minimizado ou com opacidade 1.

Limitacao: clientes que leem teclado por DirectInput/RawInput ignoram
PostMessage. OTClient e derivados normalmente aceitam. Teste com o seu!
"""
import time

import win32api
import win32con
import win32gui

# Teclas mais usadas em hotkey de OT
VK = {
    "F1": win32con.VK_F1, "F2": win32con.VK_F2, "F3": win32con.VK_F3,
    "F4": win32con.VK_F4, "F5": win32con.VK_F5, "F6": win32con.VK_F6,
    "F7": win32con.VK_F7, "F8": win32con.VK_F8, "F9": win32con.VK_F9,
    "F10": win32con.VK_F10, "F11": win32con.VK_F11, "F12": win32con.VK_F12,
    "SPACE": win32con.VK_SPACE, "ESC": win32con.VK_ESCAPE,
    "UP": win32con.VK_UP, "DOWN": win32con.VK_DOWN,
    "LEFT": win32con.VK_LEFT, "RIGHT": win32con.VK_RIGHT,
}


def _lparam(vk: int, keyup: bool = False) -> int:
    # lParam carrega o scan code fisico da tecla; alguns clientes conferem.
    scan = win32api.MapVirtualKey(vk, 0)
    lp = 1 | (scan << 16)
    if keyup:
        lp |= (1 << 30) | (1 << 31)
    return lp


def press_key(hwnd: int, key: str, hold: float = 0.05) -> None:
    """Pressiona e solta uma tecla na janela alvo. Ex: press_key(hwnd, 'F1')."""
    vk = VK[key.upper()] if key.upper() in VK else ord(key.upper())
    win32api.PostMessage(hwnd, win32con.WM_KEYDOWN, vk, _lparam(vk))
    time.sleep(hold)
    win32api.PostMessage(hwnd, win32con.WM_KEYUP, vk, _lparam(vk, keyup=True))


def click(hwnd: int, x: int, y: int, right: bool = False, hold: float = 0.05) -> None:
    """Clica na coordenada (x, y) DA JANELA (mesma referencia da captura)."""
    lp = win32api.MAKELONG(x, y)
    down = win32con.WM_RBUTTONDOWN if right else win32con.WM_LBUTTONDOWN
    up = win32con.WM_RBUTTONUP if right else win32con.WM_LBUTTONUP
    flag = win32con.MK_RBUTTON if right else win32con.MK_LBUTTON
    win32api.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lp)
    win32api.PostMessage(hwnd, down, flag, lp)
    time.sleep(hold)
    win32api.PostMessage(hwnd, up, 0, lp)


if __name__ == "__main__":
    from window import find_window

    hwnd = find_window()
    if hwnd:
        print("Enviando F1 pra janela em 2s... (coloque algo no F1 pra testar)")
        time.sleep(2)
        press_key(hwnd, "F1")
        print("Enviado. Confira no cliente se a hotkey disparou.")
    else:
        print("Cliente nao encontrado.")
