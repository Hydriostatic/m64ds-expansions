# Expansões de segunda tela (.exp) — M64-DS

Uma expansão é um arquivo `.exp` que dá a um jogo um painel na tela de baixo (BC). Ela só
contém dados: quais valores ler da memória do jogo e como desenhá-los. Não tem código, então
para fazer um painel para um jogo novo não é preciso mexer no emulador.

**Instalar:** na tela de baixo, toque em **Expansões**, depois em **Importar expansão (.exp)…**
e escolha o arquivo. O emulador copia o arquivo para dentro do app, então depois você pode apagar
o original. Ao abrir um jogo, o emulador usa a expansão que combina com aquela ROM.

## O arquivo

Um `.exp` é um **zip** renomeado, com:

```
manifest.json        obrigatório
images/…             opcional: fundo e peças (PNG/JPG)
icons/…              opcional: ícones dos blocos
fonts/…              opcional: uma fonte .ttf/.otf
```

## manifest.json

```json
{
  "format": 1,
  "id": "banjotooie-usa-exemplo",
  "name": "Banjo-Tooie – Exemplo",
  "game": "Banjo-Tooie (USA)",
  "version": "1.0",
  "author": "Você",

  "match": { "header": "BANJO TOOIE", "country": "E" },

  "theme": { … },
  "screen": { … },
  "values": { … }
}
```

- `id`: nome único. Importar outra expansão com o mesmo `id` substitui a anterior, e é assim
  que se atualiza uma expansão.
- `match`: diz para qual ROM a expansão serve. Use pelo menos um destes:
  - `header`: o começo do nome interno da ROM.
  - `country`: a letra da região (`E` para EUA, `P` para Europa, `J` para Japão).
  - `crc`: o CRC da ROM, como o app mostra.
  - `md5`: o MD5 da ROM. Se estiver presente, só ele é usado.

### theme (tudo opcional)

| chave | o que é |
|---|---|
| `background`, `panel`, `text`, `label`, `accent` | cores `#RRGGBB` |
| `title_colors` | lista de cores, uma por palavra do título; as palavras que sobram ficam com a última cor |
| `font` | caminho da fonte dentro do zip |
| `background_image` | imagem de fundo (preenche a tela) |
| `sign_image`, `tile_image`, `bar_image`, `button_image` | peças desenhadas em 9 partes (veja abaixo) |

Peça em 9 partes: `{"image": "images/tile.png", "insets": [esq, topo, dir, baixo]}`. Os cantos
mantêm o formato e só o meio estica. Também é possível informar, em pixels da própria imagem:

- `label_y`: centro do rótulo, medido a partir do topo (para blocos).
- `value_y`: centro do valor, medido a partir de baixo (para blocos).
- `content_left`: onde os itens começam (para a barra; útil quando a arte já traz uma placa
  desenhada à esquerda).

### screen

```json
"screen": {
  "title": "{world}",
  "columns": 3,
  "tiles": [
    { "label": "Jiggies", "icon": "icons/jiggy.png", "value": "{jiggies}/90" }
  ],
  "bar": { "label": "", "items": [
    { "icon": "icons/feather_red.png", "value": "{red_feathers}" }
  ]}
}
```

Os textos aceitam `{nome}`, que é trocado pelo valor com esse nome. `{time}` já existe: é o
tempo jogado nesta sessão. A tela sempre tem os botões **Opções** (abre o menu do emulador) e
**Salvar e sair**.

### values: lendo a memória

Os endereços podem ser escritos como `0x8011B080` (endereço do N64) ou como offset físico. A
ordem dos bytes já é a do N64 (big-endian).

| `type` | campos | resultado |
|---|---|---|
| `u8` `s8` `u16` `s16` `u32` | `addr`, ou `ptr` + `offset` | número; aceita `times` e `add` opcionais |
| `flags` | `addr` ou `ptr` + `offset`; `bits` (lista); `mode` | quantos bits estão ligados (`count`), ou 1/0 (`any`, `all`) |
| `sum` | `terms`: nomes, ou `{"value": "nome", "times": 5}` | soma |
| `lookup` | `value`, `table`, `default`, `keep_last` | texto da tabela; `keep_last` mantém o último valor encontrado |
| `const` | `value` | fixo |

