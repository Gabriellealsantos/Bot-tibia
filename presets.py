# -*- coding: utf-8 -*-
"""
Presets: combos de combate e camadas de cura configuraveis pela GUI,
persistidos em disco (presets.json, mesmo padrao de waypoints.json).

Por que isso existe: config.py e um modulo Python estatico — mudar uma
magia, tecla ou limiar exige editar codigo e reiniciar. Aqui a mesma
ideia (lista ordenada, primeira entrada que satisfaz as condicoes
vence — igual combat.py/healbot.py ja fazem) vira dado editavel em
runtime pela GUI, com varios presets nomeados (ex.: "Hunt1", "Hunt2").

Prioridade = posicao na lista. Nao ha campo numerico de prioridade
separado: reordenar e mover a entrada na lista.
"""
import copy
import json
import os

import config

PRESETS_FILE = "presets.json"
DEFAULT_PRESET_NAME = "Default"


def default_combo() -> list[dict]:
    return [
        {
            "name": spell["name"],
            "key": spell["key"],
            "min_monsters": spell["min_monsters"],
            "mana_pct": spell["mana_pct"],
            "cooldown": spell["cooldown"],
        }
        for spell in config.EK_SPELLS
    ]


def default_spell_heal() -> list[dict]:
    heal = config.HEAL
    return [{
        "name": "cura",
        "key": heal["spell_key"],
        "hp_below_pct": heal["spell_below_pct"],
        "cooldown": heal["spell_cooldown"],
    }]


def default_potion_heal() -> list[dict]:
    heal = config.HEAL
    return [{
        "name": "potion",
        "key": heal["potion_key"],
        "hp_below_pct": heal["potion_below_pct"],
        "cooldown": heal["potion_cooldown"],
    }]


def default_mana_potion() -> dict:
    heal = config.HEAL
    return {
        "key": heal["mana_potion_key"],
        "mana_below_pct": heal["mana_below_pct"],
        "cooldown": heal["potion_cooldown"],
    }


def default_calibration() -> dict:
    """Regioes de pixel que o bot le/clica — dependem da RESOLUCAO do frame
    do projetor, entao precisam ser calibradas por maquina (aba Calibrar).
    Semeado do config.py so como ponto de partida."""
    return {
        "hp_bar": copy.deepcopy(config.HP_BAR),
        "mana_bar": copy.deepcopy(config.MANA_BAR),
        "battle_list": copy.deepcopy(config.BATTLE_LIST),
        "game_area": copy.deepcopy(config.GAME_AREA),
        "minimap": copy.deepcopy(config.MINIMAP),
    }


def default_settings() -> dict:
    """Config global do app (nao e por-preset): janelas, hotkeys, cavebot
    e a calibracao das regioes de pixel. Semeado a partir do config.py."""
    return {
        "client_window_title": config.WINDOW_TITLE,
        "capture_window_title": config.CAPTURE_WINDOW_TITLE,
        "opacity": 255,
        "calibration": default_calibration(),
        "hotkey_panic": config.PAUSE_KEY,
        "hotkey_toggle_attack": config.HOTKEY_TOGGLE_ATTACK,
        "hotkey_toggle_spell": config.HOTKEY_TOGGLE_SPELL,
        "hotkey_toggle_cavebot": config.HOTKEY_TOGGLE_CAVEBOT,
        "waypoints_file": config.WAYPOINTS_FILE,
        "waypoint_wait": config.WAYPOINT_WAIT,
        "record_key": config.RECORD_KEY,
        "loot_radius": config.LOOT_RADIUS,
        "loot_delay": config.LOOT_DELAY,
        "loot_settle": config.LOOT_SETTLE,
    }


def _default_preset() -> dict:
    return {
        "combat": {"combo": default_combo()},
        "healing": {
            "spell_heal": default_spell_heal(),
            "potion_heal": default_potion_heal(),
            "mana_potion": default_mana_potion(),
        },
    }


