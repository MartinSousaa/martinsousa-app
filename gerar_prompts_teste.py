"""gerar_prompts_teste.py — despeja o prompt REAL de muitos cenários, sem gastar.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
O dono: *"preciso que você crie um dossiê para que o Claude acesse o Studio e
teste diversas maneiras, diversas formas de gerar imagens, para que ele analise
como esse prompt está sendo gerado, para que a gente possa corrigir diversos
erros."*

Ler um prompt de cada vez na tela do Studio custa clique e paciência. Aqui os
nove tipos vezes as combinações de contexto saem todos de uma vez, em arquivos,
prontos para serem lidos lado a lado — que é como uma contradição aparece.

O QUE ELE NÃO FAZ
-----------------
Não gera imagem, não chama motor, não gasta. O texto sai pelo MESMO caminho da
geração (`imagem.prompt_que_sera_enviado`, que é `gerar_imagem_ia` com
`so_montar`), e não de uma segunda montagem. Segunda montagem discorda da
primeira — foi assim que a varredura desta base passou semanas conferindo o
prompt em português enquanto o motor recebia outro.

A leitura de visão do produto é trocada por um texto fixo, porque aqui não há
produto real: o que se está conferindo é a MONTAGEM, não a descrição.

COMO USAR
---------
    python3 gerar_prompts_teste.py                 # cenários padrão
    python3 gerar_prompts_teste.py --saida /tmp/p  # noutra pasta
    python3 gerar_prompts_teste.py --listar        # só os nomes dos cenários

Depois leia `_INDICE.md` na pasta de saída: ele diz o que cada arquivo é e o
que se espera encontrar dentro dele. O contrato de cada seção está em
`DOSSIE_PROMPT.md`.
"""

import argparse
import io
import logging
import os
import sys


def _calar_streamlit():
    for nome in ("streamlit",
                 "streamlit.runtime.scriptrunner_utils.script_run_context"):
        logging.getLogger(nome).setLevel(logging.ERROR)


def _foto(cor=(200, 120, 60)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), cor).save(buf, "PNG")
    return buf.getvalue()


