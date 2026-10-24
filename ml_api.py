"""ml_api.py — Acesso à API do Mercado Livre, com o token se renovando sozinho.

POR QUE EXISTE (dono, 20/10)
----------------------------
Colocar produto em promoção leva MUITO tempo: quatro contas de Mercado Livre,
centenas de anúncios, tudo à mão. A API do ML permite listar os convites de
campanha, inscrever anúncios e criar desconto próprio (`/seller-promotions`).
Este módulo é a PORTA: autoriza as contas e mantém o token vivo. A tela de
promoções vem em cima dele.

UM APLICATIVO, QUATRO CONTAS
----------------------------
O ML deixa criar UM aplicativo por titular (o "Sistema MS", criado em 20/10).
Ele é autorizado uma vez em cada conta — ML1, ML2, ML3 e ML4 —, e cada conta
ganha o seu token. As credenciais do aplicativo moram nas Variáveis do Railway:
`ML_CLIENT_ID` e `ML_CLIENT_SECRET` (lidas por `chaves.ler`), nunca aqui.

QUEM DIZ QUAL CONTA É QUAL
--------------------------
O ML autoriza a conta que está LOGADA no navegador naquela hora, e não a que
o botão do Studio diz. Clicar em "ML1" logado na ML3 gravaria o token da ML3
com o nome ML1 — e as promoções iriam para a conta errada, caladas. Por isso
o token é gravado com o `user_id` e o apelido que o ML devolve, e a tela
mostra os dois: quem autorizou confere ali, e duas contas com o mesmo
`user_id` são recusadas (`conta_repetida`).

O MESMO MODELO DO BLING
-----------------------
Token na PLANILHA (aba `ml_tokens`), uma linha por conta, para atravessar
deploy e reinício; `state` sorteado e gravado antes da ida, conferido na
volta; o `code` é trocado no instante em que o navegador volta. As decisões
puras (vencimento, renovação, state) são as do `bling_api` — importadas, e
não copiadas: duas cópias passam a discordar, a questão é só quando.

NESTA PRIMEIRA VERSÃO SÓ SE LÊ
------------------------------
`get` e mais nada. Escrever promoção será função própria, com nome que diga
isso, e só depois de a leitura ter sido conferida com dado real.
"""

import time as _t

import requests
import streamlit as st

from bling_api import precisa_renovar, state_confere, state_novo, vencimento

# ── Constantes ────────────────────────────────────────────────────────────────
CONTAS = ("ml1", "ml2", "ml3", "ml4")

# Em qual CNPJ cada conta vive (`bling_api.py:19-20`). Só rótulo de tela.
CNPJ_DA_CONTA = {"ml1": "LG", "ml3": "LG", "ml2": "MS", "ml4": "MS"}

BASE = "https://api.mercadolibre.com"
URL_AUTORIZA = "https://auth.mercadolivre.com.br/authorization"
URL_TOKEN = BASE + "/oauth/token"

# A URI cadastrada no aplicativo (20/10). O ML exige que a do pedido seja
# IDÊNTICA à cadastrada, e que vá também na troca do code.
REDIRECT_URI = "https://app.martinsousa.com.br"

TIMEOUT = (10, 30)

ABA = "ml_tokens"
COLUNAS = ["conta", "access_token", "refresh_token", "expira_em",
           "atualizado_em", "escopo", "state_pendente", "user_id", "apelido"]


# ── Credenciais ───────────────────────────────────────────────────────────────
def credenciais():
    """(client_id, client_secret) do aplicativo. ('', '') sem configurar."""
    import chaves
    return (chaves.ler("ML_CLIENT_ID"), chaves.ler("ML_CLIENT_SECRET"))


def configurado():
    cid, seg = credenciais()
    return bool(cid and seg)


# ── Decisões puras ────────────────────────────────────────────────────────────
def conta_do_state(recebido):
    """A conta embutida no `state` ('ml1.xxxx'). '' quando não é do ML."""
    try:
        conta = str(recebido).split(".", 1)[0]
        return conta if conta in CONTAS else ""
    except Exception:
        return ""


def eh_callback(params):
    """O retorno do ML: `?code=…&state=ml?.…` na raiz do Studio.

    A URI cadastrada é a raiz, sem marcador; o que separa o retorno do ML de
    qualquer outra página é o `state` com o nome de uma conta ML. O retorno do
    Bling vem com `?bling=callback` e fica com ele.
    """
    try:
        if str(params.get("bling", "")):
            return False
        return bool(str(params.get("code", "")).strip()
                    and conta_do_state(str(params.get("state", "")).strip()))
    except Exception:
        return False


