# Banjo-Tooie (USA)

`make_banjotooie.py` monta o `banjotooie.exp` a partir da sua ROM (`.z64` ou `.v64`, USA). Toda a arte
sai da própria ROM: as três fontes do jogo, os ícones do HUD e texturas de madeira das fases.

```
pip install pillow
python3 make_banjotooie.py "Banjo-Tooie (USA).z64" banjotooie.exp [preview.png]
```

Precisa de uma versão do M64-DS com páginas `pixel_screen`. Para ver a prévia de outro mundo, passe o
mapa em `PREVIEW_MAP` (por exemplo `PREVIEW_MAP=0xC7` para Glitter Gulch Mine).

## O que aparece na tela de baixo

Uma página no estilo da tela de toque de um jogo de Nintendo DS: tela de 248×216 ampliada 5× (1240×1080
no AYN Thor), sem suavizar.

| Parte | O que mostra |
|---|---|
| Visual | cada mundo usa texturas das próprias fases (fundo, título, cartões, faixa); madeira na Isle o' Hags e antes do jogo |
| Cabeçalho | nome do mundo atual na fonte do título (Banjo-Tooie antes de entrar num mundo) |
| 8 cartões | Jiggies, notas, Jinjos, Glowbos, páginas do Cheato, favos vazios e golpes do Jamjars **deste mundo**, e o tempo de jogo da sessão; o número fica verde quando o mundo está completo |
| Faixa | ovos azuis, de fogo, granada, de gelo e Clockwork, penas vermelhas e douradas |
| Abas de toque | a página (acesa), **MENU** (menu do emulador) e **SAVE/QUIT** |

## Endereços (RAM do N64)

Vêm das ferramentas do Archipelago para Banjo-Tooie (MIT, © 2025 g0goTBC, Austin, jjjj12212) e batem com
os códigos GameShark da versão USA.

| Endereço | O que é |
|---|---|
| `0x80132DC2` | mapa atual (u16) → mundo |
| `0x8012C770` | ponteiro para o bloco de flags; flag = `(byte << 3) \| bit` |
| `0x8011B080 + i*0x0C` | contadores (u16): 0 ovos azuis, 1 fogo, 2 gelo, 3 granada, 4 Clockwork, 6 penas vermelhas, 7 douradas |

| Flags | O que é |
|---|---|
| `0x228`–`0x277`, `0x281`, `0x278`–`0x280` | Jiggies (10 por mundo; Isle o' Hags: Jingaling + as 9 famílias de Jinjos) |
| `0x427`–`0x4BF` | ninhos de notas (16 por mundo, 5 notas cada) e uma clave por mundo (`0x437 + 0x11*mundo`, 20 notas) |
| `0x1CC`–`0x1F8` | Jinjos (5 por mundo) |
| `0x1FA`–`0x212` | favos vazios · `0x2B3`–`0x2CB` páginas do Cheato · `0x217`–`0x227`, `0x02E` Glowbos |
| `0x0D9`–`0x0F4` | golpes do Jamjars |

## Ainda falta

- Trocar de página pelas abas (totais do jogo, Jinjos por família, HUD do Banjo): o formato ainda não tem
  ação para ir de uma `pixel_screen` a outra.
- Jolly Roger's Lagoon aparece como "JOLLY ROGER'S" porque o nome inteiro não cabe na fonte do título.
- Cauldron Keep e alguns mapas de passagem mantêm o último mundo visitado.
