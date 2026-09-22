"""gerar_params_historico.py — Recalcula as constantes do financeiro_historico.

QUANDO RODAR
------------
Uma vez por ano, quando um ano fecha. É só isso. As constantes que ele produz
descrevem o comportamento do faturamento ao longo do ano, e isso não muda de
mês para mês.

    python3 gerar_params_historico.py ~/pasta/com/os/Controle*.xlsx

Ele imprime os quatro blocos prontos para colar no `financeiro_historico.py`:
TOTAL_ANUAL, CRESCIMENTO, INDICE_SAZONAL, CURVA_DO_MES e ERRO_PROJECAO.

POR QUE ELE NÃO RODA DENTRO DO STUDIO
-------------------------------------
Os arquivos anuais somam mais de 12 MB e moram no OneDrive; o Studio lê Google
Sheets. Montar essa leitura no Studio para derivar 43 números que mudam uma vez
por ano seria trocar um incômodo pequeno e anual por uma dependência
permanente — mais um lugar para quebrar, e uma tela mais lenta em troca de
nada.

O QUE ELE LÊ
------------
A aba de vendas diárias de cada arquivo (`VENDAS 2023`, `VENDAS 2024`, …), e
dela três colunas: a data, o faturamento do dia já líquido de devolução
(`TT FAT - DEV`; em 2023 a coluna se chamava `TOTAL FAT`) e a QUANTIDADE de
vendas do dia. Meses com menos de 28 dias registrados ficam de fora — mês pela
metade distorceria a curva.

DOIS ÍNDICES SAZONAIS, E O SEGUNDO É O QUE IMPORTA PARA O CUSTO
---------------------------------------------------------------
O `INDICE_SAZONAL` pesa o FATURAMENTO de cada mês. Ele serve para projetar
quanto se vai faturar, e é o que o painel do faturamento usa.

Mas o custo fixo por venda — o UC — é `custo fixo ÷ QUANTIDADE de vendas`, e
quantidade não é dinheiro. Um dezembro de ticket alto fatura 40% acima da média
sem vender 40% a mais de pedidos; usar o índice do faturamento para estimar
pedidos erraria exatamente na direção que mais importa, a do mês que vem.

Por isso sai daqui também o `INDICE_SAZONAL_VENDAS`, medido do mesmo jeito
sobre a contagem de pedidos. Quando a coluna da quantidade não é encontrada, o
script DIZ e não gera o bloco — melhor faltar o número do que devolver o do
faturamento fingindo ser o de vendas.

O ERRO É MEDIDO COM LEAVE-ONE-OUT
---------------------------------
Para medir o erro de projetar um mês, a curva usada é construída SEM esse mês.
Sem isso, o teste mediria a memória da conta em vez da capacidade de prever, e
devolveria um erro bonito e falso.
"""

import datetime
import glob
import statistics as st
import sys
from collections import defaultdict


