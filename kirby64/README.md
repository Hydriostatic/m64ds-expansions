# Kirby 64: The Crystal Shards (USA)

`make_kirby64.py` monta o `kirby64.exp` a partir da sua ROM (`.z64` ou `.v64`, USA). Toda a arte é
cortada dos bancos de imagem do próprio jogo.

```
pip install pillow
python3 make_kirby64.py "Kirby 64 - The Crystal Shards (USA).z64" kirby64.exp [preview.png]
```

Precisa de uma versão do M64-DS com páginas `pixel_screen`.

## O que aparece na tela de baixo

| Momento do jogo | `gGameState` | Tela de baixo |
|---|---|---|
| Ligando, entre logos | 0, 2 | preto |
| Logos N64/HAL | 1 | branco |
| Tela de título | 3, 5, 7, 9 | xadrez verde do título |
| Escolha do save | 10 | quadro de cortiça com o bilhete do save: cristais por mundo, %, título |
| Mapa de mundos | 11 | só o fundo do espaço |
| Escolha da fase | 12 | página do caderno com mundo, fase e cristais da fase |
| Na fase | 15 | HUD: vidas, vida, estrelas, poderes, mundo/fase, cristais da fase e total |
| Theater, Opções e outros menus | 22–28 | o papel dos menus |
| Menu de Mini-Games | 23 | imagem e nome do jogo escolhido, Best Score, dificuldades liberadas |
| 100-Yard Hop | 29 | Best Score e o tempo de cada jogador, ao vivo |
| Checkerboard Chase | 30 | Best Score e dificuldades liberadas |
| Bumper Crop Bump | 31 | Best Score e os pontos de cada jogador, ao vivo |

As transições de fade da tela de cima são copiadas na de baixo.

## Endereços (RAM do N64)

Vêm da [decompilação do Kirby 64](https://github.com/farisawan-2000/kirby64), que bate com a ROM USA
(sha1 `6cea2d46b929a3bb347b060a77fccc83526fb855`).

| Endereço | O que é |
|---|---|
| `0x800BE4F0` | `gGameState` (tela atual) |
| `0x800D6E88` | vidas no HUD (+1) |
| `0x800D6E50` | vida (`f32`) |
| `0x800D6E60` | estrelas |
| `0x800D6BC8 + mundo*4 + fase` | cristais da fase (bits 0–2) |
| `0x800D6B88` | save escolhido |
| `0x800ECA08 + 0x58*save` | save: +0x00 mundo, +0x10 %, +0x18 recorde do Hop (quadros, 30/s), +0x1A do Bumper (pontos), +0x1C do Checker (quadros), +0x34 chefes, +0x3C cristais |
| `0x800D6BB9` / `BA` / `BB` | dificuldade liberada: Hop / Bumper / Checker |
| `0x8018EDE1` | cursor do menu de Mini-Games (0 Hop, 1 Bumper, 2 Checker) |
| `0x8018E468 + 4*jogador` | tempo do jogador no 100-Yard Hop (quadros) |
| `0x8018E1E0 + jogador` | pontos do jogador no Bumper Crop Bump |
| `0x800D6B24` / `0x800D6B28` / `0x800D6B2E` | fade: objeto, cor, alfa |

## Ainda falta

- Contagem 3-2-1 antes dos mini-games: o jogo não guarda o número numa variável fixa.
- Placar ao vivo do Checkerboard Chase.
- Fundo do tutorial e da moldura das cenas da história: falta saber o `gGameState` dessas telas.