class PresetStore:
    """Carrega/salva presets.json e da acesso as tabelas de combo/cura."""

    def __init__(self, path: str = PRESETS_FILE):
        self.path = path
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                self.data = json.load(f)
        else:
            self.data = {
                "active_preset": DEFAULT_PRESET_NAME,
                "presets": {DEFAULT_PRESET_NAME: _default_preset()},
                "settings": default_settings(),
            }
            self.save()
        self._migrate()

    def _migrate(self) -> None:
        """Garante que jsons antigos ganhem o bloco 'settings' e quaisquer
        chaves novas de config sem perder o que o usuario ja configurou."""
        settings = self.data.setdefault("settings", {})
        changed = False
        for key, value in default_settings().items():
            if key not in settings:
                settings[key] = value
                changed = True
        if changed:
            self.save()

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------ CRUD
    def names(self) -> list[str]:
        return list(self.data["presets"].keys())

    def active_name(self) -> str:
        return self.data["active_preset"]

    def set_active(self, name: str) -> None:
        if name not in self.data["presets"]:
            raise KeyError(f"preset desconhecido: {name}")
        self.data["active_preset"] = name
        self.save()

    def get(self, name: str | None = None) -> dict:
        return self.data["presets"][name or self.active_name()]

    def create(self, name: str, copy_from: str | None = None) -> None:
        if name in self.data["presets"]:
            raise ValueError(f"ja existe um preset chamado '{name}'")
        source = self.get(copy_from) if copy_from else _default_preset()
        self.data["presets"][name] = json.loads(json.dumps(source))  # deep copy
        self.save()

    def rename(self, old: str, new: str) -> None:
        if old not in self.data["presets"]:
            raise KeyError(f"preset desconhecido: {old}")
        if new in self.data["presets"]:
            raise ValueError(f"ja existe um preset chamado '{new}'")
        self.data["presets"][new] = self.data["presets"].pop(old)
        if self.data["active_preset"] == old:
            self.data["active_preset"] = new
        self.save()

    def delete(self, name: str) -> None:
        if len(self.data["presets"]) <= 1:
            raise ValueError("e preciso manter pelo menos 1 preset")
        if name not in self.data["presets"]:
            raise KeyError(f"preset desconhecido: {name}")
        del self.data["presets"][name]
        if self.data["active_preset"] == name:
            self.data["active_preset"] = self.names()[0]
        self.save()

    # -------------------------------------------------- getters/setters
    def get_combo(self, preset: str | None = None) -> list[dict]:
        return self.get(preset)["combat"]["combo"]

    def set_combo(self, combo: list[dict], preset: str | None = None) -> None:
        self.get(preset)["combat"]["combo"] = combo
        self.save()

    def get_spell_heal(self, preset: str | None = None) -> list[dict]:
        return self.get(preset)["healing"]["spell_heal"]

    def set_spell_heal(self, tiers: list[dict], preset: str | None = None) -> None:
        self.get(preset)["healing"]["spell_heal"] = tiers
        self.save()

    def get_potion_heal(self, preset: str | None = None) -> list[dict]:
        return self.get(preset)["healing"]["potion_heal"]

    def set_potion_heal(self, tiers: list[dict], preset: str | None = None) -> None:
        self.get(preset)["healing"]["potion_heal"] = tiers
        self.save()

    def get_mana_potion(self, preset: str | None = None) -> dict:
        return self.get(preset)["healing"]["mana_potion"]

    def set_mana_potion(self, tier: dict, preset: str | None = None) -> None:
        self.get(preset)["healing"]["mana_potion"] = tier
        self.save()

    # ---------------------------------------------- settings globais do app
    def get_settings(self) -> dict:
        return self.data["settings"]

    def set_setting(self, key: str, value) -> None:
        self.data["settings"][key] = value
        self.save()


if __name__ == "__main__":
    store = PresetStore()
    print(f"presets.json em: {os.path.abspath(store.path)}")
    print(f"preset ativo: {store.active_name()}")
    print(json.dumps(store.get(), indent=2, ensure_ascii=False))
