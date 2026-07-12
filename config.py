# -*- coding: utf-8 -*-
"""
Configuracao central do bot. TODAS as coordenadas sao relativas a area
cliente da janela (mesma referencia do frame capturado e dos cliques).

>>> Use `python calibrate.py` para descobrir os valores do SEU cliente. <<<
Passe o mouse sobre a barra de HP, battle list etc. e anote (x, y) e cor BGR.

IMPORTANTE: nao redimensione a janela do cliente depois de calibrar —
todas as coordenadas mudariam.
"""

# Janela do CLIENTE: recebe as teclas e cliques (PostMessage).
WINDOW_TITLE = "Tibia - Zegani"
# Janela do PROJETOR do OBS: fonte dos frames (PrintWindow). O projetor
# precisa estar aberto E com o mesmo tamanho em pixels da area do jogo no
# cliente — as coordenadas lidas do frame sao usadas nos cliques enviados
# ao cliente; se os tamanhos diferirem, tudo desalinha.
CAPTURE_WINDOW_TITLE = "Projetor - Fonte: Tibia"

# ---------------------------------------------------------------- barras
# A barra e lida como uma LINHA horizontal de pixels: do x inicial ao
# x final, na altura y. O percentual = pixels com a "cor cheia" / total.
# Calibrado em 2026-07-12 sobre o projetor do OBS (frame 1920x1009).
# Barras ao lado do minimapa, junto ao "695 / 260".
HP_BAR = {
    "x_start": 1768,
    "x_end": 1857,
    "y": 285,
    "color_bgr": (79, 79, 219),   # vermelho medido no frame
    "tolerance": 30,
}
MANA_BAR = {
    "x_start": 1768,
    "x_end": 1857,
    "y": 298,
    "color_bgr": (218, 80, 83),   # azul medido no frame
    "tolerance": 30,
}

# ------------------------------------------------------------- healbot
HEAL = {
    "spell_key": "F1",       # exura ico / exura gran ico
    "spell_below_pct": 80,   # cura por magia abaixo de 80% de HP
    "potion_key": "F2",      # health potion (emergencia)
    "potion_below_pct": 45,  # potion abaixo de 45%
    "mana_potion_key": "F3",
    "mana_below_pct": 40,    # mana potion abaixo de 40% de mana
    "spell_cooldown": 1.0,   # exhaust de cura do SEU servidor (segundos)
    "potion_cooldown": 1.0,
}

# --------------------------------------------------- battle list / combate
# Regiao da battle list: recorte (x, y, largura, altura) onde aparecem
# as criaturas. As entradas sao detectadas pela barrinha de vida delas.
BATTLE_LIST = {
    # Painel "Battle List" da coluna direita, abaixo dos botoes de filtro
    # (area util das entradas, sem o scrollbar). CUIDADO: a regiao default
    # anterior (0,0) caia em cima do Bestiary Tracker e contava fantasmas.
    "x": 1750, "y": 465, "w": 155, "h": 170,
    # Barrinha de vida da criatura na battle list: borda preta com
    # preenchimento verde/amarelo/vermelho. Detectamos o VERDE cheio
    # e tons parciais pela linha vertical de amostragem.
    "entry_height": 22,
}

ATTACK_KEY = "SPACE"        # attack next do proprio Tibia
ATTACK_COOLDOWN = 2.0       # espera entre re-targets

# Rotacao do Elite Knight: da mais forte pra mais fraca. O bot escolhe a
# primeira que satisfaz: monstros >= min_monsters, mana atual >= mana_pct
# (percentual estimado; ajuste pro seu total de mana) e fora de cooldown.
EK_SPELLS = [
    {"name": "exori gran", "key": "F5", "min_monsters": 3, "mana_pct": 35, "cooldown": 6.0},
    {"name": "exori",      "key": "F6", "min_monsters": 2, "mana_pct": 15, "cooldown": 4.0},
    {"name": "exori ico",  "key": "F7", "min_monsters": 1, "mana_pct": 5,  "cooldown": 2.0},
]
SPELL_GLOBAL_COOLDOWN = 2.0  # exhaust global de ataque do seu servidor

# ----------------------------------------------------------------- loot
# Centro do personagem na tela e tamanho de 1 SQM em pixels, para achar
# os 8 tiles ao redor (onde caem os corpos).
GAME_AREA = {
    # ESTIMADO pelo frame (viewport 325..1417 x 5..800, 15x11 SQMs).
    # Confira com calibrate.py: mouse no centro do char e nas bordas de 1 SQM.
    "player_x": 871,
    "player_y": 402,
    "sqm_size": 73,
}
LOOT_DELAY = 0.25    # pausa entre cliques de loot
LOOT_RADIUS = 1      # 1 = 3x3 SQMs ao redor; 2 = 5x5 (pega corpo mais longe)
LOOT_SETTLE = 0.4    # espera o char PARAR antes de lootear (segundos)

# -------------------------------------------------------------- cavebot
MINIMAP = {
    "x": 1752, "y": 4, "w": 106, "h": 109,   # canto superior direito do frame
}
WAYPOINTS_FILE = "waypoints.json"
WAYPOINT_WAIT = 4.0      # v1: segundos esperando chegar apos clicar no minimapa
RECORD_KEY = "F11"       # tecla p/ gravar waypoint no modo gravacao
PAUSE_KEY = "F12"        # liga/desliga o bot inteiro (main.py)

# ---------------------------------------------------------- hotkeys globais
# Teclas que ligam/desligam modulos com o JOGO em foco (lidas via
# GetAsyncKeyState, igual a tecla de panico). Sao apenas os DEFAULTS —
# a GUI salva as escolhas do usuario em presets.json (bloco "settings").
HOTKEY_TOGGLE_ATTACK = "F9"    # liga/desliga o auto-attack (targeting)
HOTKEY_TOGGLE_SPELL = "F10"    # liga/desliga o auto-spell (combo de magias)
HOTKEY_TOGGLE_CAVEBOT = "F8"   # liga/desliga so o cavebot