- `ptr`: um endereço que guarda um ponteiro. O valor é lido em ponteiro + `offset`.
- `bits`: números no formato `(byte << 3) | bit`, contados a partir do endereço base.

Exemplo, com as notas do Banjo-Tooie (ninhos valem 5, claves valem 20):

```json
"nests": { "type": "flags", "ptr": "0x8012C770", "bits": [1063, 1064, …] },
"clefs": { "type": "flags", "ptr": "0x8012C770", "bits": [ … ] },
"notes": { "type": "sum", "terms": [ {"value": "nests", "times": 5}, {"value": "clefs", "times": 20} ] }
```

## Página de mapa (`map_screen`, opcional)

Uma segunda página, desenhada sobre uma imagem de template que mantém a proporção original
(as sobras da tela ficam na cor `fill`). Todas as posições são em pixels do template.

```json
"map_screen": {
  "template": "images/map_template.jpg",
  "mask": "images/map_mask.png",
  "fill": "#2A1709",
  "title": { "x": 205, "y": 120, "w": 320, "size": 58, "value": "{world}" },
  "map": {
    "rect": [228, 58, 1158, 892],
    "zoom": 2.0,
    "map_value": "map",
    "x": "pos_x", "z": "pos_z", "yaw": "",
    "images": [ { "image": "maps/mayahem_temple.png", "ids": ["0xB8"], "center": [0.5, 0.45],
                  "ref": [[x, z, px, py], [x, z, px, py], [x, z, px, py]] } ]
  },
  "slots": [ { "x": 110, "y": 270, "r": 72, "icon": "icons/jiggy.png", "value": "{here_jiggies}/10" } ],
  "tabs":  [ { "x": 10, "y": 925, "w": 262, "h": 150, "label": "Painel", "action": "screen:main" } ]
}
```

- `title`: o nome em duas linhas. A primeira palavra usa a cor 1 de `title_colors` e o resto
  usa a cor 2. Segure o nome para salvar uma cópia da memória em Download/Mupen64BT.
- `mask`: um PNG do tamanho do template. O mapa só aparece onde a máscara é opaca (por exemplo,
  no formato do pergaminho).
- `map`: o mapa aparece com `zoom` e acompanha o jogador. A seta fica sempre no meio e o mapa
  desliza por baixo dela. A imagem do mapa é escolhida pelo valor `map_value`, comparado com
  `ids`. Sem `yaw`, o pin é redondo.
- **Posição automática:** sem `ref`, o emulador descobre sozinho onde o jogo cai no mapa. Ele
  junta os lugares por onde o jogador anda e, se houver `objects`, as posições dos objetos da
  fase. Depois encaixa esses pontos na parte opaca da imagem do mapa, testando as 8 rotações e
  espelhamentos. A estimativa melhora conforme se joga e fica salva no aparelho. Exemplo de
  `objects` (a lista de objetos do Banjo-Tooie):
  `{"list": "0x80136EE0", "first": 4, "last": 8, "base": 16, "stride": 156, "x": 4, "z": 12}`.
- `ref`: pontos de calibração (posição no jogo para pixel do mapa); três pontos aceitam rotação.
  Dá para calibrar no aparelho, sem escrever `ref`: **segure o mapa** e toque onde o personagem
  está, em 3 lugares diferentes. A calibração fica salva no aparelho.
- `tabs` → `action`: `screen:main` (página de blocos), `screen:map`, `menu` (menu do emulador),
  `save_quit`.

## Página em pixel art (`pixel_screen`, opcional)

Uma página montada com sprites sobre uma tela pequena, no tamanho de pixel do próprio jogo. O
emulador amplia essa tela pelo maior número inteiro que couber, sem suavizar, e a centraliza (as
sobras ficam na cor `fill`). Serve para refazer o HUD de um jogo com a arte dele. Se existir, é a
página que abre primeiro. O menu continua no botão Voltar.

