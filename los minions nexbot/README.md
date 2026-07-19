# Los Minions Nextbot

Аддон nextbot для Garry's Mod.

## Установка

Скопируй папку `los minions nexbot` в:

```
Steam/steamapps/common/GarrysMod/garrysmod/addons/
```

В игре: **Q → NPCs → Los Minions Nextbot → Los Minions**

## Структура

```
los minions nexbot/
├── lua/
│   ├── autorun/los_minions_nextbot.lua
│   └── entities/npc_los_minions.lua
├── models/los_minions/          ← сюда .mdl после компиляции
├── materials/
│   ├── entities/npc_los_minions.png
│   └── los_minions/             ← .vtf / .vmt
├── sound/los_minions/           ← музыка для игры (mp3/wav)
├── song/                        ← исходные треки (скопируй в sound/)
└── source/glb/                  ← положи сюда minions.glb
```

## Компиляция minions.glb → Source .mdl

Garry's Mod **не читает** `.glb` напрямую. Нужно скомпилировать в Source:

1. Положи `minions.glb` в `source/glb/minions.glb`
2. Открой Blender → Import → glTF 2.0 (`.glb`)
3. Экспорт через **Blender Source Tools** в `.smd` / `.dmx`
4. Собери `.qc` (пример: `source/glb/minions.qc`)
5. Скомпилируй Crowbar / `studiomdl.exe`
6. Готовые файлы положи в:
   - `models/los_minions/minions.mdl` (+ `.vvd`, `.dx80.vtx`, `.dx90.vtx`, `.phy`)
   - текстуры → `materials/los_minions/minions.vtf` (и обнови `.vmt`)

Пока модели нет, nextbot спавнится с fallback-моделью `kleiner`.

## Музыка (song)

Положи треки в `song/`, затем скопируй нужные файлы в `sound/los_minions/` с именами:

| Файл | Когда играет |
|------|----------------|
| `chase1.mp3` | погоня |
| `chase2.mp3` | погоня |
| `banana.mp3` | погоня |
| `idle1.mp3` | бродит |
| `idle2.mp3` | бродит |
| `jumpscare.mp3` | касание / смерть |

## Пути в Lua

- Модель: `models/los_minions/minions.mdl`
- Звуки: `sound/los_minions/*.mp3`