# ── QUATRO PRODUTOS, E A RAZAO DE SEREM QUATRO ──────────────────────────────
#
# Um produto so ja acha TODO defeito de montagem: contradicao numerica, bloco
# que sumiu, placeholder vazado, ordem e contraordem. Esses nao dependem do
# produto — trocar de produto so produz quatro copias do mesmo achado.
#
# O que um produto so NAO acha e o defeito de JULGAMENTO: a direcao de arte
# esta mesmo sendo deduzida deste produto, ou caiu num padrao? O par do
# Presenteie muda com o publico? O risco de reflexo vira instrucao quando o
# produto e metalico? Isso exige produtos que discordem entre si.
#
# Por isso os quatro sao escolhidos para serem opostos nos eixos que decidem
# a direcao de arte: cor, material e acabamento, posicionamento, publico e
# ambiente de uso. Dois produtos parecidos testam uma coisa so, duas vezes.
PRODUTOS = {
    "album": {
        "_porque": "Escuro, fosco, delicado, adulto, sem reflexo. É a linha de "
                   "base — produto premium calmo.",
        "dados": {
            "nome_comercial": "Álbum de Fotos 30x30 Capa Dura Preta",
            "cor": "preto", "medidas": "30x30x2 cm", "peso": "501 g",
            "material": "Papel cartão e capa dura",
            "diferenciais": "Folhas pretas internas, acabamento artesanal",
            "caracteristicas": "60 folhas, encadernação costurada",
            "uso": "Guardar fotografias impressas",
        },
        "direcao": {
            "nome": "Elegância Minimalista Contemporânea",
            "posicionamento": "delicado, premium, nostálgico",
            "atmosfera": "Universo calmo e atemporal, onde a capa dura preta é "
                         "protagonista e o espaço respira.",
            "paleta": {
                "fundo":  {"nome": "Branco Natural", "hex": "#F7F5F1"},
                "painel": {"nome": "Cinza Claro", "hex": "#E3E0DA"},
                "titulo": {"nome": "Preto Profundo", "hex": "#1C1B19"},
                "apoio":  {"nome": "Cinza Médio", "hex": "#A9A29A"},
                "acento": {"nome": "Cobre Envelhecido", "hex": "#A9793F"},
            },
            "materiais": ["linho natural", "madeira clara fosca", "papel artesanal"],
            "luz": "Luz natural difusa, lateral suave, contrastes controlados.",
            "saturacao": "BAIXA",
            "props_preferidos": ["fotografias impressas", "tecido de linho"],
            "props_proibidos": ["planta grande", "papelaria colorida"],
            "risco_de_reflexo": "BAIXO",
            "trava_do_produto": "Álbum quadrado 30x30 com capa dura preta "
                                "fosca, folhas pretas internas.",
        },
        "cor_foto": (28, 27, 25),
    },
    "caneca": {
        "_porque": "Cinza pedra texturizado, temático, masculino, ambiente de "
                   "bar. Testa cenário deduzido longe de escritório e "
                   "superfície com textura forte.",
        "dados": {
            "nome_comercial": "Caneca Medieval Guerreiro 400ml Inox",
            "cor": "cinza pedra", "medidas": "14x12x10 cm", "peso": "326 g",
            "material": "Resina com interior em aço inox",
            "diferenciais": "Interior inox térmico, textura de pedra esculpida",
            "caracteristicas": "400ml, alça em formato de corrente",
            "uso": "Bebidas quentes e frias, colecionador",
        },
        "direcao": {
            "nome": "Taverna Contemporânea",
            "posicionamento": "temático, artesanal, masculino",
            "atmosfera": "Mesa de taverna com madeira escura e luz baixa, onde "
                         "a textura de pedra da caneca é o centro.",
            "paleta": {
                "fundo":  {"nome": "Carvalho Escuro", "hex": "#3A2E24"},
                "painel": {"nome": "Areia Quente", "hex": "#D8CBB6"},
                "titulo": {"nome": "Grafite", "hex": "#221F1C"},
                "apoio":  {"nome": "Pedra Média", "hex": "#8C867D"},
                "acento": {"nome": "Bronze Fosco", "hex": "#8A6A3B"},
            },
            "materiais": ["madeira escura bruta", "couro envelhecido",
                          "pedra rústica", "ferro fosco"],
            "luz": "Luz lateral quente e baixa, sombras definidas.",
            "saturacao": "BAIXA",
            "props_preferidos": ["tábua de madeira", "pano de linho cru"],
            "props_proibidos": ["plástico colorido", "objeto moderno brilhante"],
            "risco_de_reflexo": "MEDIO",
            "trava_do_produto": "Resina cinza pedra texturizada com aro e "
                                "interior de aço inox escovado.",
        },
        "cor_foto": (140, 138, 132),
    },
    "porta_canetas": {
        "_porque": "Dourado metálico brilhante. É o unico com risco de reflexo "
                   "ALTO — se a instrução de reflexo não aparecer aqui, ela "
                   "não aparece em lugar nenhum.",
        "dados": {
            "nome_comercial": "Porta-Canetas Centurião Resina Dourada",
            "cor": "dourado escuro", "medidas": "18x11x9 cm", "peso": "640 g",
            "material": "Resina com acabamento metálico",
            "diferenciais": "Peça esculpida, acabamento dourado envelhecido",
            "caracteristicas": "Comporta até 6 canetas",
            "uso": "Organização de mesa de escritório",
        },
        "direcao": {
            "nome": "Executivo Quente Contemporâneo",
            "posicionamento": "premium, sofisticado, corporativo",
            "atmosfera": "Escritório executivo contido, onde o dourado escuro "
                         "é o único ponto de brilho.",
            "paleta": {
                "fundo":  {"nome": "Marfim Quente", "hex": "#F2EEE6"},
                "painel": {"nome": "Pedra Quente", "hex": "#D5C9B8"},
                "titulo": {"nome": "Grafite Espresso", "hex": "#292520"},
                "apoio":  {"nome": "Nogueira", "hex": "#695445"},
                "acento": {"nome": "Dourado Envelhecido", "hex": "#B18A4A"},
            },
            "materiais": ["nogueira escura", "travertino claro",
                          "couro marrom escuro"],
            "luz": "Quente-neutra, lateral suave, contraste médio.",
            "saturacao": "BAIXA",
            "props_preferidos": ["caderno fechado neutro", "caneta discreta"],
            "props_proibidos": ["superfície dourada grande", "papelaria colorida",
                                "planta grande"],
            "risco_de_reflexo": "ALTO",
            "trava_do_produto": "Resina dourada escura com acabamento "
                                "acetinado. Nunca dourado amarelo nem rosé.",
        },
        "cor_foto": (176, 138, 74),
    },
    "brinquedo": {
        "_porque": "Colorido, plástico brilhante, infantil. Inverte todos os "
                   "eixos dos outros três — é ele que mostra se o Presenteie "
                   "troca o par para pai e filho, e se a paleta muda de "
                   "verdade em vez de cair num padrão neutro.",
        "dados": {
            "nome_comercial": "Kit Marcadores de Taça Infantil 6 Cores",
            "cor": "multicolorido", "medidas": "8x6x1 cm", "peso": "45 g",
            "material": "Silicone atóxico",
            "diferenciais": "Seis cores vivas, silicone flexível",
            "caracteristicas": "6 unidades, formatos de animais",
            "uso": "Festa infantil, identificar copos",
        },
        "direcao": {
            "nome": "Festa Clara e Alegre",
            "posicionamento": "divertido, leve, familiar",
            "atmosfera": "Mesa de festa clara e luminosa, onde as seis cores "
                         "do produto são o único acento forte.",
            "paleta": {
                "fundo":  {"nome": "Branco Leitoso", "hex": "#FAFAF8"},
                "painel": {"nome": "Cinza Névoa", "hex": "#ECECE9"},
                "titulo": {"nome": "Azul Petróleo", "hex": "#1E3A44"},
                "apoio":  {"nome": "Cinza Quente", "hex": "#9C9892"},
                "acento": {"nome": "Coral Suave", "hex": "#E2705C"},
            },
            "materiais": ["vidro transparente", "mesa branca fosca",
                          "tecido de algodão claro"],
            "luz": "Luz natural alta e difusa, contraste baixo.",
            "saturacao": "MEDIA",
            "props_preferidos": ["taças de vidro", "guardanapo claro"],
            "props_proibidos": ["madeira escura", "cenário sombrio"],
            "risco_de_reflexo": "MEDIO",
            "trava_do_produto": "Silicone nas seis cores originais. Nenhuma "
                                "cor pode ser trocada ou unificada.",
        },
        "cor_foto": (226, 112, 92),
    },
}