def _ler_ano(caminho):
    """[(data, faturamento_do_dia)] de um arquivo anual. [] se não der."""
    import openpyxl
    try:
        wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    except Exception as e:
        print(f"# nao consegui abrir {caminho}: {type(e).__name__}", file=sys.stderr)
        return []
    aba = next((n for n in wb.sheetnames if n.upper().startswith("VENDAS ")), None)
    if not aba:
        print(f"# {caminho}: sem aba 'VENDAS ...'", file=sys.stderr)
        wb.close()
        return []
    ws = wb[aba]
    it = ws.iter_rows(values_only=True)
    cabecalho = list(next(it))

    def coluna(*nomes):
        """O indice da coluna, procurando NA ORDEM DOS NOMES.

        A ordem importa e nao e detalhe. A mesma planilha traz `TT VENDAS -
        DEV` e `TOTAL VENDAS2`; varrer as colunas da esquerda para a direita
        devolveria a que aparecesse primeiro na aba, que muda de ano para ano.
        Procurando por nome, o primeiro nome da lista e o preferido — e e o
        que casa com o faturamento usado aqui (`TT FAT - DEV`).
        """
        mapa = {}
        for i, c in enumerate(cabecalho):
            if c:
                mapa.setdefault(str(c).strip().upper(), i)
        for n in nomes:
            if n in mapa:
                return mapa[n]
        return None

    i_data = coluna("DATA")
    i_fat = coluna("TT FAT - DEV", "TOTAL FAT")
    # A contagem de pedidos do dia. Os nomes mudam de um ano para o outro, como
    # ja mudaram os do faturamento — entao se procura por varios, e se IMPRIME
    # qual foi usado. Coluna adivinhada em silencio e numero em que ninguem
    # confia depois.
    # `TT VENDAS - DEV` primeiro: e a contagem liquida de devolucao, o par
    # exato do `TT FAT - DEV` que ja se usa aqui. Em 2023 as duas colunas
    # tinham outro nome (`TOTAL FAT` / `TOTAL VENDAS`), e o par se mantem.
    # `TOTAL VENDAS2` fica de fora de proposito: e o acumulado do mes repetido
    # na linha do dia, e somaria o mes inteiro a cada dia.
    i_qtd = coluna("TT VENDAS - DEV", "TOTAL VENDAS", "QTD VENDAS",
                   "QTD. VENDAS", "QUANTIDADE", "QTD", "QTDE", "PEDIDOS",
                   "N VENDAS", "Nº VENDAS", "VENDAS DIA", "VENDAS")
    if i_qtd is None:
        print(f"# {caminho}: sem coluna de QUANTIDADE de vendas — "
              f"colunas: {[str(c) for c in cabecalho if c]}", file=sys.stderr)
    else:
        print(f"# {caminho}: quantidade de vendas na coluna "
              f"'{cabecalho[i_qtd]}'", file=sys.stderr)
    if i_data is None or i_fat is None:
        print(f"# {caminho}: nao achei DATA ou o faturamento do dia", file=sys.stderr)
        wb.close()
        return []
    saida = []
    for linha in it:
        d, v = linha[i_data], linha[i_fat]
        q = linha[i_qtd] if i_qtd is not None else None
        if isinstance(d, datetime.datetime):
            d = d.date()
        if isinstance(d, datetime.date) and isinstance(v, (int, float)):
            saida.append((d, float(v),
                          float(q) if isinstance(q, (int, float)) else None))
    wb.close()
    return saida


def _curva(meses, excluir=None):
    """Fração média do mês faturada até cada dia. `excluir` deixa um mês fora."""
    acumulado = defaultdict(list)
    for chave, dias in meses.items():
        if chave == excluir:
            continue
        total = sum(v for _, v in dias)
        soma = 0.0
        for dia, v in dias:
            soma += v
            acumulado[dia].append(soma / total)
    return acumulado


