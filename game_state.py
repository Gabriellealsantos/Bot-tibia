# -*- coding: utf-8 -*-
"""
Infraestrutura de paralelismo do bot — o "sistema nervoso".

Por que threads? Um jogador de verdade cura ENQUANTO anda e ataca.
Se tudo rodasse num unico loop, um loot demorado (9 cliques com pausa)
seguraria a cura por 2+ segundos = morte. Entao:

  CaptureThread  -> captura frames sem parar e guarda o mais recente
  1 thread por modulo (heal, combate, navegacao) -> cada uma le o
     MESMO frame compartilhado e decide por conta propria
  InputSender    -> fila UNICA com prioridade por onde saem as teclas
     (cura fura a fila; duas threads nunca digitam ao mesmo tempo)

threading (e nao multiprocessing/asyncio) porque o trabalho pesado
(captura via API do Windows e numpy) libera o GIL, e o volume de dados
compartilhado (1 frame) torna processos separados um exagero.
"""
import threading
import time
from queue import Empty, PriorityQueue

import win32api

import config
from capture import capture
from healbot import HealBot
from combat import Combat
from loot import Loot
from cavebot import CaveBot
from inputs import click, press_key
from window import find_window

# prioridades da fila de inputs (menor = mais urgente)
PRIO_HEAL, PRIO_COMBAT, PRIO_NAV = 0, 1, 2
MIN_INPUT_GAP = 0.08  # segundos entre inputs; humano nao digita 2 teclas no mesmo ms


class SharedFrame:
    """Ultimo frame capturado, protegido por lock (varias threads leem)."""

    def __init__(self):
        self._frame = None
        self._lock = threading.Lock()

    def set(self, frame):
        with self._lock:
            self._frame = frame

    def get(self):
        with self._lock:
            return self._frame


class InputSender:
    """Fila unica de saida: garante ordem, prioridade e espacamento."""

    def __init__(self, hwnd: int):
        self._hwnd = hwnd
        self._queue: PriorityQueue = PriorityQueue()
        self._seq = 0  # desempate FIFO p/ mesma prioridade

    def key(self, priority: int, key: str):
        self._seq += 1
        self._queue.put((priority, self._seq, ("key", key)))

    def click(self, priority: int, x: int, y: int, right: bool):
        self._seq += 1
        self._queue.put((priority, self._seq, ("click", x, y, right)))

    def run(self, running: threading.Event):
        while running.is_set():
            try:
                _, _, action = self._queue.get(timeout=0.2)
            except Empty:
                continue
            if action[0] == "key":
                press_key(self._hwnd, action[1])
            else:
                _, x, y, right = action
                click(self._hwnd, x, y, right=right)
            time.sleep(MIN_INPUT_GAP)


class BotRunner:
    """Liga tudo: threads de captura, modulos e envio de inputs.

    `enabled` e lido pela GUI (checkboxes) — cada modulo pode ser
    ligado/desligado em tempo real sem parar o resto.
    `status` e atualizado a cada captura pra GUI mostrar HP/mana/etc.
    """

    def __init__(self):
        self.hwnd = 0          # cliente Tibia: recebe os inputs
        self.capture_hwnd = 0  # projetor do OBS: fonte dos frames
        self.running = threading.Event()
        self.enabled = {"heal": True, "combat": True, "loot": True, "cavebot": True}
        self.status = {"hp": 0.0, "mana": 0.0, "monsters": 0, "attacking": False}
        self._threads: list[threading.Thread] = []

    # ------------------------------------------------------------ start/stop
    def start(self) -> bool:
        self.hwnd = find_window(config.WINDOW_TITLE)
        self.capture_hwnd = find_window(config.CAPTURE_WINDOW_TITLE)
        if not self.hwnd or not self.capture_hwnd:
            return False
        self.running.set()
        self._shared = SharedFrame()
        self._sender = InputSender(self.hwnd)
        self._heal, self._combat = HealBot(), Combat()
        self._loot, self._cave = Loot(), CaveBot()

        targets = [
            self._capture_loop,
            self._sender_loop,
            self._heal_loop,
            self._combat_loop,
            self._nav_loop,
            self._panic_key_loop,
        ]
        self._threads = [threading.Thread(target=t, daemon=True) for t in targets]
        for t in self._threads:
            t.start()
        return True

    def stop(self):
        self.running.clear()

    # ---------------------------------------------------------------- loops
    def _capture_loop(self):
        import vision
        while self.running.is_set():
            try:
                frame = capture(self.capture_hwnd)
            except Exception:
                self.stop()  # janela fechou
                break
            self._shared.set(frame)
            self.status.update(
                hp=vision.hp_percent(frame),
                mana=vision.mana_percent(frame),
                monsters=vision.monster_count(frame),
                attacking=vision.is_attacking(frame),
            )
            time.sleep(0.066)  # ~15 fps

    def _sender_loop(self):
        self._sender.run(self.running)

    def _module_loop(self, name: str, interval: float, do_tick):
        """Esqueleto comum: espera frame, tica se o modulo esta ligado."""
        while self.running.is_set():
            frame = self._shared.get()
            if frame is not None and self.enabled[name]:
                do_tick(frame)
            time.sleep(interval)

    def _heal_loop(self):
        self._module_loop("heal", 0.1,
            lambda f: self._heal.tick(f, lambda k: self._sender.key(PRIO_HEAL, k)))

    def _combat_loop(self):
        self._module_loop("combat", 0.15,
            lambda f: self._combat.tick(f, lambda k: self._sender.key(PRIO_COMBAT, k)))

    def _nav_loop(self):
        def tick(frame):
            if self.enabled["loot"]:
                self._loot.tick(frame,
                    lambda x, y, r: self._sender.click(PRIO_NAV, x, y, r))
            if self.enabled["cavebot"]:
                self._cave.tick(frame,
                    lambda x, y, r: self._sender.click(PRIO_NAV, x, y, r))
        # loot/cavebot dividem a thread: nenhum dos dois e urgente
        while self.running.is_set():
            frame = self._shared.get()
            if frame is not None:
                tick(frame)
            time.sleep(0.2)

    def _panic_key_loop(self):
        """Tecla de emergencia global (config.PAUSE_KEY) para o bot inteiro."""
        from inputs import VK
        vk = VK.get(config.PAUSE_KEY.upper(), 0)
        while self.running.is_set():
            if vk and win32api.GetAsyncKeyState(vk) & 0x8000:
                print(f"[panic] {config.PAUSE_KEY} pressionado -> parando o bot")
                self.stop()
                break
            time.sleep(0.05)