# Ficam como nomes para o resto do arquivo continuar legível.
DADOS = PRODUTOS["album"]["dados"]
DIRECAO = PRODUTOS["album"]["direcao"]


def _plano_do_tipo(numero, rotulo):
    """O item de plano que a triagem devolveria para este tipo."""
    copy_por_tipo = {
        2: ["PRESERVA MEMÓRIAS: Folhas pretas protegem suas fotos",
            "CAPA DURÁVEL: Resistência que dura décadas",
            "ORGANIZAÇÃO PESSOAL: Espaço para cada momento",
            "PRESENTE PERFEITO: Álbum para compartilhar histórias"],
        3: ["REUNIR FAMÍLIAS: Momentos compartilhados que unem",
            "MEMÓRIA TANGÍVEL: Mais que arquivo, é relação"],
        4: ["TEXTURA FOSCA: Acabamento que se sente",
            "COSTURA FIRME: Encadernação que não solta"],
        5: ["ALTURA: 30 centímetros", "LARGURA: 30 centímetros",
            "ESPESSURA: 2 centímetros", "PESO: 501 gramas"],
        6: ["AS FOTOS CAEM?: Não, cantoneiras seguram cada uma",
            "AMARELA COM O TEMPO?: Não, papel livre de ácido",
            "CABE FOTO GRANDE?: Sim, até 20x25 centímetros"],
        7: ["Presenteie com memórias que duram"],
    }
    cena_por_tipo = {
        1: "Superfície branca pura, sombra suave dissolvida nas laterais.",
        2: "Superfície de linho claro, álbum aberto, câmera frontal.",
        3: "Sala de estar com luz de janela, sofá de tecido, álbum nas mãos.",
        4: "Madeira clara horizontal, ângulo zenital inclinado, recorte fechado.",
        5: "Superfície cinza claro fosca, sombra controlada, close meio-plano.",
        6: "Papel artesanal claro, álbum de pé, câmera em três quartos.",
        7: "Mesa de linho, embrulho de papel artesanal, duas pessoas.",
        8: "Estante de madeira clara com fotografias impressas ao redor.",
    }
    return {
        "numero": numero,
        "tipo": rotulo,
        "composicao": f"Composição planejada para a peça {numero}.",
        "cena": cena_por_tipo.get(numero, ""),
        "textos": copy_por_tipo.get(numero, []),
        "flags": [],
        "viavel": True,
        "pergunta_info": "",
    }