def conta_repetida(conta, user_id, gravados):
    """A conta do ML que acabou de autorizar já está gravada com OUTRO nome?

    `gravados`: {conta: {"user_id": …}}. Devolve o nome da outra conta, ou ''.
    É o caso de clicar em "ML2" com o navegador ainda logado na ML1.
    """
    uid = str(user_id or "").strip()
    if not uid:
        return ""
    for outra, d in (gravados or {}).items():
        if outra != conta and str((d or {}).get("user_id", "")).strip() == uid:
            return outra
    return ""


def url_montada(cid, est):
    """A URL de autorização. Pura."""
    from urllib.parse import urlencode
    return URL_AUTORIZA + "?" + urlencode({"response_type": "code", "client_id": cid,
                                           "redirect_uri": REDIRECT_URI, "state": est})


# ── Autorização ───────────────────────────────────────────────────────────────
def url_de_autorizacao(conta):
    """(url, erro). Grava o `state` na planilha ANTES de devolver a URL."""
    conta = str(conta).strip().lower()
    if conta not in CONTAS:
        return ("", f"conta desconhecida: {conta}")
    cid, _seg = credenciais()
    if not cid:
        return ("", "faltam ML_CLIENT_ID e ML_CLIENT_SECRET nas Variáveis do Railway")
    est = f"{conta}.{state_novo()}"
    if not _gravar_na_planilha(conta, {"state_pendente": est}):
        return ("", "não consegui guardar o state na planilha")
    return (url_montada(cid, est), "")


def processar_callback(params):
    """Trata o retorno do ML. (conta, apelido, erro) — calado fora do callback."""
    if not eh_callback(params):
        return ("", "", "")
    code = str(params.get("code", "")).strip()
    recebido = str(params.get("state", "")).strip()
    conta = conta_do_state(recebido)
    esperado = str((_ler_da_planilha(conta) or {}).get("state_pendente", ""))
    if not state_confere(esperado, recebido):
        return ("", "", "o `state` não confere com nenhuma autorização pedida")
    dados, erro = trocar_code_por_token(conta, code)
    if erro:
        return ("", "", erro)
    _gravar_na_planilha(conta, {"state_pendente": ""})
    return (conta, dados.get("apelido", ""), "")


# ── HTTP ──────────────────────────────────────────────────────────────────────
def _post_token(dados):
    """POST no /oauth/token. (json, erro) — nunca levanta, nunca ecoa segredo."""
    cid, seg = credenciais()
    corpo_envio = dict(dados, client_id=cid, client_secret=seg)
    try:
        r = requests.post(URL_TOKEN, data=corpo_envio, timeout=TIMEOUT,
                          headers={"Accept": "application/json",
                                   "Content-Type": "application/x-www-form-urlencoded"})
    except Exception as e:
        return (None, f"Mercado Livre não respondeu: {type(e).__name__}")
    try:
        corpo = r.json()
    except Exception:
        return (None, f"Mercado Livre respondeu {r.status_code} sem JSON")
    if not r.ok:
        tipo = str((corpo or {}).get("error") or "") if isinstance(corpo, dict) else ""
        return (None, f"Mercado Livre recusou ({r.status_code}{': ' + tipo if tipo else ''})")
    return (corpo, "")


def _quem_sou(access_token):
    """(user_id, apelido) da conta dona do token, por GET /users/me."""
    try:
        r = requests.get(BASE + "/users/me", timeout=TIMEOUT,
                         headers={"Authorization": f"Bearer {access_token}"})
        d = r.json() if r.ok else {}
        return (str(d.get("id", "")), str(d.get("nickname", "")))
    except Exception:
        return ("", "")


# ── Planilha ──────────────────────────────────────────────────────────────────
# Cache do Streamlit, e não dicionário de módulo: a aba e os tokens são da
# CONTA, iguais para toda a equipe, e quem grava limpa (`_reler`).
@st.cache_resource
def _aba():
    import gspread
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        aba = planilha.worksheet(ABA)
    except gspread.exceptions.WorksheetNotFound:
        aba = planilha.add_worksheet(title=ABA, rows=20, cols=len(COLUNAS))
        aba.append_row(COLUNAS, value_input_option="RAW")
    return aba