def main(padroes):
    caminhos = []
    for p in padroes:
        caminhos.extend(sorted(glob.glob(p)))
    if not caminhos:
        print("uso: python3 gerar_params_historico.py <arquivos Controle*.xlsx>",
              file=sys.stderr)
        return 1

    dias = []
    for c in caminhos:
        d = _ler_ano(c)
        if d:
            _q = sum(q for _, _, q in d if q is not None)
            print(f"# {c}: {len(d)} dias, R$ {sum(v for _, v, _ in d):,.2f}"
                  + (f", {_q:,.0f} vendas" if _q else ", sem contagem de vendas"))
        dias.extend(d)
    if not dias:
        print("nenhum dia lido — nada a gerar", file=sys.stderr)
        return 1

    por_mes = defaultdict(list)
    qtd_mes = defaultdict(float)
    tem_qtd = set()
    for d, v, q in dias:
        por_mes[(d.year, d.month)].append((d.day, v))
        if q is not None:
            qtd_mes[(d.year, d.month)] += q
            tem_qtd.add((d.year, d.month))
    # Mes incompleto distorce tanto a curva quanto o indice: fica de fora.
    meses = {k: sorted(v) for k, v in por_mes.items()
             if len(v) >= 28 and sum(x for _, x in v) > 0}

    # E ANO incompleto e pior ainda: o indice sazonal divide cada mes pela media
    # do ano, e a media de um ano pela metade nao e media de nada. Rodando com o
    # 2026 em agosto, o crescimento saiu -62% e janeiro virou 1,40 (±0,70).
    # So entram anos FECHADOS, com os 12 meses.
    completos = sorted(a for a in {y for y, _ in meses}
                       if sum(1 for (y, _) in meses if y == a) == 12)
    if not completos:
        print("nenhum ano fechado nos arquivos — nada a gerar", file=sys.stderr)
        return 1
    descartados = sorted({y for y, _ in meses} - set(completos))
    if descartados:
        print(f"# anos incompletos, fora da conta: {descartados}")
    meses = {k: v for k, v in meses.items() if k[0] in completos}
    anos = completos
    print(f"# {len(meses)} meses completos, anos {anos[0]}-{anos[-1]}\n")

    total_ano = {a: sum(sum(v for _, v in dd) for (y, _), dd in meses.items() if y == a)
                 for a in anos}
    print("TOTAL_ANUAL = {")
    for a in anos:
        print(f"    {a}: {total_ano[a]:_.2f},")
    print("}\n")

    print("CRESCIMENTO = {")
    for i in range(1, len(anos)):
        print(f"    {anos[i]}: {total_ano[anos[i]] / total_ano[anos[i - 1]] - 1:.4f},")
    print("}\n")

    print("INDICE_SAZONAL = {")
    for m in range(1, 13):
        vs = [sum(v for _, v in meses[(a, m)]) / (total_ano[a] / 12)
              for a in anos if (a, m) in meses]
        if vs:
            print(f"    {m:>2}: {st.mean(vs):.4f},   # ±{st.pstdev(vs):.3f}")
    print("}\n")

    # ── O indice sobre QUANTIDADE de vendas ─────────────────────────────
    # Mesma conta do INDICE_SAZONAL, trocando reais por pedidos. So entram os
    # anos em que TODOS os 12 meses tem contagem: um ano com dois meses sem
    # quantidade tem media anual menor do que a real, e todo mes desse ano sai
    # com indice inflado.
    anos_q = [a for a in anos
              if all((a, m) in tem_qtd and qtd_mes[(a, m)] > 0
                     for m in range(1, 13))]
    if not anos_q:
        print("# INDICE_SAZONAL_VENDAS: nenhum ano fechado tem a contagem de")
        print("# vendas nos 12 meses. O bloco NAO foi gerado — o indice do")
        print("# faturamento nao serve no lugar dele (ticket medio varia).\n")
    else:
        if set(anos_q) != set(anos):
            _fora = sorted(set(anos) - set(anos_q))
            print(f"# INDICE_SAZONAL_VENDAS sem os anos {_fora} "
                  f"(faltou contagem em algum mes)")
        print(f"# INDICE_SAZONAL_VENDAS: anos {anos_q[0]}-{anos_q[-1]}, "
              f"{sum(qtd_mes[(a, m)] for a in anos_q for m in range(1, 13)):,.0f}"
              " vendas")
        print("INDICE_SAZONAL_VENDAS = {")
        for m in range(1, 13):
            med_ano = {a: sum(qtd_mes[(a, mm)] for mm in range(1, 13)) / 12
                       for a in anos_q}
            vs = [qtd_mes[(a, m)] / med_ano[a] for a in anos_q]
            print(f"    {m:>2}: {st.mean(vs):.4f},   # ±{st.pstdev(vs):.3f}")
        print("}\n")

    ac = _curva(meses)
    print("CURVA_DO_MES = {")
    for dia in range(1, 32):
        if len(ac.get(dia, [])) >= 20:
            print(f"    {dia:>2}: ({st.mean(ac[dia]):.4f}, {st.pstdev(ac[dia]):.4f}),")
    print("}\n")

    print("ERRO_PROJECAO = {")
    for dia in range(1, 32):
        erros = []
        for chave, dd in meses.items():
            c = _curva(meses, excluir=chave)
            if dia not in c:
                continue
            fracao = st.mean(c[dia])
            if fracao <= 0:
                continue
            real = sum(v for _, v in dd)
            ate = sum(v for d, v in dd if d <= dia)
            erros.append(abs(ate / fracao - real) / real)
        if len(erros) >= 20:
            erros.sort()
            p90 = erros[int(len(erros) * 0.9)]
            print(f"    {dia:>2}: ({st.mean(erros):.4f}, {p90:.4f}),")
    print("}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
