"""favorecidos.py — o que cada nome do extrato significa, dito uma vez.

O PROBLEMA
----------
O extrato diz PARA QUEM o dinheiro foi, e nada sobre o que aquilo é. "Vanda
Maria Martinez" é estacionamento; "Katia Sola de Araujo" é a faxineira das
salas; "APEXIMP" é mercadoria; "MAREE INSTITUICAO DE PAGAMENTO" é repasse da
Shopee. Nenhuma dessas respostas está no arquivo — todas estão na cabeça do
dono, e é por isso que a classificação era manual, mês após mês, nas mesmas
52 linhas.

Aqui cada nome é classificado UMA vez. No mês seguinte, as 16 linhas da
APEXIMP já entram como mercadoria.

A ARMADILHA QUE ESTE MÓDULO EVITA
---------------------------------
Entrada com o nome da própria empresa NÃO é transferência entre contas: no
extrato do Inter, "Pix recebido - LITTLE GLASS COMERCIO" é repasse do MERCADO
LIVRE, e "MAREE INSTITUICAO DE PAGAMENTO" é a SHOPEE. Quem lê o nome e conclui
"dinheiro meu indo de uma conta para outra" tira 30 mil de faturamento do mês
— foi o que eu conclui antes de o dono mostrar a coluna FINALIDADE dele.

Por isso a origem da entrada é cadastro, e não dedução pelo nome.

ONDE MORA
---------
Na aba `favorecidos` da planilha, como todo cadastro deste projeto. O SEED
abaixo é o que o dono já classificou à mão no extrato de agosto/2026, e serve
só para a primeira carga — depois quem manda é a planilha.
"""

from datetime import datetime, timezone, timedelta

import streamlit as st

ABA_NOME = "favorecidos"
COLUNAS = ["favorecido", "finalidade", "tipo", "observacao",
           "atualizado_em", "atualizado_por"]

FUSO = timezone(timedelta(hours=-3))

# saida  -> consome a meta de gastos
# entrada -> é dinheiro entrando, e `finalidade` diz de qual plataforma
TIPOS = ("saida", "entrada")