def _reler():
    """Esquece a leitura guardada — a próxima vem da planilha."""
    getattr(_todas, "clear", lambda: None)()


@st.cache_data(ttl=300, show_spinner=False)
def _todas():
    """{conta: registro} de todas as contas gravadas."""
    try:
        regs = _aba().get_all_records(value_render_option="UNFORMATTED_VALUE")
    except Exception:
        return {}
    return {str(r.get("conta", "")).strip().lower(): dict(r) for r in regs
            if str(r.get("conta", "")).strip()}


def _ler_da_planilha(conta):
    return _todas().get(conta, {})


def linha_mesclada(conta, atual, dados, agora_txt):
    """A linha da planilha: os campos de `dados` por cima do que já estava.
    Campo ausente PRESERVA o gravado — gravar o state não zera o token. Pura."""
    def campo(nome):
        return str(dados[nome]) if nome in dados else str((atual or {}).get(nome, ""))
    return [conta] + [agora_txt if c == "atualizado_em" else campo(c) for c in COLUNAS[1:]]


def _gravar_na_planilha(conta, dados):
    from datetime import datetime as _dt
    import placar_core as _pc
    try:
        aba = _aba()
        registros = aba.get_all_records(value_render_option="UNFORMATTED_VALUE")
        atual, alvo = {}, 0
        for i, r in enumerate(registros, start=2):
            if str(r.get("conta", "")).strip().lower() == conta:
                atual, alvo = dict(r), i
                break
        linha = linha_mesclada(conta, atual, dados, _dt.now(_pc.FUSO).strftime("%d/%m/%Y %H:%M"))
        if alvo:
            fim = chr(ord("A") + len(COLUNAS) - 1)
            aba.update(f"A{alvo}:{fim}{alvo}", [linha], value_input_option="RAW")
        else:
            aba.append_row(linha, value_input_option="RAW")
        _reler()
        return True
    except Exception:
        return False


# ── Token ─────────────────────────────────────────────────────────────────────
def _guardar(conta, corpo, extra=None):
    dados = {"access_token": str(corpo.get("access_token", "")),
             # O ML troca o refresh_token a cada renovação: guardar o velho
             # deixaria a próxima renovação sem chave.
             "refresh_token": str(corpo.get("refresh_token", "")),
             "expira_em": vencimento(corpo.get("expires_in")),
             "escopo": str(corpo.get("scope", ""))}
    dados.update(extra or {})
    _gravar_na_planilha(conta, dados)
    return dados


def trocar_code_por_token(conta, code):
    """Troca o `code` por tokens e confere de quem é a conta. (dados, erro)."""
    if not configurado():
        return ({}, "faltam ML_CLIENT_ID e ML_CLIENT_SECRET nas Variáveis do Railway")
    corpo, erro = _post_token({"grant_type": "authorization_code", "code": code,
                               "redirect_uri": REDIRECT_URI})
    if erro:
        return ({}, erro)
    uid, apelido = _quem_sou(corpo.get("access_token", ""))
    uid = uid or str(corpo.get("user_id", ""))
    outra = conta_repetida(conta, uid, _todas())
    if outra:
        return ({}, f"esta conta do Mercado Livre ({apelido or uid}) já está ligada como "
                    f"{outra.upper()}. Saia dela no navegador, entre na {conta.upper()} e autorize de novo.")
    return (_guardar(conta, corpo, {"user_id": uid, "apelido": apelido}), "")


def token(conta):
    """O access_token válido da conta, renovando se preciso. ('', motivo)."""
    conta = str(conta).strip().lower()
    if conta not in CONTAS:
        return ("", f"conta desconhecida: {conta}")
    if not configurado():
        return ("", "faltam ML_CLIENT_ID e ML_CLIENT_SECRET nas Variáveis do Railway")
    dados = _ler_da_planilha(conta) or {}
    if dados.get("access_token") and not precisa_renovar(dados.get("expira_em")):
        return (dados["access_token"], "")
    # Relê da planilha antes de renovar: outra sessão pode ter renovado, e o
    # refresh_token guardado já não vale.
    _reler()
    dados = _ler_da_planilha(conta) or {}
    if dados.get("access_token") and not precisa_renovar(dados.get("expira_em")):
        return (dados["access_token"], "")
    rt = str(dados.get("refresh_token", "")).strip()
    if not rt:
        return ("", f"{conta.upper()} ainda não foi autorizada")
    corpo, erro = _post_token({"grant_type": "refresh_token", "refresh_token": rt})
    if erro:
        return ("", f"não consegui renovar o token da {conta.upper()}: {erro}")
    return (_guardar(conta, corpo).get("access_token", ""), "")


