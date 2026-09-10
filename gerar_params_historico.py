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
dela duas colunas: a data e o faturamento do dia já líquido de devolução
(`TT FAT - DEV`; em 2023 a coluna se chamava `TOTAL FAT`). Meses com menos de
28 dias registrados ficam de fora — mês pela metade distorceria a curva.

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
        for i, c in enumerate(cabecalho):
            if c and str(c).strip().upper() in nomes:
                return i
        return None

    i_data = coluna("DATA")
    i_fat = coluna("TT FAT - DEV", "TOTAL FAT")
    if i_data is None or i_fat is None:
        print(f"# {caminho}: nao achei DATA ou o faturamento do dia", file=sys.stderr)
        wb.close()
        return []
    saida = []
    for linha in it:
        d, v = linha[i_data], linha[i_fat]
        if isinstance(d, datetime.datetime):
            d = d.date()
        if isinstance(d, datetime.date) and isinstance(v, (int, float)):
            saida.append((d, float(v)))
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
            print(f"# {c}: {len(d)} dias, R$ {sum(v for _, v in d):,.2f}")
        dias.extend(d)
    if not dias:
        print("nenhum dia lido — nada a gerar", file=sys.stderr)
        return 1

    por_mes = defaultdict(list)
    for d, v in dias:
        por_mes[(d.year, d.month)].append((d.day, v))
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
