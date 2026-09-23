"""checar_prompts.py — a varredura que eu vinha fazendo na mão, e errando.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
O dono disse, e está certo: *"É um princípio básico analisar TODA a
codificação para corrigir em todos os lugares. É ÓBVIO que se não fizer isso
o erro persistirá no sistema."*

O histórico desta base prova que ele tem razão, e que a minha disciplina não
basta:

    a paleta azul fixa voltou TRÊS vezes, em lugares diferentes
    o "ZERO TEXTO" sobreviveu no preset do tipo 8 depois de eu o remover
    a regra de ocupar 65-80% do quadro pegou a AMBIENTAÇÃO, e o produto
      saiu do tamanho do ambiente

Nos três casos eu procurei pelo TEXTO do sintoma, e não pelo ALCANCE da regra.
Corrigi onde o problema apareceu e deixei onde ele ainda não tinha aparecido.

O QUE ELE FAZ
-------------
Monta o prompt REAL dos nove tipos — os oito do padrão mais o Personalizado —
e confere, um por um, o que cada um TEM de conter e o que NÃO PODE conter.

Não é teste de unidade: é varredura. A pergunta que ele responde não é "esta
função funciona", e sim "esta regra chegou em todos os lugares onde deveria, e
em nenhum onde não deveria".

COMO USAR
---------
    python3 checar_prompts.py

Entra no ritual de antes de subir, ao lado do `compileall` e do
`checar_ordem.py`. Regra nova mexida em `imagem.py` sem passar por aqui é
regra que vai reaparecer daqui a três semanas na tela de alguém.
"""

import sys

TIPOS_COM_TEXTO = (
    "2 — Benefícios do produto",
    "3 — Benefícios no cenário de uso",
    "4 — Close nos detalhes",
    "5 — Características técnicas (medidas/peso/material)",
    "6 — Quebra de objeção",
    "7 — Presenteie",
)
TIPO_CAPA = "1 — Capa do anúncio (fundo branco)"
TIPO_AMBIENTE = "8 — Ambientação realista (sem texto)"
TIPO_LIVRE = "Personalizado (descrevo o que quero)"

TODOS = (TIPO_CAPA,) + TIPOS_COM_TEXTO + (TIPO_AMBIENTE, TIPO_LIVRE)

# ── O que cada regra exige, e onde ela vale ─────────────────────────────────
#
# (descrição, trecho procurado, tipos onde DEVE existir, tipos onde NÃO pode)
#
# `None` em "onde deve" significa "em todos". A tabela é o contrato: mudar uma
# regra em `imagem.py` sem mexer aqui faz a varredura reprovar, que é
# exatamente o ponto.
REGRAS = [
    ("a trava de cor do produto", "TRAVA DE COR", None, ()),
    ("a proibição de trocar o produto", "PROIBIÇÃO ABSOLUTA", None, ()),
    ("a fidelidade às fotos de referência", "REGRA DE FIDELIDADE", None, ()),

    # A REGRA QUE CAUSOU O PRODUTO GIGANTE.
    ("a ocupação medida do quadro (55-70% / 65-80%)", "55% a 70%",
     TIPOS_COM_TEXTO, (TIPO_AMBIENTE,)),
    ("a proibição de produto pequeno em cenário amplo",
     "Nunca deixe o produto pequeno", TIPOS_COM_TEXTO, (TIPO_AMBIENTE,)),
    ("a escala real do ambiente", "ESCALA REAL", (TIPO_AMBIENTE,),
     TIPOS_COM_TEXTO + (TIPO_CAPA,)),
    ("o produto pousado com sombra real", "POUSADO", (TIPO_AMBIENTE,),
     TIPOS_COM_TEXTO),

    # A PALETA AZUL FIXA, QUE VOLTOU TRÊS VEZES.
    ("a cor de marca imposta ao fundo", "#1A3A6B", (), TODOS),
    ("a paleta azul como regra de fundo", "fundo azul da marca", (), TODOS),

    # O "ZERO TEXTO" QUE SOBREVIVEU NUM PRESET.
    #
    # A primeira versao desta tabela proibia a frase em TODOS os tipos — e a
    # varredura reprovou na hora, apontando a Capa. Ela estava certa e eu
    # errado: a capa e foto limpa em fundo branco, e ali "zero texto" e a
    # regra correta. O erro nunca foi a frase existir; foi ela existir nos
    # tipos que precisam de texto, e no tipo 8, que tem UMA excecao explicita
    # ("Imagem meramente ilustrativa").
    ("a proibição total de texto", "ZERO TEXTO", (),
     TIPOS_COM_TEXTO + (TIPO_AMBIENTE,)),
    ("a exceção única de texto da ambientação",
     "EXCEÇÃO ÚNICA", (TIPO_AMBIENTE,), TIPOS_COM_TEXTO),

    ("o marcador de modo de fundo", "MS_FUNDO:", None, ()),
]


def _prompt(tipo):
    # O aviso de "missing ScriptRunContext" do Streamlit polui a saida e
    # esconde justamente a linha que interessa: a falha.
    import logging
    logging.getLogger("streamlit").setLevel(logging.ERROR)
    logging.getLogger(
        "streamlit.runtime.scriptrunner_utils.script_run_context"
    ).setLevel(logging.ERROR)
    import imagem
    return imagem.montar_prompt_imagem(
        tipo, "", {"nome_comercial": "Produto de Teste", "cor": "preto",
                   "medidas": "71x14x14", "material": "Metal"},
        "Produto de Teste")


def main():
    prompts = {}
    for t in TODOS:
        try:
            prompts[t] = _prompt(t)
        except Exception as e:
            print(f"FALHA  nao consegui montar o prompt de '{t}': "
                  f"{type(e).__name__}: {e}")
            return 1

    falhas = 0
    for desc, trecho, deve, nao_pode in REGRAS:
        alvo_deve = TODOS if deve is None else deve
        for t in alvo_deve:
            if trecho not in prompts[t]:
                print(f"FALHA  {desc}: FALTA em '{t}'")
                falhas += 1
        for t in nao_pode:
            if trecho in prompts[t]:
                print(f"FALHA  {desc}: NAO DEVIA estar em '{t}'")
                falhas += 1

    # Prompt vazio ou minúsculo é sintoma de branch que deixou de montar.
    for t, p in prompts.items():
        if len(p) < 800:
            print(f"FALHA  o prompt de '{t}' tem so {len(p)} caracteres")
            falhas += 1

    if not falhas:
        print(f"ok    {len(TODOS)} tipos, {len(REGRAS)} regras varridas, "
              "nenhuma fora do lugar")
    print(f"\nfalhas: {falhas}")
    return falhas


if __name__ == "__main__":
    sys.exit(main())