```json
"pixel_screen": {
  "size": [248, 199],
  "fill": "#9C7318",
  "layers": [
    { "image": "images/bg.png", "x": 0, "y": 0 },
    { "repeat": "images/cell.png", "count": "hp", "max": 6, "dx": 20, "x": 101, "y": 6 },
    { "pick": "ability_l", "images": { "1": "icons/fire.png", "7": "icons/cutter.png" },
      "anchor": "center", "x": 46, "y": 111 },
    { "number": "lives", "glyphs": "digits/{c}.png", "pad": 2, "advance": 20, "x": 43, "y": 12 },
    { "image": "icons/shard.png", "x": 124, "y": 109, "show": "s0_0", "hide": "is_dark" }
  ],
  "buttons": [ { "x": 0, "y": 0, "w": 40, "h": 20, "action": "menu" } ]
}
```

As posições são em pixels da tela (`size`). As camadas são desenhadas na ordem da lista:

| camada | o que desenha |
|---|---|
| `image` | uma imagem fixa |
| `repeat` + `count` | a imagem repetida `count` vezes (até `max`), andando `dx`/`dy` a cada uma |
| `pick` + `images` | a imagem escolhida pelo valor (`"default"` vale quando nenhuma combina); sem imagem, nada |
| `number` + `glyphs` | o valor desenhado com uma imagem por caractere: `{c}` vira `0`–`9`, `slash`, `minus`, `colon`, `dot` ou `percent`. `pad` completa com zeros à esquerda; `advance` é a largura de cada caractere (sem ele, usa a largura da imagem); `align`: `left`, `right` ou `center` |

- `anchor: "center"` faz `x`/`y` serem o centro da imagem.
- `show` / `hide`: o nome de um valor. A camada só aparece se `show` for diferente de 0 e se
  `hide` for 0.
- Enquanto o jogo não começa, só as camadas fixas aparecem.
- `buttons` (opcional): áreas de toque com as mesmas ações das abas do mapa (`menu`,
  `save_quit`, `screen:map`). A arte do botão vai numa camada.
- Segure a página para salvar uma cópia da memória, como no nome do mundo das outras páginas.

### Animação e transição (versões do M64-DS de outubro/2026 em diante)

Uma camada `frames` toca uma animação: `{f}` no caminho vira o número do quadro, de 0 a `length - 1`.

```json
{ "frames": "anim/jinjo_{f}.png", "length": 10, "fps": 15, "phase": 3, "anchor": "center", "x": 40, "y": 60 }
```

- `fps`: quadros por segundo (padrão 15). `phase`: quantos quadros adiantar, para ícones lado a lado
  não girarem juntos. Aceita `show` / `hide` como as outras camadas.
- Enquanto a página tem animação ou transição na tela, o emulador redesenha a ~30 quadros por segundo.
  Os valores da memória continuam sendo lidos 4 vezes por segundo.

`transition` (opcional, dentro de `pixel_screen`) toca uma transição quando um valor muda, por exemplo
ao trocar de mundo:

```json
"transition": { "value": "world", "style": "jigsaw", "ms": 850, "cols": 8, "rows": 7 }
```

- `jigsaw`: a página nova cai por cima da antiga em peças de quebra-cabeça (`cols` × `rows`), uma de
  cada vez. `fade`: a página nova aparece por cima, aos poucos.
- A primeira leitura do valor não dispara transição; só as mudanças depois dela.

O exemplo é [`kirby64/make_kirby64.py`](kirby64/make_kirby64.py), que monta o `kirby64.exp` a partir da
sua ROM do Kirby 64 (USA), cortando a arte do próprio jogo.

### Mais tipos de valor

| `type` | campos | resultado |
|---|---|---|
| `f32` | `addr`, `ptr` ou `chain` | número decimal do jogo (arredondado); aceita `times` e `add` |
| `select` | `index`, `options` (nomes), `default` | o valor escolhido pelo índice |

`lookup` também pode devolver números (por exemplo, mapa → índice do mundo).

`chain` segue ponteiros: `["0x80135490", {"value": "player_index", "times": 4}, "*", "0xE4", "*", "8"]`.
O primeiro item é o endereço inicial. Números somam ao endereço, `{"value": …}` soma um valor e
`"*"` lê o ponteiro guardado ali.

O emulador não tem nenhum painel de jogo embutido: tudo vem das expansões.