# ── Os cenários ─────────────────────────────────────────────────────────────
#
# Cada um muda UMA coisa em relação ao completo. Mudar duas de uma vez faz o
# arquivo parar de responder a pergunta "o que esta variação causa".
CENARIOS = {
    "01_completo":
        "Tudo preenchido: direção de arte herdada, plano com copy e cena, "
        "dados técnicos completos. É a referência — os outros se comparam com "
        "este.",
    "02_sem_direcao_de_arte":
        "Plano antigo, sem direção. Cada peça volta a deduzir a paleta. O que "
        "NÃO pode: a ordem de deduzir e a direção herdada aparecerem juntas.",
    "03_sem_plano_de_triagem":
        "Geração avulsa, sem plano. Não pode haver bloco de TEXTO EXATO nem "
        "cena, e o gerador volta a escrever a copy — é o caminho que produziu "
        "'Portátile'.",
    "04_sem_dados_tecnicos":
        "Sem medidas e sem peso. O tipo 5 não pode inventar número nenhum.",
    "05_sem_fotos_do_produto":
        "Sem foto. A SEÇÃO 2 troca de referência visual para descrição em "
        "texto — é o caminho onde nasceu o 'aquecedor vermelho'.",
    "06_com_instrucoes_do_colaborador":
        "Instrução escrita por quem vende. Nos tipos padrão é CONTEXTO "
        "INTERNO (não vira texto na imagem); no Personalizado é ordem visual.",
    "07_com_tema_de_ambientacao":
        "Tema escrito pelo colaborador. É TEMA, não roteiro: as oito não "
        "podem repetir a mesma cena.",
    "08_com_referencia_de_layout":
        "Referência de layout por nome de arquivo. Só a composição se copia — "
        "nunca o produto, a cor ou o texto dela.",
    "09_copy_acima_do_teto":
        "A triagem escreveu mais blocos do que o tipo comporta. A copy tem de "
        "ser cortada no teto, e o prompt não pode trazer dois números "
        "diferentes de blocos.",
    "10_rotulo_inventado_pela_ia":
        "A triagem renomeou o tipo ('Foto editorial — ambientação realista'). "
        "O prompt tem de sair idêntico ao do rótulo oficial.",
}


