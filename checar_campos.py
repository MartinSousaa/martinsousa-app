"""checar_campos.py — toda tabela editável desenha em CAMPOS, no Streamlit de verdade.

Dono, 09/10: as tabelas editáveis viram campos, sem a caixinha flutuante, em
TODAS as bases (`campos.py`). Este verificador pergunta três coisas:

1. O `app.py` instala os campos, e ANTES do dinheiro? Sem a linha, toda tela
   volta à grade; depois do `rotulos.instalar_moeda`, o embrulho do dinheiro
   fica por dentro e a coluna chega ao editor sem o "localized".
2. Alguma tela chama a grade por fora do `st`? `c1.data_editor(...)` é método
   da coluna, e não passa pelo `st.data_editor` que o `app.py` trocou: aquela
   tela voltaria à caixinha em silêncio.
3. Cada tela com tabela editável MONTA no Streamlit de verdade, com dado, sem
   grade editável e com campos desenhados? O duplo do `checar_tela` não sabe o
   que o Streamlit recusa — `number_input` com tipos misturados, valor fora do
   limite, botão do lado errado do formulário. O `AppTest` sabe.

SÓ A PLANILHA É TROCADA. As abas voltam linhas na forma que o Google devolve
(`get_all_records`), e quem as lê é o `carregar` de cada módulo — a cadeia
real, e não um DataFrame montado aqui (Forma 7 do CLAUDE.md).
"""
import ast
import os
import sys
from datetime import date

RAIZ = os.path.dirname(os.path.abspath(__file__))

# (módulo, função, argumentos). Toda chamada de `st.data_editor` do Studio
# está alcançada por uma destas — `_alcance` confere.
TELAS = [
    ("folha_salarial", "pagina", ("leo",)),
    ("finalidades_tela", "pagina", ("leo",)),
    ("meta_gastos_tela", "pagina", ("leo",)),
    ("ajustes", "pagina", ("leo",)),
    ("nao_operacional", "pagina", ("leo",)),
    ("extratos_tela", "pagina", ("leo",)),
    ("cheques_tela", "pagina", ("leo",)),
    ("custo_fixo", "pagina", ("leo",)),
    ("assinaturas_tela", "_grade", ("leo",)),
    # O dono: os movimentos (Aportes e saldos) só abrem para ele.
    ("headcount", "pagina", ("martinsousa",)),
    ("colaboradores", "bloco", ("leo",)),
]


def _abas():
    """O que cada aba devolve, nas colunas de cada módulo."""
    hoje = date.today()
    mes = f"{hoje.year}-{hoje.month:02d}"
    return {
        # Lançamento do mês corrente (o `_ver_mes` abre no mês de hoje) e um
        # sem finalidade, para a fila de finalidades aparecer.
        "lancamentos": [
            {"id": "1", "conta": "itau-1", "data": f"{mes}-02",
             "descricao": "PIX ALUGUEL", "favorecido": "IMOB",
             "valor": -3000.0, "tipo": "", "finalidade": "CUSTO FIXO",
             "fixada": "", "observacao": "", "atualizado_em": "",
             "atualizado_por": ""},
            {"id": "2", "conta": "itau-1", "data": f"{mes}-03",
             "descricao": "PIX LOJA XPTO SEM CADASTRO",
             "favorecido": "LOJA XPTO SEM CADASTRO",
             "valor": -300.0, "tipo": "", "finalidade": "", "fixada": "",
             "observacao": "", "atualizado_em": "", "atualizado_por": ""},
        ],
        "cheques": [
            {"id": "c1", "tipo": "", "folha": "564", "compra": "2026-09-18",
             "vencimento": "2026-10-18", "valor": 1500.0, "envio": 0,
             "estoque": 1500.0, "favorecido": "LEXTACK", "situacao": "",
             "observacao": "", "atualizado_em": "", "atualizado_por": ""},
        ],
        "ajustes": [
            {"grade": "custo_fixo", "item": "Aluguel", "valor_novo": 3200.0,
             "vigente_desde": "2026-05", "observacao": "reajuste",
             "atualizado_em": "", "atualizado_por": ""},
        ],
        # O ajuste só abre com item cadastrado numa grade. A segunda linha
        # tem as células VAZIAS como o Google as devolve: "" — e não None —
        # num campo de número e num de dinheiro.
        "custo_fixo": [
            {"item": "Aluguel", "valor_mensal": 3000.0,
             "vigente_desde": "2026-01", "dia_debito": 5,
             "forma_pagamento": "PIX", "favorecido": "IMOB",
             "atualizado_em": "", "atualizado_por": ""},
            {"item": "Internet", "valor_mensal": "",
             "vigente_desde": "", "dia_debito": "",
             "forma_pagamento": "", "favorecido": "",
             "atualizado_em": "", "atualizado_por": ""},
        ],
        "headcount_movimentos": [
            {"tipo": "Aporte", "data": "2026-01", "valor": 50000,
             "observacao": "", "atualizado_em": "", "atualizado_por": ""},
            {"tipo": "Saldo", "data": "2026-02", "valor": "",
             "observacao": "", "atualizado_em": "", "atualizado_por": ""},
        ],
    }


