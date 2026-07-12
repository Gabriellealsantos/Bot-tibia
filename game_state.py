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
from presets import PresetStore
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
        # "combat" virou dois toggles independentes: attack (targeting) e
        # spell (combo de magias) — dá pra ligar so um dos dois.
        self.enabled = {"heal": True, "attack": True, "spell": True,
                        "loot": True, "cavebot": True}
        self.status = {"hp": 0.0, "mana": 0.0, "monsters": 0, "attacking": False}
        self.presets = PresetStore()  # carrega/semeia presets.json
        self._heal: HealBot | None = None
        self._combat: Combat | None = None
        self._loot: Loot | None = None
        self._cave: CaveBot | None = None
        self._threads: list[threading.Thread] = []

    # ------------------------------------------------------------ start/stop
    def start(self) -> bool:
        settings = self.presets.get_settings()
        self.hwnd = find_window(settings["client_window_title"])
        self.capture_hwnd = find_window(settings["capture_window_title"])
        if not self.hwnd:
            print(f"[start] janela do CLIENTE '{settings['client_window_title']}' "
                  "nao encontrada — escolha a janela certa na aba Geral.")
            return False
        if not self.capture_hwnd:
            print(f"[start] janela de CAPTURA '{settings['capture_window_title']}' "
                  "nao encontrada — escolha a janela certa na aba Geral.")
            return False
        self.running.set()
        self._shared = SharedFrame()
        self._sender = InputSender(self.hwnd)
        # aplica a calibracao do usuario (regioes de pixel) antes de ler frames
        import vision
        calibration = settings.get("calibration", {})
        vision.set_calibration(calibration)
        preset = self.presets.get()
        self._heal = HealBot(preset["healing"]["spell_heal"],
                              preset["healing"]["potion_heal"],
                              preset["healing"]["mana_potion"])
        self._combat = Combat(preset["combat"]["combo"])
        self._loot = Loot(calibration.get("game_area"),
                          radius=settings.get("loot_radius"),
                          delay=settings.get("loot_delay"),
                          settle=settings.get("loot_settle"))
        self._cave = CaveBot(settings["waypoints_file"], settings["waypoint_wait"])

        targets = [
            self._capture_loop,
            self._sender_loop,
            self._heal_loop,
            self._combat_loop,
            self._nav_loop,
            self._hotkey_loop,
        ]
        self._threads = [threading.Thread(target=t, daemon=True) for t in targets]
        for t in self._threads:
            t.start()
        return True

    def stop(self):
        self.running.clear()

    def apply_preset(self, name: str | None = None) -> None:
        """Chamado pela GUI (thread principal do Tk) apos editar ou trocar
        o preset ativo. Troca os objetos de combo/cura por inteiro nas
        instancias vivas de Combat/HealBot — mesma logica de atomicidade
        do SharedFrame, sem precisar de lock. No-op seguro se o bot ainda
        nao foi iniciado."""
        if name:
            self.presets.set_active(name)
        preset = self.presets.get()
        if self._combat is not None:
            self._combat.set_combo(preset["combat"]["combo"])
        if self._heal is not None:
            self._heal.set_tiers(preset["healing"]["spell_heal"],
                                  preset["healing"]["potion_heal"],
                                  preset["healing"]["mana_potion"])

    def apply_settings(self) -> None:
        """Empurra as settings globais (arquivo de rota, espera) para o
        cavebot vivo. As hotkeys sao lidas ao vivo pelo _hotkey_loop, entao
        nao precisam ser empurradas aqui. No-op seguro se o bot esta parado."""
        settings = self.presets.get_settings()
        if self._cave is not None:
            self._cave.wait = settings["waypoint_wait"]
            if self._cave.waypoints_file != settings["waypoints_file"]:
                self._cave.waypoints_file = settings["waypoints_file"]
                self._cave.reload()
        if self._loot is not None:
            self._loot.set_config(radius=settings.get("loot_radius"),
                                  delay=settings.get("loot_delay"),
                                  settle=settings.get("loot_settle"))

    def reload_cavebot(self) -> None:
        """Recarrega a rota do disco na instancia viva (GUI editou/gravou)."""
        if self._cave is not None:
            self._cave.reload()

    def apply_calibration(self) -> None:
        """Empurra a calibracao das regioes de pixel (barras, battle list,
        game area) para a percepcao viva — a GUI chama isso apos calibrar,
        sem precisar reiniciar o bot."""
        import vision
        cal = self.presets.get_settings().get("calibration", {})
        vision.set_calibration(cal)
        if self._loot is not None and cal.get("game_area"):
            self._loot.game_area = cal["game_area"]

    def cave_progress(self) -> tuple[int, int]:
        """(waypoint atual, total) para a GUI mostrar o progresso ao vivo."""
        if self._cave is None:
            return (0, 0)
        return (self._cave.index, len(self._cave.waypoints))

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
        # attack e spell tem toggles separados; a thread roda se qualquer um
        # estiver ligado e o Combat.tick recebe os dois flags.
        while self.running.is_set():
            frame = self._shared.get()
            if frame is not None and (self.enabled["attack"] or self.enabled["spell"]):
                self._combat.tick(
                    frame,
                    lambda k: self._sender.key(PRIO_COMBAT, k),
                    do_attack=self.enabled["attack"],
                    do_spell=self.enabled["spell"],
                )
            time.sleep(0.15)

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

    def _hotkey_loop(self):
        """Hotkeys globais lidas com o JOGO em foco (GetAsyncKeyState):
        panico para tudo; as outras alternam attack/spell/cavebot. Deteccao
        por borda de subida (so alterna 1x por toque, nao a cada frame).
        As teclas vem das settings, entao mudar na GUI vale na hora."""
        from inputs import VK
        prev: dict[str, bool] = {}
        toggles = {
            "hotkey_toggle_attack": "attack",
            "hotkey_toggle_spell": "spell",
            "hotkey_toggle_cavebot": "cavebot",
        }
        while self.running.is_set():
            settings = self.presets.get_settings()

            panic_key = settings.get("hotkey_panic", config.PAUSE_KEY)
            vk = VK.get(panic_key.upper(), 0)
            if vk and win32api.GetAsyncKeyState(vk) & 0x8000:
                print(f"[panic] {panic_key} pressionado -> parando o bot")
                self.stop()
                break

            for setting_key, flag in toggles.items():
                keyname = settings.get(setting_key, "")
                vk = VK.get(keyname.upper(), 0)
                down = bool(vk and win32api.GetAsyncKeyState(vk) & 0x8000)
                if down and not prev.get(flag, False):
                    self.enabled[flag] = not self.enabled[flag]
                    estado = "ligado" if self.enabled[flag] else "desligado"
                    print(f"[hotkey] {keyname} -> {flag} {estado}")
                prev[flag] = down

            time.sleep(0.03)
