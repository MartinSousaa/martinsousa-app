"""
fechar_expediente.py — Põe FIM DE EXPEDIENTE no que ficou aberto, e só isso.

Roda sozinho, de tempos em tempos, fora do Studio. É a única parte deste projeto
que ESCREVE no Trello — todas as outras nove chamadas são GET — e por isso ela
mora num arquivo só dela, com as travas na entrada e não espalhadas.

O que resolve
-------------
A pessoa vai embora e o cartão fica com EM ANDAMENTO. O relógio não para: ele
volta a andar às 9h do dia seguinte e ela aparece trabalhando sem ter tocado no
cartão. Aconteceu: saída batida às 17h45, cartão ainda contando às 20h30.

Quem decide é fim_expediente.decidir(); aqui só se busca o que ela precisa e se
aplica o que ela mandou.

As quatro travas
----------------
1. Só em produção. O ambiente de teste aponta para o board REAL: sem esta trava,
   um teste mexeria no Trello de verdade. `AMBIENTE=homologacao` aborta.
2. Só a etiqueta FIM DE EXPEDIENTE, e só em cartão que já está EM ANDAMENTO.
   Não move cartão, não muda campo, não escreve em mais nada.
3. Idempotente. Cartão que já tem a etiqueta é pulado — rodar de novo não
   duplica nem reescreve.
4. `--simular` mostra o que faria sem tocar em nada. É o modo da primeira vez.

Uso
---
    python3 fechar_expediente.py --simular    # mostra, não aplica
    python3 fechar_expediente.py              # aplica
"""

import os
import sys
from datetime import datetime

import fim_expediente as _fe

TIMEOUT = (10, 30)
SECRETS = ".streamlit/secrets.toml"


def _preparar_secrets():
    """Escreve o secrets.toml a partir do ambiente, se ele ainda não existir.

    Quem faz isso na aplicação web é o Procfile — e o Procfile NÃO roda numa
    tarefa agendada. Sem este passo o script sobe sem credencial nenhuma e
    morre no primeiro acesso ao Trello, com um erro que não diz o que faltou.

    A ordem importa: PLANILHA_ID vai ANTES do bloco de segredos porque, em TOML,
    chave solta escrita depois de um cabeçalho [secao] pertence àquela seção.
    """
    if os.path.exists(SECRETS):
        return True
    bloco = os.environ.get("STREAMLIT_SECRETS", "")
    if not bloco.strip():
        _log("ABORTADO: a variável STREAMLIT_SECRETS não está definida neste "
             "serviço. Copie-a do serviço de produção.")
        return False
    os.makedirs(os.path.dirname(SECRETS), exist_ok=True)
    pid = (os.environ.get("PLANILHA_ID") or "").strip()
    with open(SECRETS, "w", encoding="utf-8") as fh:
        if pid:
            fh.write('PLANILHA_ID = "%s"\n' % pid)
        fh.write(bloco)
    _log(f"secrets.toml montado a partir do ambiente"
         + (" (com PLANILHA_ID)" if pid else ""))
    return True


def _log(msg):
    # Log em hora de Brasilia, e nao a do container: quem le o log procura o
    # horario que a equipe viveu.
    try:
        import placar_core as _pc_log
        _ag = datetime.now(_pc_log.FUSO)
    except Exception:
        _ag = datetime.now()
    print(f"[{_ag:%d/%m %H:%M:%S}] {msg}", flush=True)


def _abortar_se_nao_for_producao():
    """O ambiente de teste aponta para o board real. Escrever dali é acidente."""
    import planilha as _plan
    if _plan.eh_homologacao():
        _log(f"ABORTADO: ambiente '{_plan.ambiente()}'. Esta tarefa só roda em "
             f"produção — o board do Trello é o mesmo nos dois ambientes.")
        return True
    return False


def _saidas_de_hoje(hoje):
    """{username: 'HH:MM'|None} — a saída batida hoje por cada pessoa.

    Ausente do dicionário significa "não sei", e não "não bateu": pessoa que a
    RHiD não reconheceu não pode ter cartão fechado por suposição.
    """
    import rhid_api as _rhid
    import relogio_ponto as _rp

    dia = hoje.strftime("%d/%m/%Y")
    saidas = {}
    try:
        pessoas = [p for p in (_rhid.get_persons() or [])
                   if str(p.get("status", "1")) != "0"]
    except Exception as e:
        _log(f"RHiD não respondeu a lista de pessoas ({str(e)[:120]}).")
        return saidas

    for p in pessoas:
        nome = (p.get("name") or p.get("nome") or p.get("nomeCompleto")
                or p.get("fullName") or p.get("personName") or "")
        user = _rp._rhid_nome_para_trello(nome)
        if not user:
            continue
        pid = p.get("id") or p.get("idPerson") or p.get("personId") or 0
        try:
            regs, _diag = _rhid.get_registros_diarios(dia, dia, int(pid))
        except Exception as e:
            _log(f"RHiD falhou para {nome} ({str(e)[:80]}); pulando.")
            continue
        hoje_reg = next((r for r in regs if r.get("data") == hoje), None)
        saidas[user] = (hoje_reg or {}).get("saida")
    return saidas


