"""idioma.py — tudo que o Studio escreve sai em português do Brasil.

POR QUE ISTO EXISTE
-------------------
O pedido do dono foi literal: "tudo precisa estar em português do Brasil".
Chegou junto de duas peças — uma imagem com "Apretica newtona estético" e
relatos de resposta misturando inglês com português.

A causa não era o modelo escolher outro idioma por conta própria. Era que
NENHUM prompt pedia idioma. `descricao.py`, `tit_ml.py` e `palavras_chave.py`
mandavam a instrução em português e confiavam que a resposta viria igual —
e vem, quase sempre, menos nas palavras que o mercado escreve em inglês:
premium, design, kit, home office, wireless, best seller. Elas atravessam
sozinhas, e é isso que o colaborador vê como "misturado".

UMA REGRA, E NÃO UMA CÓPIA
--------------------------
O texto mora aqui e é acrescentado ao prompt de quem gera conteúdo. Colado em
seis arquivos, ele passaria a discordar de si mesmo na primeira correção — é a
mesma razão pela qual a lista de colaboradores saiu do código.

Para tornar uma tela obediente ao idioma, some `idioma.REGRA` ao prompt dela.
"""

REGRA = """

━━━ IDIOMA (regra final, acima de qualquer outra) ━━━
Escreva TUDO em português do Brasil. Nenhuma palavra em inglês na resposta.
- Palavra estrangeira que virou hábito de marketplace também conta: troque
  premium por "de alto padrão", design por "desenho"/"acabamento", kit por
  "conjunto", home office por "escritório em casa", best seller por "mais
  vendido", wireless por "sem fio", case por "capa", led por "led" (esta é
  sigla técnica e pode ficar).
- Nome próprio de marca, modelo e sigla técnica (LED, USB, ABS, Bluetooth)
  ficam como estão — traduzi-los seria erro maior.
- Ortografia, acentuação e concordância corretas. Frase que você não
  escreveria num anúncio publicado não deve sair daqui.
"""


def com_regra(prompt):
    """O prompt com a regra de idioma no fim. Onde ela pesa mais."""
    return f"{prompt}{REGRA}"