# O que o dono classificou à mão na coluna FINALIDADE do extrato de agosto.
# Primeira carga apenas: depois a planilha manda, e mudar aqui não muda nada.
SEED = [
    ("APEXIMP", "MERCADORIA", "saida", ""),
    ("Apeximp Comercio de Presentes Importacao E Exportacao LTDA",
     "MERCADORIA", "saida", ""),
    ("LEXTACK COMERCIO DE PRESENTES LTDA", "MERCADORIA", "saida", ""),
    ("PLASTICOS NOVA FENIX", "EMBALAGEM", "saida", ""),
    ("ER EMBALAGENS", "EMBALAGEM", "saida", ""),
    ("Nzb Comercio de Embalagens LTDA", "EMBALAGEM", "saida", ""),
    # Os dois custos fixos que saem pela conta do Inter, ditos pelo dono.
    ("RECEITA FEDERAL", "CUSTO FIXO", "saida",
     "DAS do Simples Nacional, pago no Pix quando não sai o código do boleto"),
    ("Vanda Maria Martinez", "ESTACIONAMENTO", "saida",
     "Estacionamento fixo da empresa"),
    ("Katia Sola de Araujo", "SERVIÇO", "saida", "Faxineira das salas"),
    ("PIX Marketplace", "SERVIÇO", "saida", "Frete de produto vendido no site"),
    ("Renan Candido Sousa", "MERCADORIA", "saida",
     "Pagou mercadoria com dinheiro dele e se reembolsa"),
    ("ESPETARIA IBITIRAMA COMERCIO DE ALIMENTOS LTDA", "OUTROS", "saida", ""),
    ("SUPERMERCADO DA PRACA IBITIRAMA LTDA", "OUTROS", "saida", ""),
    ("ESFIHARIA POLY", "OUTROS", "saida", ""),
    ("OBA HORTIFRUTI", "OUTROS", "saida", ""),
    ("VINDI PAGAMENTOS ONLINE", "CUSTO FIXO", "saida", ""),
    # Entradas: o nome não diz a plataforma, e deduzir pelo nome é o erro.
    ("MAREE INSTITUICAO DE PAGAMENTO LTDA", "SHOPEE", "entrada", ""),
    ("LITTLE GLASS COMERCIO DE AROMATIZADORES E PRODUTOS LTDA",
     "MERCADO LIVRE", "entrada", "Repasse, não transferência entre contas"),
    ("MARTINS E SOUSA COMERCIO DE PRODUTOS IMPORTADOS E NACIONAIS LTDA",
     "MERCADO LIVRE", "entrada", "Repasse, não transferência entre contas"),
    # Fornecedores de mercadoria, ditos pelo dono em 17/09. Os nomes chineses
    # ele deu como certos; o resto da fila de agosto veio como "provavelmente
    # tudo compra de mercadoria" — entra classificado, com a duvida escrita na
    # observacao em vez de virar uma certeza que ninguem checou.
    ("Jie Meng", "MERCADORIA", "saida", ""),
    ("Yuefu Pan", "MERCADORIA", "saida", ""),
    ("Xiaoyue Jiang", "MERCADORIA", "saida", ""),
    ("Xiao Xu", "MERCADORIA", "saida", ""),
    ("AIJIN ZHANG", "MERCADORIA", "saida", ""),
    ("PAN ZHENGZHONG", "MERCADORIA", "saida", ""),
    ("MAGB", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("ELISEO VARIEDADES", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("AGE UNDERWEAR", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("ADRIANA BIJOUTERIAS  ARMARINHOS", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("STARJET CARRINHOS ESCOLARES", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("JB PEREIRA MERCADO E DISTRIBUIDORA", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("Efrain Noe Apaza Mamani", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("Jovane dos Reis", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("GUILHERME AUGUSTO BERTOLINI", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("Henrique Francabandiera da Silva", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("Ana Carla Conceicao dos Santos", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("Ana Beatriz Batista Bonates", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("Robson Cavalcanti Ramos 94274770168", "ESTACIONAMENTO", "saida",
     "Estacionamento fixo da empresa"),
    ("62108197 EDNARIA ALVES DA CONCEICAO", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("57118099 JOSE AIRTON GOMES DE SA", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("Beatriz Falconi", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("VALDEMIR SILVA SANTOS", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("Flavio Adriano Rodrigues", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("MYRELLA CANDIDO", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("Lucas Porto Leite", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("JAILSON NUNES DE OLIVEIRA 88310892500", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("Wilyan Nicanor Accioli da Silva", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("Andre de Almeida Ferreira", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("Cleudio Pereira", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("Monique Sola Araujo de Sousa", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("Cleiton Costabile Martorano", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("MANOEL PEDROSA CAVALCANTE", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("SEM TITULO", "MERCADORIA", "saida", "provável — classificado em bloco, confirmar"),
    ("AIBR INSTITUICAO DE PAGAMENTO LTDA", "OUTROS", "saida", ""),
    # A conta que a Shopee paga (Inter 167513915) e so passagem: entra o
    # repasse e sai para a Little Glass no mesmo valor, no mesmo dia. Aqui
    # LITTLE GLASS no sentido SAIDA e transferencia — na conta da rua, o mesmo
    # nome no sentido ENTRADA e repasse do Mercado Livre.
    ("LITTLE GLASS", "TRANSFERENCIA ENTRE CONTAS", "saida",
     "Repasse da Shopee sendo passado para a conta da Little Glass"),
    ("F CARNEIRO CIA LTDA", "SHOPEE", "entrada", ""),
    ("MODA MUNDIAL BRASIL", "SHEIN", "entrada", "Instituição de pagamento da Shein"),
    ("MODA MUNDIAL BRASIL PAGAMENTOS LTDA", "SHEIN", "entrada", ""),
    ("MODA MUNDIAL BRASIL INTERMED", "SHEIN", "entrada", ""),
    # O MESMO dinheiro chega com outro nome em cada banco. No Inter o repasse
    # vem como "MARTINS E SOUSA COMERCIO DE PRODUTOS IMPORTADOS E NACIONAIS
    # LTDA"; no Itaú, como "MARTINSOUSA". A chave normalizada não junta os
    # dois — um não é começo do outro —, e sem estas linhas o dono responderia
    # de novo o que já respondeu.
    ("MARTINSOUSA", "MERCADO LIVRE", "entrada", "Repasse, como no Inter"),
    ("LITTLE GLASS COMERCIO DE ARO", "MERCADO LIVRE", "entrada", ""),
    # DAS do Simples: no Inter sai como RECEITA FEDERAL, no Itaú como
    # PAGAMENTOS / SIMPLES NACIONAL. Mesmo imposto, mesma finalidade.
    ("SIMPLES NACIONAL", "CUSTO FIXO", "saida", "DAS do Simples Nacional"),
    # Ditos pelo dono em 17/09, lendo a fila do extrato do Itaú.
    ("GRUPO GARCIA IMOBILIARIA", "CUSTO FIXO", "saida", "Aluguel"),
    ("SIMONE MARIA DOS SANTOS", "MERCADORIA", "saida", ""),
    ("IMPORIENTE COMERCIO EXTERIOR LTDA", "MERCADORIA", "saida", ""),
    ("POLICARGO SERVICE", "MERCADORIA", "saida", ""),
    ("MYRELLA DE SOUZA CANDIDO", "FOLHA", "saida", "Salário"),
    ("ELIANE MARTINS DA SILVA BESERRA", "CONSUMO INTERNO", "saida",
     "Compra da TV da empresa"),
    # O Vagner aparece nos dois sentidos, e sao coisas diferentes: saindo e
    # compra de mercadoria, entrando e a parte dele na parcela do PRONAMP.
    ("VAGNER LAZARINI BESERRA", "MERCADORIA", "saida", ""),
    ("VAGNER LAZARINI BESERRA", "REEMBOLSO PRONAMP", "entrada", ""),
    ("RICCI E RICCI COMERCIO E INDUSTRIA", "CUSTO FIXO", "saida", "Anvisa"),
    ("VALDILENE DA SILVA COELHO", "CUSTO FIXO", "saida",
     "Aluguel da sala onde fica o plástico bolha"),
    ("ROBSON SOUSA DOS SANTOS", "ESTACIONAMENTO", "saida",
     "Estacionamento fixo da empresa"),
    ("LEONARDO MARTINS BESERRA", "REEMBOLSO", "entrada", ""),
    ("BYTEDANCE BRASIL TECNOLOGIA LTDA", "TIKTOK", "entrada",
     "Repasse do TikTok Shop"),
    # Flex: transporte da mercadoria até o Full. Aparece como boleto pago à TM
    # Logistica e, na conta da MS, como SISPAG FORNECEDORES sem nome nenhum.
    ("TM LOGISTICA", "FLEX", "saida", "Transporte da mercadoria até o Full"),
    ("SISPAG FORNECEDORES", "FLEX", "saida", "TM Logistica"),
    # O extrato do Itaú não traz favorecido nestas: o nome está só na
    # descrição, e sem elas a linha fica dependendo de quem clicou primeiro.
    ("SISPAG SALARIOS", "FOLHA", "saida", ""),
    ("TAR CHEQUE EMITIDO", "TARIFA BANCÁRIA", "saida", ""),
    # ── Fatura do cartao do Inter, anotada pelo dono em 17/09 ────────────
    # Ele marcou alguns e mandou aplicar aos semelhantes. Os semelhantes
    # ficam explicitos aqui: "aplicar ao parecido" nao pode virar regra de
    # adivinhacao, senao a proxima loja de nome parecido entra classificada
    # errada e ninguem ve.
    ("ZUL", "ESTACIONAMENTO", "saida",
     "Zona azul que o Renan paga ao sair para comprar mercadoria"),
    ("VINDI TRAYECOMMERCE", "SERVIÇO", "saida", "Plataforma da loja"),
    ("UBER", "SERVIÇO", "saida", ""),
    ("UBER ONE", "SERVIÇO", "saida", ""),
    ("DL UBERRIDES", "SERVIÇO", "saida", ""),
    ("APPLE COM", "SERVIÇO", "saida", ""),
    ("MICROSOFT MICROSOFT", "SERVIÇO", "saida", ""),
    ("EBN", "SERVIÇO", "saida", "Canva"),
    ("MERCADOLIVRE", "CONSUMO INTERNO", "saida", ""),
    ("MERCADOLIVRE MERCADOL", "CONSUMO INTERNO", "saida", ""),
    ("MERCADO RASTREAMENTOA", "CONSUMO INTERNO", "saida", ""),
    ("MERCADO FENIXOFFICE", "CONSUMO INTERNO", "saida", ""),
    ("Debito titulo KG", "NÃO OPERACIONAL", "saida", ""),
    # O extrato do Itaú rotula errado, e o rótulo dele é o que engana: os
    # R$ 170.000 de "PAGAMENTOS A FORNECEDORES" foram transferidos para a outra
    # conta do Itaú e investidos. Deixados como gasto, sozinhos estouravam a
    # meta do mês.
    ("PAGAMENTOS A FORNECEDORES", "TRANSFERENCIA ENTRE CONTAS", "saida",
     "Transferência para a outra conta do Itaú, investida lá"),
    ("RECEBIMENTOS", "TRANSFERENCIA ENTRE CONTAS", "entrada",
     "A mesma transferência chegando"),
    # PRONAMP: 170 mil numa conta e 100 mil na outra, para suprir as
    # contratações e os custos por um período. É dívida entrando, não receita —
    # somada ao faturamento, inventaria um mês recorde que não existiu.
    ("EMPREST CAPITAL DE GIRO", "EMPRESTIMO PRONAMP", "entrada",
     "Dívida entrando, não faturamento"),
    ("PARCELA GIRO", "NÃO OPERACIONAL", "saida", "Parcela de PRONAMP"),
    # O Vagner (VLB ONLINE) paga parte da parcela de um dos PRONAMPs. É
    # ABATIMENTO da parcela, não faturamento: somado à receita, inventaria
    # venda que não houve e ainda deixaria o não operacional cheio demais.
    ("VLB ONLINE LTDA", "REEMBOLSO PRONAMP", "entrada",
     "Vagner paga parte da parcela de um dos PRONAMPs"),
    ("VLB ONL", "REEMBOLSO PRONAMP", "entrada", ""),
    ("APLICACAO CDB DI", "APLICACAO", "saida", ""),
    ("RENDIMENTOS REND PAGO APLIC", "APLICACAO", "entrada", ""),
]


def chave(nome):
    """A forma comparável de um favorecido.

    O mesmo fornecedor aparece como "APEXIMP" e "Apeximp Comercio de Presentes
    Importacao E Exportacao LTDA"; sem normalizar, viram dois cadastros e o
    total do mês sai partido em dois.
    """
    import re
    import unicodedata
    t = str(nome or "").strip().upper()
    if not t:
        return ""
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"\b(LTDA|ME|EPP|SA|S/A|EIRELI|COMERCIO|DE|DA|DO|E)\b", " ", t)
    t = re.sub(r"[^A-Z0-9 ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# Finalidades que NÃO consomem a meta de gastos. Dinheiro indo de uma conta
# nossa para outra não é despesa: contá-lo dobraria o gasto do mês e faria a
# meta estourar sozinha.
NAO_CONSOME_META = {"TRANSFERENCIA ENTRE CONTAS", "TRANSFERENCIA", "APLICACAO",
                    "RESGATE"}

# Entradas que NÃO são faturamento. Elas abatem um custo ou são dívida
# entrando; somadas à receita, inventam venda que não houve.
NAO_E_FATURAMENTO = {"TRANSFERENCIA ENTRE CONTAS", "TRANSFERENCIA",
                     "EMPRESTIMO PRONAMP", "REEMBOLSO PRONAMP", "APLICACAO",
                     "RATEIO CUSTO FIXO"}


def eh_faturamento(finalidade):
    """Esta entrada é venda? Empréstimo, rateio e reembolso não são."""
    return str(finalidade or "").strip().upper() not in NAO_E_FATURAMENTO


def consome_meta(finalidade):
    """Este lançamento consome a meta de gastos?"""
    return str(finalidade or "").strip().upper() not in NAO_CONSOME_META


def _aba():
    import gspread
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        return planilha.worksheet(ABA_NOME)
    except gspread.WorksheetNotFound:
        nova = planilha.add_worksheet(title=ABA_NOME, rows=400,
                                      cols=len(COLUNAS))
        nova.append_row(COLUNAS, value_input_option="RAW")
        nova.append_rows(
            [[f, fin, tp, obs, "", "seed"] for f, fin, tp, obs in SEED],
            value_input_option="RAW")
        return nova


@st.cache_data(ttl=300)
def carregar():
    """{(chave, tipo): {...}} — o SEED por baixo, a planilha por cima.

    O SEED entra SEMPRE, e não só quando a aba nasce. Esse era o furo: a aba
    foi criada na primeira subida de extrato, com o cadastro daquele instante,
    e toda resposta que o dono deu depois ficou no código sem nunca chegar à
    planilha — a tela continuava perguntando o que ele já tinha respondido.

    A planilha vence o SEED em cima da mesma chave, e é isso que mantém a
    correção feita à mão de pé: quem edita na tela está corrigindo o código.

    Falha de leitura não zera nada: o SEED responde sozinho, e o que se perde é
    só o que o dono cadastrou pela tela.
    """
    fora = {(chave(f), tp): {"favorecido": f, "finalidade": fin, "tipo": tp,
                             "observacao": o}
            for f, fin, tp, o in SEED if chave(f)}
    try:
        registros = _aba().get_all_records()
    except Exception:
        return fora
    for linha in registros:
        nome = str(linha.get("favorecido", "") or "").strip()
        k = chave(nome)
        if not k:
            continue
        tp = str(linha.get("tipo", "") or "").strip().lower()
        fora[(k, tp if tp in TIPOS else None)] = {
            "favorecido": nome,
            "finalidade": str(linha.get("finalidade", "") or "").strip(),
            "tipo": tp or "",
            "observacao": str(linha.get("observacao", "") or "").strip(),
        }
    return fora


def casar(nome, cadastro, sentido=None):
    """O cadastro que corresponde a este nome. None quando não há.

    `sentido` ("saida"/"entrada") faz parte da identidade, e não é detalhe: na
    conta da rua, "Pix RECEBIDO de LITTLE GLASS" é repasse do Mercado Livre;
    na conta que a Shopee paga, "Pix ENVIADO para LITTLE GLASS" é transferência
    entre contas nossas. Mesmo nome, dois significados opostos — um é receita,
    o outro não é nem gasto.

    Primeiro a chave exata. Depois, o prefixo: o mesmo fornecedor aparece como
    "APEXIMP" e como "Apeximp Comercio de Presentes Importacao E Exportacao
    LTDA", e normalizar não junta os dois — um é começo do outro, não o mesmo
    texto.

    O prefixo só vale quando UM candidato casa. Com dois, o nome é ambíguo
    ("ER EMBALAGENS" e "ER TRANSPORTES" começam igual), e classificar um como
    o outro seria erro que ninguém vê: o total do mês fica certo, e a
    finalidade, errada.
    """
    k = chave(nome)
    if not k:
        return None
    # Do mais específico para o mais geral: o cadastro do sentido certo manda;
    # sem ele, vale o cadastro sem sentido declarado.
    for alvo in ((k, sentido), (k, None)) if sentido else ((k, None),):
        if alvo in cadastro:
            return cadastro[alvo]
    if sentido:
        iguais = [v for (ck, st), v in cadastro.items()
                  if ck == k and st in (sentido, None)]
        if iguais:
            return iguais[0]
    candidatos = [v for (ck, st), v in cadastro.items()
                  if len(ck) >= 4 and st in (sentido, None)
                  and (k.startswith(ck + " ") or ck.startswith(k + " "))]
    return candidatos[0] if len(candidatos) == 1 else None


def classificar(lancamentos, cadastro=None):
    """Põe `finalidade` em cada lançamento. Devolve (classificados, faltando).

    `faltando` é a lista de nomes sem cadastro, do maior valor para o menor —
    é a fila de trabalho do dono, e ela encurta a cada mês.
    """
    cad = carregar() if cadastro is None else cadastro
    fora, faltando = [], {}
    for l in (lancamentos or []):
        # O Itaú não traz favorecido em tudo: "PAGAMENTOS A FORNECEDORES" e
        # "EMPREST CAPITAL DE GIRO" só existem como descrição. Sem esta
        # reserva, as duas linhas mais pesadas do mês ficavam sem classificação.
        nome = (l.get("favorecido") or l.get("razao_social")
                or l.get("descricao") or "")
        sentido = l.get("sentido") or ("saida" if float(l.get("valor") or 0) < 0
                                       else "entrada")
        reg = casar(nome, cad, sentido)
        novo = dict(l)
        # Finalidade que o lançamento JÁ trazia não é apagada.
        #
        # Ela vem de duas fontes legítimas: o tipo que o próprio extrato
        # resolve (cheque, folha, fatura) e a anotação que o dono escreveu no
        # arquivo. Apagá-la aqui mandava para a fila 49 linhas que o sistema
        # entendia sozinho — e a fila é justamente o que se quer curto.
        ja_tinha = str(l.get("finalidade") or "").strip()
        novo["finalidade"] = (reg["finalidade"] if reg else ja_tinha)
        novo["classificado"] = bool(reg) or bool(ja_tinha)
        fora.append(novo)
        if not novo["classificado"] and nome:
            d = faltando.setdefault(nome, {"n": 0, "total": 0.0})
            d["n"] += 1
            d["total"] += abs(float(l.get("valor") or 0))
    fila = sorted(({"favorecido": k, **v} for k, v in faltando.items()),
                  key=lambda x: -x["total"])
    return fora, fila


def salvar(favorecido, finalidade, tipo="saida", observacao="", usuario=""):
    """Grava ou atualiza a classificação de um nome. (ok, mensagem)."""
    nome = str(favorecido or "").strip()
    if not nome or not str(finalidade or "").strip():
        return False, "Favorecido e finalidade são obrigatórios."
    agora = datetime.now(FUSO).strftime("%Y-%m-%d %H:%M")
    linha = [nome, str(finalidade).strip().upper(),
             (tipo if tipo in TIPOS else "saida"),
             str(observacao or "")[:200], agora, str(usuario or "")[:60]]
    try:
        aba = _aba()
        alvo = chave(nome)
        atuais = aba.get_all_records()
        pos = next((i for i, l in enumerate(atuais)
                    if chave(l.get("favorecido")) == alvo), None)
        if pos is None:
            aba.append_row(linha, value_input_option="RAW")
        else:
            fim = chr(ord("A") + len(COLUNAS) - 1)
            aba.update(f"A{pos + 2}:{fim}{pos + 2}", [linha],
                       value_input_option="RAW")
    except Exception as e:
        return False, str(e)[:200]
    carregar.clear()
    return True, f"{nome} → {finalidade}."


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    # O mesmo fornecedor com duas redacoes tem que virar um cadastro so.
    # A chave NAO junta "APEXIMP" com a razao social inteira — um e comeco do
    # outro, nao o mesmo texto. Quem junta e `casar`, e so quando nao ha duvida.
    ok("a chave tira ltda, comercio e conectivos",
       chave("ER EMBALAGENS LTDA") == "ER EMBALAGENS")
    ok("caixa e acento nao criam cadastro novo",
       chave("Plásticos Nova Fênix") == chave("PLASTICOS NOVA FENIX"))
    ok("pontuacao nao separa",
       chave("VINDI PAGAMENTOS ONLINE.") == chave("Vindi Pagamentos Online"))
    ok("nome vazio nao vira chave", chave("") == "" and chave(None) == "")
    # Dois fornecedores diferentes nao podem colidir.
    ok("nomes diferentes continuam diferentes",
       chave("ER EMBALAGENS") != chave("NZB EMBALAGENS"))

    CAD = {(chave(f), tp): {"favorecido": f, "finalidade": fin, "tipo": tp,
                            "observacao": o} for f, fin, tp, o in SEED}
    LANC = [
        {"favorecido": "APEXIMP", "valor": -1303.00},
        {"favorecido": "Apeximp Comercio de Presentes  Importacao E Exportacao LTDA",
         "valor": -1372.44},
        {"favorecido": "MAREE INSTITUICAO DE PAGAMENTO LTDA", "valor": 2181.29},
        # Nomes que NAO estao no SEED de proposito: e a fila que se confere.
        {"favorecido": "LOJA QUE NUNCA APARECEU", "valor": -200.00},
        {"favorecido": "FORNECEDOR NOVO", "valor": -190.00},
        {"favorecido": "FORNECEDOR NOVO", "valor": -186.00},
    ]
    ok("nome curto casa com a razao social inteira",
       casar("Apeximp Comercio de Presentes Importacao E Exportacao LTDA",
             {(chave("APEXIMP"), "saida"): {"finalidade": "MERCADORIA"}},
             "saida")["finalidade"] == "MERCADORIA")
    ok("dois candidatos com o mesmo comeco NAO sao casados no chute",
       casar("ER ALGUMA COISA",
             {(chave("ER EMBALAGENS"), "saida"): {"finalidade": "A"},
              (chave("ER TRANSPORTES"), "saida"): {"finalidade": "B"}},
             "saida") is None)
    ok("prefixo curto demais nao casa",
       casar("JB PEREIRA", {(chave("JB"), "saida"): {"finalidade": "X"}},
             "saida") is None)

    # O caso que motivou a chave composta: mesmo nome, sentidos opostos.
    _DOIS = {(chave("LITTLE GLASS"), "entrada"): {"finalidade": "MERCADO LIVRE"},
             (chave("LITTLE GLASS"), "saida"):
                 {"finalidade": "TRANSFERENCIA ENTRE CONTAS"}}
    ok("recebido da Little Glass e repasse do Mercado Livre",
       casar("LITTLE GLASS COMERCIO", _DOIS, "entrada")["finalidade"]
       == "MERCADO LIVRE")
    ok("enviado para a Little Glass e transferencia entre contas",
       casar("LITTLE GLASS", _DOIS, "saida")["finalidade"]
       == "TRANSFERENCIA ENTRE CONTAS")
    ok("transferencia nao consome a meta de gastos",
       not consome_meta("TRANSFERENCIA ENTRE CONTAS")
       and consome_meta("MERCADORIA"))
    # As duas linhas mais pesadas de agosto nao tem favorecido nenhum: o nome
    # esta so na descricao, e e la que a classificacao tem que ir procurar.
    _ITAU = [{"descricao": "PAGAMENTOS A FORNECEDORES", "valor": -170000.0},
             {"descricao": "EMPREST CAPITAL DE GIRO", "valor": 172029.0}]
    _ci, _fi = classificar(_ITAU, CAD)
    ok("o Itau sem favorecido e classificado pela descricao",
       _ci[0]["finalidade"] == "TRANSFERENCIA ENTRE CONTAS"
       and _ci[1]["finalidade"] == "EMPRESTIMO PRONAMP")
    ok("os 170 mil de transferencia NAO consomem a meta",
       not consome_meta(_ci[0]["finalidade"]))
    ok("nada ficou na fila", _fi == [])
    # Entrada que nao e venda: divida, rateio e reembolso entram na conta
    # errada se forem somados ao faturamento.
    ok("PRONAMP e reembolso nao sao faturamento",
       not eh_faturamento("EMPRESTIMO PRONAMP")
       and not eh_faturamento("REEMBOLSO PRONAMP")
       and not eh_faturamento("RATEIO CUSTO FIXO"))
    ok("repasse de plataforma e faturamento",
       eh_faturamento("MERCADO LIVRE") and eh_faturamento("SHOPEE"))

    _c, _fila = classificar(LANC, CAD)
    ok("as duas redacoes da Apeximp saem como MERCADORIA",
       _c[0]["finalidade"] == "MERCADORIA" and _c[1]["finalidade"] == "MERCADORIA")
    ok("entrada da Shopee e reconhecida, e nao vira transferencia",
       _c[2]["finalidade"] == "SHOPEE")
    # O erro que este modulo existe para impedir.
    ok("repasse do ML chega com o nome da empresa e NAO e transferencia",
       CAD[(chave("LITTLE GLASS COMERCIO DE AROMATIZADORES E PRODUTOS LTDA"),
            "entrada")]["finalidade"] == "MERCADO LIVRE")
    ok("quem nao tem cadastro fica sem finalidade, e nao com um chute",
       _c[3]["finalidade"] == "" and _c[3]["classificado"] is False)
    ok("a fila vem do maior para o menor",
       [x["favorecido"] for x in _fila]
       == ["FORNECEDOR NOVO", "LOJA QUE NUNCA APARECEU"])
    ok("a fila soma as vezes do mesmo nome",
       _fila[0]["n"] == 2 and abs(_fila[0]["total"] - 376.0) < 0.01)
    ok("lista vazia nao derruba", classificar([], CAD) == ([], []))
    # O furo que fez a tela perguntar de novo o que ja tinha sido respondido:
    # o SEED so entrava quando a aba nascia.
    ok("todo nome do SEED tem chave utilizavel",
       all(chave(f) for f, _fin, _tp, _o in SEED))
    ok("o SEED nao tem duas respostas para a mesma chave e sentido",
       len({(chave(f), tp) for f, _fin, tp, _o in SEED}) == len(SEED))

    # O cheque e a folha o proprio extrato resolve: nao podem virar pergunta.
    _ja = classificar([{"favorecido": "CH COMPENSADO 001 000504",
                        "valor": -968.6, "finalidade": "CHEQUES"}], CAD)
    ok("finalidade que ja veio no lancamento e preservada",
       _ja[0][0]["finalidade"] == "CHEQUES"
       and _ja[0][0]["classificado"] is True)
    ok("e ela nao vai para a fila", _ja[1] == [])
    # Mas o cadastro continua mandando quando existe: e nele que a correcao do
    # dono vale para o passado inteiro.
    _cad_manda = classificar([{"favorecido": "APEXIMP", "valor": -100.0,
                               "finalidade": "OUTROS"}], CAD)
    ok("o cadastro vence a finalidade que veio no arquivo",
       _cad_manda[0][0]["finalidade"] == "MERCADORIA")

    print("\nfalhas:", falhas)