def _cartoes_em_andamento():
    """[{'id','nome','membros','labels'}] dos cartões em execução agora."""
    import placar_core as _pc
    listas, cards, membros_map, *_ = _pc._buscar_board()
    if not cards:
        return []
    fora = []
    for c in cards:
        nomes = {(lb.get("name") or "").upper().strip()
                 for lb in (c.get("labels") or [])}
        if not (nomes & _pc.LABELS_TRABALHO):
            continue
        fora.append({
            "id": c["id"],
            "nome": c.get("name", ""),
            "membros": [membros_map.get(m) for m in (c.get("idMembers") or [])
                        if membros_map.get(m)],
            "labels": nomes,
        })
    return fora


def _id_da_etiqueta():
    """Id da etiqueta FIM DE EXPEDIENTE no board, ou None se ela não existir."""
    import placar_core as _pc
    mapa = _pc.mapa_labels(forcar=True)
    alvos = {_pc.LABEL_FIM_EXPEDIENTE, "FIM DO EXPEDIENTE"}
    for lid, nome in mapa.items():
        if (nome or "").upper().strip() in alvos:
            return lid
    return None


def _aplicar(card_id, label_id):
    """A única escrita deste projeto no Trello. Devolve (ok, detalhe)."""
    import requests
    import placar_core as _pc
    try:
        r = requests.post(
            f"https://api.trello.com/1/cards/{card_id}/idLabels",
            params={"key": _pc.TRELLO_KEY, "token": _pc.TRELLO_TOKEN,
                    "value": label_id},
            timeout=TIMEOUT)
        return r.ok, (f"HTTP {r.status_code}" if not r.ok else "")
    except Exception as e:
        return False, str(e)[:140]


def main(simular=False, agora=None):
    """`agora` existe para a conferência poder fixar a hora.

    Sem ela, o caso "ainda dentro do expediente" só passava se a máquina que
    roda o teste estivesse, ela própria, dentro do expediente — e o container
    onde isto é escrito trabalha em UTC.
    """
    if not _preparar_secrets():
        return 1
    if _abortar_se_nao_for_producao():
        return 1

    import placar_core as _pc
    _pc.recarregar_membros()
    # A hora TEM que ser a de Brasilia. O container roda em UTC, e datetime.now()
    # devolvia 19h30 quando aqui eram 16h30 — tres horas adiantado. Como a regra
    # compara essa hora com o fim do expediente ("18:00"), que e local, a
    # etiqueta caia no meio da tarde: a equipe via cartao fechado entre 16h30 e
    # 17h. Toda a decisao depende desta linha.
    agora = agora or datetime.now(_pc.FUSO)
    hoje = agora.date()

    label_id = _id_da_etiqueta()
    if not label_id:
        _log(f"ABORTADO: o board não tem a etiqueta "
             f"'{_pc.LABEL_FIM_EXPEDIENTE}'. Crie-a no Trello.")
        return 1

    saidas = _saidas_de_hoje(hoje)
    if not saidas:
        _log("ABORTADO: nenhuma pessoa reconhecida na RHiD. Sem saber quem "
             "encerrou, fechar cartão seria chute.")
        return 1

    pessoas = {}
    for user in saidas:
        h = _pc.horario_de(user)
        pessoas[user] = {"fim": f"{h['fim'].hour:02d}:{h['fim'].minute:02d}",
                         "saida": saidas[user]}

    cartoes = _cartoes_em_andamento()
    alvos = _fe.decidir(agora, pessoas, cartoes)

    # Etiqueta ja posta: rodar de novo nao reescreve.
    ja = {c["id"] for c in cartoes
          if c["labels"] & {_pc.LABEL_FIM_EXPEDIENTE, "FIM DO EXPEDIENTE"}}
    alvos = [a for a in alvos if a["id"] not in ja]

    _log(f"{len(cartoes)} cartão(ões) em execução · "
         f"{len(pessoas)} pessoa(s) com ponto · {len(alvos)} a fechar"
         + (" (SIMULAÇÃO)" if simular else ""))
    if not alvos:
        return 0

    erros = 0
    for a in alvos:
        if simular:
            _log(f"  [simulado] {a['nome'][:60]} · {a['quem']} · {a['motivo']}")
            continue
        ok, detalhe = _aplicar(a["id"], label_id)
        if ok:
            _log(f"  fechado: {a['nome'][:60]} · {a['quem']} · {a['motivo']}")
        else:
            erros += 1
            _log(f"  FALHOU: {a['nome'][:60]} · {detalhe}")
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main(simular="--simular" in sys.argv))