def _planilha(abas):
    import checar_tela as _ct

    class _Aba(_ct._AbaVazia):
        def __init__(self, linhas):
            self._linhas = linhas

        def get_all_records(self, **kw):
            return [dict(r) for r in self._linhas]

        def get_all_values(self, **kw):
            if not self._linhas:
                return []
            cab = list(self._linhas[0])
            return [cab] + [[r.get(c, "") for c in cab] for r in self._linhas]

        def row_values(self, n):
            v = self.get_all_values()
            return v[n - 1] if 0 < n <= len(v) else []

    class _Planilha(_ct._PlanilhaVazia):
        def worksheet(self, nome):
            return _Aba(abas.get(nome, []))

    return _Planilha()


def _tela(modulo, funcao, args):
    """O script do AppTest. Roda isolado: tudo o que usa é importado aqui."""
    import importlib
    import streamlit as st
    import campos
    import rotulos
    campos.instalar(st)
    rotulos.instalar_moeda(st)
    getattr(importlib.import_module(modulo), funcao)(*args)


def _ordem_no_app():
    """[] se o app.py chama `campos.instalar(st)` antes do dinheiro."""
    arv = ast.parse(open(os.path.join(RAIZ, "app.py"), encoding="utf-8").read())
    linhas = {}
    for no in arv.body:
        if (isinstance(no, ast.Expr) and isinstance(no.value, ast.Call)
                and isinstance(no.value.func, ast.Attribute)
                and isinstance(no.value.func.value, ast.Name)):
            nome = f"{no.value.func.value.id}.{no.value.func.attr}"
            linhas.setdefault(nome, no.lineno)
    if "campos.instalar" not in linhas:
        return ["app.py não chama campos.instalar(st): toda tabela volta à "
                "grade com a caixinha"]
    if linhas["campos.instalar"] > linhas.get("rotulos.instalar_moeda", 10**9):
        return ["app.py chama campos.instalar DEPOIS de rotulos.instalar_moeda"]
    return []


def _grade_por_fora():
    """Chamadas `x.data_editor(...)` em que x não é o `st` — passam por fora
    da troca do app.py."""
    fora = []
    for nome in sorted(os.listdir(RAIZ)):
        if (not nome.endswith(".py") or nome.startswith("checar_")
                or nome in ("campos.py", "rotulos.py")):
            continue
        try:
            arv = ast.parse(open(os.path.join(RAIZ, nome),
                                 encoding="utf-8").read())
        except SyntaxError:
            continue
        for no in ast.walk(arv):
            if (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
                    and no.func.attr == "data_editor"
                    and not (isinstance(no.func.value, ast.Name)
                             and no.func.value.id == "st")):
                fora.append(f"{nome}:{no.lineno}")
    return fora


