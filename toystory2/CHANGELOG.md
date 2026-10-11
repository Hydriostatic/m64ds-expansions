# Toy Story 2 — histórico de versões

Toda mudança no que o `.exp` mostra sobe a versão (`VERSION` em `make_toystory2.py`). O emulador mostra
essa versão na lista de expansões, então dá para saber qual está instalada.

## 1.6
- ROM USA original (Rev 0): ela não tem os ícones da tela de fase completa (`levcomp1`/`levcomp2`, que só existem na Rev 1). Nos cartões entram peças do HUD do próprio jogo: Hamm, bandeira quadriculada, a mira (chefe), um "5" com o nome dos itens (missão) e um "?" na fonte da seleção de fases. Na Rev 1 nada muda.
- Logo do Toy Story 2 inteiro na página de abertura.

## 1.5
- O script acha sozinho, no código da ROM, a tabela de arquivos e os endereços (fase, tokens, bateria, vidas, moedas, buffer da imagem), então funciona com a ROM USA original (Rev 0) e com a Rev 1. Para a Rev 1 o `.exp` sai igual ao da 1.4.

## 1.4
- Telas de baixo para fora das fases, cada uma seguindo a imagem da tela de cima: textos legais e logos de abertura (Activision, Disney Interactive, Traveller's Tales, o que está na tela acende), título com "PRESS START" piscando, menu principal, opções na moldura do Etch A Sketch com a fonte de rabisco do jogo, e a tela dos 50 tokens com o token girando.
- Fade entre as páginas quando a tela ou a fase muda.

## 1.3
- Cada cartão mostra o token de verdade: escuro e parado enquanto não foi pego, girando depois que pega (lido de `0x801E22A1` + fase). Nas fases de chefe, o token acende quando o chefe é derrotado.
- Ícones dos cartões menores (24 px).

## 1.2
- Página mais espaçada: margens e espaços maiores entre os painéis, cabeçalho mais alto para os nomes de duas linhas, cartões separados e sem texto (o ícone do jogo já diz o que é), barra de bateria mais estreita para o contador de moedas não encostar na borda, dica do Hamm em até duas linhas.

## 1.1
- Token da Pizza Planet girando embaixo de cada cartão (cada um num tempo diferente) e no cartão das fases de chefe.

## 1.0
- Primeira versão: nome da fase na fonte de menu do jogo, vidas, bateria e moedas, os 5 cartões de token de
  cada fase com os ícones do jogo, a dica do Hamm de cada fase, token e moeda animados.