def _monta(imagem, tipo, cenario, numero, produto="album"):
    """(brief em português, prompt que iria ao motor) daquele cenário."""
    perfil = PRODUTOS[produto]
    dados = dict(perfil["dados"])
    plano = _plano_do_tipo(numero, tipo)
    direcao = dict(perfil["direcao"])
    fotos = [_foto(perfil["cor_foto"]), _foto((90, 90, 95))]
    instrucoes = ""
    ambientacao = ""
    refs_nomes = []
    refs_bytes = None
    tipo_usado = tipo

    if cenario == "02_sem_direcao_de_arte":
        direcao = {}
    elif cenario == "03_sem_plano_de_triagem":
        plano = None
    elif cenario == "04_sem_dados_tecnicos":
        dados.pop("medidas", None)
        dados.pop("peso", None)
    elif cenario == "05_sem_fotos_do_produto":
        fotos = []
    elif cenario == "06_com_instrucoes_do_colaborador":
        instrucoes = "O álbum é vendido para casais em aniversário de casamento."
    elif cenario == "07_com_tema_de_ambientacao":
        ambientacao = "sala de estar afetiva, fim de tarde, fotografias espalhadas"
    elif cenario == "08_com_referencia_de_layout":
        refs_nomes = [f"{tipo.split(' — ')[0]} referencia.webp"]
        refs_bytes = [_foto((240, 240, 235))]
    elif cenario == "09_copy_acima_do_teto":
        if plano:
            plano = dict(plano)
            plano["textos"] = [f"BLOCO {k}: frase de teste número {k}"
                               for k in range(1, 9)]
    elif cenario == "10_rotulo_inventado_pela_ia":
        apelidos = {1: "Capa em Fundo Branco", 2: "Imagem de marketing — benefícios",
                    3: "Produto no ambiente de uso real", 4: "Detalhe: Costura",
                    5: "Infográfico técnico de medidas", 6: "Quebra de objeção",
                    7: "Imagem emocional — presentear",
                    8: "Foto editorial — ambientação realista"}
        if numero in apelidos:
            plano = dict(plano or {})
            plano["tipo"] = apelidos[numero]
            plano["numero"] = numero
            tipo_usado = imagem.tipo_canonico(plano, imagem.TIPOS_PADRAO)

    pt = imagem.montar_prompt_imagem(
        tipo_usado, instrucoes, dados, perfil["dados"]["nome_comercial"],
        refs_layout_nomes=refs_nomes, instrucao_layout="",
        plano_triagem=plano, ambientacao=ambientacao,
        direcao_arte=direcao,
    )
    en = imagem.prompt_que_sera_enviado(
        pt, fotos, refs_layout=refs_bytes, refs_layout_nomes=refs_nomes,
        tipo=tipo_usado)
    return pt, en


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--saida", default="prompts_teste",
                    help="pasta onde escrever (padrão: ./prompts_teste)")
    ap.add_argument("--cenario", action="append",
                    help="só este cenário (pode repetir)")
    ap.add_argument("--produto", action="append",
                    help="qual produto usar (pode repetir; 'todos' para os "
                         "quatro). Padrão: album")
    ap.add_argument("--listar", action="store_true",
                    help="lista os cenários e os produtos, e sai")
    args = ap.parse_args()

    if args.listar:
        print("CENÁRIOS — cada um isola UMA variação:\n")
        for nome, desc in CENARIOS.items():
            print(f"  {nome}\n      {desc}\n")
        print("PRODUTOS — escolhidos para discordarem entre si:\n")
        for nome, perfil in PRODUTOS.items():
            print(f"  {nome}  ({perfil['dados']['nome_comercial']})")
            print(f"      {perfil['_porque']}\n")
        return 0

    _calar_streamlit()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import imagem

    # A leitura de visão é trocada: aqui não há produto real, e o que se
    # confere é a MONTAGEM. Trocar isto também garante que nada saia para a
    # rede e que dois cenários iguais deem textos iguais.
    imagem._descricao_do_produto_cacheada = lambda *a, **k: (
        "Álbum de fotos quadrado com capa dura preta fosca, lombada costurada "
        "e folhas internas pretas.",
        "Layout de duas colunas: produto à esquerda, blocos de texto "
        "empilhados à direita, margens generosas.",
    )
    imagem._get_openai_api_key = lambda: "sk-teste-sem-rede"

    alvos = args.cenario or list(CENARIOS)
    desconhecidos = [c for c in alvos if c not in CENARIOS]
    if desconhecidos:
        print("cenário não existe: " + ", ".join(desconhecidos))
        print("use --listar para ver os nomes")
        return 1

    produtos = args.produto or ["album"]
    if "todos" in produtos:
        produtos = list(PRODUTOS)
    desconhecidos = [p for p in produtos if p not in PRODUTOS]
    if desconhecidos:
        print("produto não existe: " + ", ".join(desconhecidos))
        print("use --listar para ver os nomes")
        return 1

    os.makedirs(args.saida, exist_ok=True)
    indice = ["# Prompts de teste — o que é cada arquivo",
              "",
              "Gerado por `gerar_prompts_teste.py`. **Nenhuma imagem foi "
              "gerada e nenhum motor foi chamado.**",
              "",
              "O contrato de cada seção — o que TEM de estar e o que NÃO PODE "
              "— está em `DOSSIE_PROMPT.md`.",
              ""]
    total = 0
    for produto in produtos:
        indice += [f"# Produto: {PRODUTOS[produto]['dados']['nome_comercial']}",
                   "", f"_{PRODUTOS[produto]['_porque']}_", ""]
        for cenario in alvos:
            pasta = os.path.join(args.saida, produto, cenario)
            os.makedirs(pasta, exist_ok=True)
            indice += [f"## {produto} / {cenario}", "", CENARIOS[cenario], "",
                       "| arquivo | tipo | caracteres |", "|---|---|---|"]
            tipos = list(imagem.TIPOS_PADRAO) + ["Personalizado (descrevo o que quero)"]
            for n, tipo in enumerate(tipos, 1):
                numero = n if n <= 8 else 0
                try:
                    pt, en = _monta(imagem, tipo, cenario, numero, produto)
                except Exception as e:
                    print(f"FALHA  {produto} / {cenario} / {tipo}: "
                          f"{type(e).__name__}: {e}")
                    return 1
                base = (f"{numero if numero else 'P'}_"
                        f"{imagem._chave_tipo(tipo)[:24].replace(' ', '_')}")
                io.open(os.path.join(pasta, base + "_pt.txt"), "w",
                        encoding="utf-8").write(pt)
                io.open(os.path.join(pasta, base + "_ENVIADO.txt"), "w",
                        encoding="utf-8").write(en)
                indice.append(f"| `{produto}/{cenario}/{base}_ENVIADO.txt` "
                              f"| {tipo} | {len(en)} |")
                total += 1
            indice.append("")

    io.open(os.path.join(args.saida, "_INDICE.md"), "w",
            encoding="utf-8").write("\n".join(indice) + "\n")
    print(f"ok    {total} prompts · {len(produtos)} produto(s) × "
          f"{len(alvos)} cenário(s) × 9 tipos, em '{args.saida}/'")
    print(f"      leia '{args.saida}/_INDICE.md' primeiro")
    print("      o arquivo que importa é o _ENVIADO.txt — o _pt.txt é o brief "
          "de onde ele nasce")
    return 0


if __name__ == "__main__":
    sys.exit(main())