def chaves_das_grades():
    """{key: "arquivo:linha"} de toda chamada `st.data_editor` do Studio.

    A chave em f-string (`f"ed_{aba_nome}"`) entra pelo trecho fixo antes da
    primeira variável — é o prefixo que o campo leva."""
    fora = {}
    for nome in sorted(os.listdir(RAIZ)):
        if (not nome.endswith(".py") or nome.startswith("checar_")
                or nome in ("campos.py", "rotulos.py")):
            continue
        try:
            arv = ast.parse(open(os.path.join(RAIZ, nome),
                                 encoding="utf-8").read())
        except SyntaxError:
            continue
        for no in ast.walk(arv):
            if not (isinstance(no, ast.Call)
                    and isinstance(no.func, ast.Attribute)
                    and no.func.attr == "data_editor"):
                continue
            k = next((kw.value for kw in no.keywords if kw.arg == "key"), None)
            if isinstance(k, ast.Constant):
                fora[str(k.value)] = f"{nome}:{no.lineno}"
            elif isinstance(k, ast.JoinedStr) and k.values and isinstance(
                    k.values[0], ast.Constant):
                fora[str(k.values[0].value) + "*"] = f"{nome}:{no.lineno}"
            else:
                fora[f"?{nome}:{no.lineno}"] = f"{nome}:{no.lineno}"
    return fora


def main():
    sys.path.insert(0, RAIZ)
    os.chdir(RAIZ)
    falhas = 0

    def conta(nome, ok, detalhe=""):
        nonlocal falhas
        falhas += not ok
        print(("ok    " if ok else "FALHA ") + nome
              + (f"\n      {detalhe}" if detalhe and not ok else ""))

    _o = _ordem_no_app()
    conta("app.py instala os campos antes do dinheiro", not _o, "; ".join(_o))
    _f = _grade_por_fora()
    conta("nenhuma tela chama a grade por fora do st", not _f, ", ".join(_f))
    _grades = chaves_das_grades()
    desenhadas = set()

    import logging
    logging.getLogger("streamlit").setLevel(logging.ERROR)
    import sheets as _sh
    from streamlit.testing.v1 import AppTest
    _guardado = (_sh.planilha, _sh.cliente)
    _pl = _planilha(_abas())
    _sh.planilha = lambda *a, **k: _pl
    _sh.cliente = lambda *a, **k: None
    try:
        for modulo, funcao, args in TELAS:
            nome = f"{modulo}.{funcao}{'(' + args[1] + ')' if len(args) > 1 else ''}"
            try:
                at = AppTest.from_function(_tela, args=(modulo, funcao, args),
                                           default_timeout=60).run()
            except Exception as e:
                conta(f"{nome} monta em campos", False,
                      f"{type(e).__name__}: {str(e)[:200]}")
                continue
            if at.exception:
                conta(f"{nome} monta em campos", False,
                      str(at.exception[0].value)[:300])
                continue
            grades = [g for g in at.get("arrow_data_frame")
                      if getattr(g.proto, "editing_mode", 0)]
            campos_vistos = [w for t in ("text_input", "number_input",
                                         "selectbox", "checkbox")
                             for w in getattr(at, t)
                             if str(w.key or "").startswith("cp_")]
            conta(f"{nome} monta em campos", not grades and campos_vistos,
                  f"{len(grades)} grade(s) editável(is), "
                  f"{len(campos_vistos)} campo(s)")
            desenhadas |= {str(w.key)[3:] for w in campos_vistos}
    finally:
        _sh.planilha, _sh.cliente = _guardado

    # TODA tabela editável do código apareceu em campos em alguma tela. Sem
    # isto, uma tabela nova (ou uma que só abre com dado) passaria sem ser
    # desenhada nunca — e o verde valeria para as outras.
    def _vista(k):
        if k.endswith("*"):
            return any(d.startswith(k[:-1]) for d in desenhadas)
        return any(d.startswith(k + "_") for d in desenhadas)
    _nunca = [f"{k} ({onde})" for k, onde in _grades.items() if not _vista(k)]
    conta(f"as {len(_grades)} tabelas editáveis do código aparecem em campos",
          not _nunca and len(_grades) > 0,
          "nunca desenhadas: " + ", ".join(_nunca))

    print(f"\nfalhas: {falhas}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