def estados():
    """{conta: estado} das quatro, com UMA leitura da planilha — a tela roda
    a cada clique, e quatro leituras por clique eram quatro idas à rede."""
    todas = _todas() if configurado() else {}
    return {c: estado(c, todas.get(c, {})) for c in CONTAS}


def estado(conta, registro=None):
    """Resumo legível para a tela — sem o token."""
    if not configurado():
        return {"conta": conta, "situacao": "sem credenciais"}
    d = registro if registro is not None else (_ler_da_planilha(conta) or {})
    if not d.get("refresh_token"):
        return {"conta": conta, "situacao": "não autorizada"}
    try:
        falta = (float(d.get("expira_em", 0)) - _t.time()) / 60
    except (TypeError, ValueError):
        falta = 0.0
    return {"conta": conta, "situacao": "autorizada", "apelido": str(d.get("apelido", "")),
            "user_id": str(d.get("user_id", "")), "minutos_para_vencer": round(falta, 1),
            "atualizado_em": str(d.get("atualizado_em", ""))}


# ── Leitura ───────────────────────────────────────────────────────────────────
def get(conta, caminho, params=None):
    """GET num recurso da API. (json, erro) — nunca levanta. Só leitura."""
    tok, erro = token(conta)
    if erro:
        return (None, erro)
    url = BASE + ("" if caminho.startswith("/") else "/") + caminho
    for tentativa in range(2):
        try:
            r = requests.get(url, params=params or {}, timeout=TIMEOUT,
                             headers={"Authorization": f"Bearer {tok}"})
        except Exception as e:
            return (None, f"Mercado Livre não respondeu: {type(e).__name__}")
        if r.status_code == 429 and tentativa == 0:
            _t.sleep(1.5)
            continue
        break
    if r.status_code == 401:
        return (None, f"Mercado Livre recusou o token da {conta.upper()} (401)")
    if r.status_code == 403:
        return (None, f"o aplicativo não tem permissão para isto na {conta.upper()} (403)")
    if r.status_code == 429:
        return (None, "Mercado Livre: limite de requisições, mesmo após esperar")
    if not r.ok:
        return (None, f"Mercado Livre respondeu {r.status_code}")
    try:
        return (r.json(), "")
    except Exception:
        return (None, "Mercado Livre devolveu resposta que não é JSON")


def convites(conta):
    """As promoções disponíveis para a conta. (lista, erro).

    `GET /seller-promotions/users/{user_id}?app_version=v2`. A forma da
    resposta é conferida com dado real na tela de diagnóstico antes de
    qualquer tela de promoções ser desenhada em cima dela.
    """
    uid = str((_ler_da_planilha(conta) or {}).get("user_id", "")).strip()
    if not uid:
        return ([], f"{conta.upper()} ainda não foi autorizada")
    resp, erro = get(conta, f"/seller-promotions/users/{uid}", {"app_version": "v2"})
    if erro:
        return ([], erro)
    lista = resp.get("results") if isinstance(resp, dict) else resp
    return (lista if isinstance(lista, list) else [], "")



# O que o ML chama cada `status`, no nome que a equipe usa. Situação que não
# está aqui aparece crua — melhor que sumir com ela.
SITUACAO = {"started": "em andamento", "candidate": "disponível (convite)",
            "pending": "programada", "finished": "encerrada"}


def por_situacao(lista):
    """[{"situação", "tipo", "promoções"}] contando a lista de `convites`.

    Em andamento primeiro: é o que já está mexendo no preço agora."""
    cont = {}
    for p in lista or []:
        if not isinstance(p, dict):
            continue
        st_ = str(p.get("status", "?"))
        chave = (SITUACAO.get(st_, st_), str(p.get("type", "?")))
        cont[chave] = cont.get(chave, 0) + 1
    ordem = {v: i for i, v in enumerate(SITUACAO.values())}
    return [{"situação": s, "tipo": t, "promoções": n}
            for (s, t), n in sorted(cont.items(),
                                    key=lambda x: (ordem.get(x[0][0], 9), x[0][1]))]

