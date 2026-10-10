# Expansões M64-DS

Painéis de segunda tela (`.exp`) para o [M64-DS](https://github.com/Hydriostatic/mupen64plus-ae), o
Mupen64Plus AE para aparelhos com duas telas, como o AYN Thor. Cada expansão desenha um painel do jogo
na tela de baixo, lendo a memória do jogo enquanto você joga.

## Expansões

| Jogo | Pasta | O que a tela de baixo mostra |
|---|---|---|
| Kirby 64: The Crystal Shards (USA) — v1.6 | [`kirby64/`](kirby64/) | HUD da fase, menus, quadro de cristais por save, mini-games com placar ao vivo |

## Por que não tem `.exp` pronto aqui

As expansões usam a arte, as fontes e as cores do próprio jogo. Esse material é da Nintendo e da HAL,
então não fica neste repositório. Cada pasta tem um script que monta o `.exp` a partir da **sua** ROM:

```
pip install pillow
python3 kirby64/make_kirby64.py "Kirby 64 - The Crystal Shards (USA).z64" kirby64.exp
```

## Instalar no emulador

Na tela de baixo, toque em **Expansões** › **Importar expansão (.exp)…** e escolha o arquivo. Quando
você abre a ROM certa, o emulador usa a expansão sozinho.

## Versões

Toda mudança no que um `.exp` mostra sobe a versão dele, e cada pasta tem um `CHANGELOG.md`.

## Fazer uma expansão nova

O formato está em [FORMAT.md](FORMAT.md). Uma expansão é só um zip com um `manifest.json` (quais
endereços ler e como desenhar) e imagens; não é preciso mexer no emulador.

Para achar endereços, segure a tela de baixo durante o jogo: o emulador salva uma cópia da memória
(8 MB, big-endian) em `Download/Mupen64BT/`.
