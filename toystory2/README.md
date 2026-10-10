# Toy Story 2: Buzz Lightyear to the Rescue! (USA, Rev 1)

`make_toystory2.py` monta o `toystory2.exp` a partir da sua ROM (`.z64` ou `.v64`, USA Rev 1). Toda a arte
sai da própria ROM: a fonte de menu do jogo (`psxfont`) para o nome da fase, a fonte pequena (`tahoma08`),
os sprites do HUD, os ícones da tela de fase completa e o token da Pizza Planet girando.

```
pip install pillow
python3 make_toystory2.py "Toy Story 2 - Buzz Lightyear to the Rescue! (USA) (Rev 1).z64" toystory2.exp [preview.png]
```

Precisa do M64-DS com camadas animadas (`frames`). Para ver a prévia de outra fase, use `PREVIEW_LEVEL`
(por exemplo `PREVIEW_LEVEL=11`).

## O que aparece na tela de baixo

Tela de 248×216 ampliada 5× (1240×1080 no AYN Thor), sem suavizar.

| Parte | O que mostra |
|---|---|
| Cabeçalho | nome da fase na fonte de menu do jogo (duas linhas nos nomes longos), número da fase e o token girando |
| Status | vidas, bateria (14 segmentos) e moedas de 50, com a moeda girando |
| Cartões | os 5 tokens da fase: moedas do Hamm, a missão da fase (ovelhas, soldados, Little Tikes…), desafio, chefe e segredo, com os ícones do próprio jogo e um token girando embaixo de cada um; nas fases de chefe, um cartão de chefe com o token |
| Dica | a dica do Hamm de onde ele está naquela fase, com as palavras destacadas em amarelo como no jogo |

## Endereços (RAM do N64, Rev 1)

| Endereço | O que é |
|---|---|
| `0x801EFBEC` | fase atual (u32, 1–15): o número que o jogo usa para carregar `pictures\lvlNNx.pic` |
| `0x800BB556` | bateria (u16, cheia = 14) |
| `0x800BB55A` | vidas (u16) |
| `0x800BB55E` | moedas (u16) |

Vidas, bateria e moedas são os códigos GameShark públicos (`0x800BB10A`, `0x800BB106`, `0x800BB10E`) movidos
`+0x450` para a Rev 1. O código do jogo confirma a bateria: soma 4 quando pega uma pilha, limita em 14 e
avisa quando está baixa.

## Formato dos arquivos da ROM

- `0x0D8E78`: tabela de arquivos (nome, tamanho guardado). Os dados começam em `0x0DC380`, na ordem da tabela,
  cada arquivo alinhado a 8 bytes.
- 417 arquivos usam RNC método 1.
- `.tpg`: 16 códigos de página + paleta de 256 cores RGBA5551 + páginas (página de 4 bits no slot N usa as
  cores N×16…N×16+15). `.pic`: paleta + CI8 em blocos de 64×32. `.fnt`: tabela de glifos + 16 cores + glifos de 4 bits.

## Ainda falta

- Confirmar no aparelho os quatro endereços acima (segure a tela de baixo para salvar a memória).
- Tokens pegos em cada cartão e o total de tokens: falta achar onde o jogo guarda isso.