if __name__ == "__main__":
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    _ps = por_situacao([{"id": "1", "status": "candidate", "type": "SMART"},
                        {"id": "2", "status": "started", "type": "DEAL"},
                        {"id": "3", "status": "candidate", "type": "SMART"},
                        {"id": "4", "status": "xyz", "type": "LIGHTNING"}, "lixo"])
    ok("SITUACAO: o status do ML vira o nome que a equipe usa",
       SITUACAO["started"] == "em andamento" and SITUACAO["candidate"].startswith("disponível"))
    ok("por_situacao: em andamento primeiro, convites somados por tipo, status novo aparece cru",
       _ps == [{"situação": "em andamento", "tipo": "DEAL", "promoções": 1},
               {"situação": "disponível (convite)", "tipo": "SMART", "promoções": 2},
               {"situação": "xyz", "tipo": "LIGHTNING", "promoções": 1}])
    ok("as quatro contas, com o CNPJ de cada uma (bling_api.py:19-20)",
       CONTAS == ("ml1", "ml2", "ml3", "ml4")
       and CNPJ_DA_CONTA == {"ml1": "LG", "ml3": "LG", "ml2": "MS", "ml4": "MS"})
    ok("conta_do_state: lê a conta e recusa o que não é do ML",
       conta_do_state("ml3.abc") == "ml3" and conta_do_state("lg.abc") == ""
       and conta_do_state("") == "" and conta_do_state(None) == "")
    ok("eh_callback: code + state de conta ML na raiz é o retorno do ML",
       eh_callback({"code": "TG-1", "state": "ml1.x"}))
    ok("eh_callback: o retorno do Bling não é do ML, nem página sem code",
       not eh_callback({"bling": "callback", "code": "c", "state": "ml1.x"})
       and not eh_callback({"state": "ml1.x"}) and not eh_callback({})
       and not eh_callback({"code": "c", "state": "lg.x"}))
    ok("processar_callback fora do retorno do ML não faz nada (nem abre a planilha)",
       processar_callback({"pagina": "home"}) == ("", "", ""))
    _url = url_montada("123", "ml2.abc")
    ok("a URL de autorização leva client_id, a redirect cadastrada e o state",
       _url.startswith(URL_AUTORIZA + "?") and "client_id=123" in _url
       and "redirect_uri=https%3A%2F%2Fapp.martinsousa.com.br" in _url and "state=ml2.abc" in _url)
    ok("conta_repetida: a mesma conta ML gravada com outro nome é recusada",
       conta_repetida("ml2", "999", {"ml1": {"user_id": 999}, "ml3": {"user_id": "5"}}) == "ml1")
    ok("conta_repetida: reautorizar a mesma conta com o mesmo nome passa; sem user_id não acusa",
       conta_repetida("ml1", "999", {"ml1": {"user_id": "999"}}) == ""
       and conta_repetida("ml1", "", {"ml2": {"user_id": ""}}) == "")
    _l = linha_mesclada("ml1", {"conta": "ml1", "access_token": "A", "refresh_token": "R",
                                "user_id": "7", "apelido": "LOJA"}, {"state_pendente": "ml1.s"}, "20/10/2026 16:00")
    ok("gravar o state preserva token, user_id e apelido (campo ausente não zera)",
       _l[COLUNAS.index("access_token")] == "A" and _l[COLUNAS.index("refresh_token")] == "R"
       and _l[COLUNAS.index("user_id")] == "7" and _l[COLUNAS.index("apelido")] == "LOJA"
       and _l[COLUNAS.index("state_pendente")] == "ml1.s" and _l[COLUNAS.index("atualizado_em")] == "20/10/2026 16:00"
       and len(_l) == len(COLUNAS))
    ok("estado de um registro autorizado mostra apelido e user_id, sem o token",
       (lambda e: e["situacao"] in ("autorizada", "sem credenciais") and "access_token" not in e)(
           estado("ml1", {"refresh_token": "R", "access_token": "A", "apelido": "LOJA", "user_id": "7"})))
    ok("a aba e a leitura dos tokens usam o cache do Streamlit (limpável), e não dicionário de módulo",
       hasattr(_aba, "clear") and hasattr(_todas, "clear"))
    ok("as decisões de vencimento são as do Bling, não uma cópia",
       precisa_renovar.__module__ == "bling_api" and vencimento.__module__ == "bling_api")

    # PELA CADEIA: o retorno do ML passa por processar_callback → state →
    # troca do code → /users/me → gravação. Só a planilha e a rede são
    # trocadas; o corpo do /oauth/token tem os campos que a documentação do
    # ML mostra (access_token, refresh_token, expires_in, scope, user_id).
    _g = (credenciais, _todas, _gravar_na_planilha, _post_token, _quem_sou)
    _gravado = {}
    _planilha = {"ml1": {"conta": "ml1", "state_pendente": "ml1.certo"},
                 "ml3": {"conta": "ml3", "user_id": "555", "refresh_token": "R3"}}
    try:
        credenciais = lambda: ("1", "2")
        _todas = lambda: _planilha
        _gravar_na_planilha = lambda conta, dados: (_gravado.setdefault(conta, {}).update(dados), True)[1]
        _post_token = lambda dados: ({"access_token": "A", "refresh_token": "R", "expires_in": 21600,
                                      "scope": "offline_access read write", "user_id": 999}, "")
        _quem_sou = lambda tok: ("999", "LOJA1")
        ok("callback com state que não confere não troca o code",
           processar_callback({"code": "TG-1", "state": "ml1.outro"})[2].startswith("o `state` não confere")
           and not _gravado)
        _r = processar_callback({"code": "TG-1", "state": "ml1.certo"})
        ok("callback certo grava token, user_id e apelido, e gasta o state",
           _r == ("ml1", "LOJA1", "") and _gravado["ml1"]["refresh_token"] == "R"
           and _gravado["ml1"]["user_id"] == "999" and _gravado["ml1"]["apelido"] == "LOJA1"
           and _gravado["ml1"]["state_pendente"] == "")
        _gravado.clear()
        _planilha["ml2"] = {"conta": "ml2", "state_pendente": "ml2.ok"}
        _quem_sou = lambda tok: ("555", "LOJA3")
        _r2 = processar_callback({"code": "TG-2", "state": "ml2.ok"})
        ok("autorizar ML2 logado na conta que já é ML3 é recusado e nada é gravado",
           _r2[0] == "" and "já está ligada como ML3" in _r2[2] and "ml2" not in _gravado)
    finally:
        credenciais, _todas, _gravar_na_planilha, _post_token, _quem_sou = _g

    # ── SITUACAO: O NOME QUE O admin.py LE ──────────────────────────────
    #
    # `checar_impacto` reprovou o nome: ele tem leitor em outro arquivo
    # (`admin.py`) e nenhuma guarda citava ele. A guarda mede o que a tela
    # depende: cada codigo que o Mercado Livre manda vira UM rotulo em
    # portugues, e a ORDEM e a do dicionario — "em andamento" primeiro,
    # porque e o que ja esta mexendo no preco agora.
    #
    # E ela mede pela CADEIA (`por_situacao`), e nao so o dicionario: e a
    # funcao que a tela chama, e e nela que a traducao e a ordem acontecem.
    ok("todo codigo do ML tem rotulo em portugues",
       set(SITUACAO) == {"started", "candidate", "pending", "finished"}
       and all(isinstance(v, str) and v for v in SITUACAO.values()))
    _promos = [{"status": "finished", "type": "DEAL"},
               {"status": "started", "type": "DEAL"},
               {"status": "started", "type": "DEAL"},
               {"status": "candidate", "type": "PRICE_MATCH"}]
    _por = por_situacao(_promos)
    ok("a contagem agrupa por situacao E tipo",
       {(d["situação"], d["tipo"], d["promoções"]) for d in _por}
       == {("em andamento", "DEAL", 2), ("disponível (convite)", "PRICE_MATCH", 1),
           ("encerrada", "DEAL", 1)})
    ok("e 'em andamento' vem primeiro, que e o que mexe no preco agora",
       _por[0]["situação"] == "em andamento")
    # CODIGO QUE O ML INVENTAR AMANHA NAO SOME DA TELA: ele aparece com o
    # nome cru, no fim. Sumir seria promocao ativa que ninguem ve.
    _novo = por_situacao([{"status": "xpto_novo", "type": "DEAL"}])
    ok("codigo desconhecido aparece cru em vez de sumir",
       _novo and _novo[0]["situação"] == "xpto_novo")

    print(f"\nfalhas: {falhas}")
    raise SystemExit(1 if falhas else 0)
