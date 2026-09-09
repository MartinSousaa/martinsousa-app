"""bling_api.py — Acesso à API v3 do Bling, com o token se renovando sozinho.

O QUE ESTE MÓDULO RESOLVE
-------------------------
O Bling usa OAuth 2 com Authorization Code, e o `access_token` vence. Quem
guarda o token na memória do processo perde ele em todo deploy e em todo
reinício do container — e no Railway isso acontece várias vezes por dia. O
sintoma não é um erro na tela: é a integração parar no meio da tarde, calada,
e alguém descobrir horas depois pelo número errado.

Então o token mora na PLANILHA, como os tokens de login já moram
(auth.py:34-46). Ele atravessa deploy, reinício e os dois processos do
container — o Streamlit e o tv_worker.

DUAS CONTAS, UM CNPJ CADA
-------------------------
São 2 contas Bling, 5 canais cada, cobrindo os 10:

    lg   ML1, ML3, Shopee 2, Shein 1, TikTok 1
    ms   ML2, ML4, Shopee 1, Shein 2, TikTok 2

Cada uma tem o seu aplicativo, o seu par de credenciais e o seu token. Nada
aqui assume ordem: a conta é sempre nomeada.

O QUE ESTE MÓDULO **NÃO** FAZ
-----------------------------
Não lê valor. Ficou decidido que o Bling entra só para situação de pedido e
cancelamento — os valores continuam vindo da planilha, porque o dado do Bling
ainda não passou pelo teste dos 5 pedidos que saíram errados no relatório.
Somar faturamento aqui faria a mesma pergunta ter duas respostas no sistema, e
elas passariam a discordar; a questão seria só quando.

Só escreve na planilha (o token). No Bling, só GET.

O RELÓGIO
---------
Vencimento é guardado em EPOCH, nunca em hora local. O container do Railway
roda em UTC e `datetime.now()` devolve UTC; epoch não tem esse problema porque
não tem fuso nenhum.
"""

import time as _t
import secrets as _secrets_py

import requests

# O `streamlit` e importado DENTRO das funcoes que precisam dele, e nao aqui em
# cima como no resto do repositorio. O motivo e a conferencia no fim do arquivo:
# ela roda com `python3 bling_api.py`, e um import de streamlit no topo faria o
# teste depender do ambiente inteiro estar montado — que e exatamente o tipo de
# teste que ninguem roda. As decisoes puras (vencimento, state, renovacao) ficam
# testaveis com a biblioteca padrao e mais nada.

# ── Constantes ────────────────────────────────────────────────────────────────
CONTAS = ("lg", "ms")

BASE = "https://api.bling.com.br/Api/v3"
URL_AUTORIZA = "https://bling.com.br/Api/v3/oauth/authorize"
URL_TOKEN = BASE + "/oauth/token"

# Conexão curta, leitura generosa — o mesmo critério do Trello (placar_core.py:13)
# e da planilha (sheets.py:38). Chamada sem timeout foi o que ja pendurou a TV.
TIMEOUT = (10, 30)

# Quanto antes do vencimento o token e renovado. Dez minutos: curto o bastante
# para nao renovar a toa, longo o bastante para uma chamada que comeca agora nao
# terminar com token vencido.
MARGEM_RENOVACAO_SEG = 600

ABA = "bling_tokens"
COLUNAS = ["conta", "access_token", "refresh_token", "expira_em",
           "atualizado_em", "escopo", "state_pendente"]

# O `state` fica na PLANILHA, nao no st.session_state.
#
# Autorizar e uma navegacao para fora do Studio e uma volta: o navegador sai
# para o Bling e retorna numa carga de pagina nova, que no Streamlit e outra
# sessao. Guardar o state em session_state daria um valor que nunca volta, e a
# conferencia passaria a comparar o que se pediu com nada — sempre falhando, ou
# pior, sendo desligada por "nao funcionar". Guardado na planilha, ele
# atravessa a ida, a volta e ate um deploy no meio.

# O `code` do Bling vive UM MINUTO. Nao da para alguem copiar da barra de
# enderecos e colar noutro lugar: a troca acontece na mesma requisicao que
# recebe o callback.
CHAVE_STATE = "_bling_state"

# Cache por processo. Sem ele, cada rerun do Streamlit abriria a planilha —
# e foi cache dado como pago sem conferencia que fez uma tela levar 15
# segundos para abrir.
_CACHE = {}


# ── Credenciais ───────────────────────────────────────────────────────────────
def credenciais(conta):
    """(client_id, client_secret) da conta. ('', '') quando não configurada.

    Os valores vêm das Variáveis do Railway, via `STREAMLIT_SECRETS`. Nunca do
    repositório: um commit de secret já derrubou o Fim de Expediente.
    """
    try:
        import streamlit as _st
        bloco = _st.secrets["bling"][conta]
        return (str(bloco["client_id"]).strip(),
                str(bloco["client_secret"]).strip())
    except Exception:
        return ("", "")


def configurada(conta):
    """A conta tem credenciais? Serve para a tela dizer o que falta."""
    cid, seg = credenciais(conta)
    return bool(cid and seg)


# ── Decisões puras (testadas no fim do arquivo) ───────────────────────────────
def precisa_renovar(expira_em, agora=None, margem=MARGEM_RENOVACAO_SEG):
    """O token vence antes da margem? Sem carimbo legível, sim — por segurança.

    Um vencimento ilegível significa "não sei", e não sei tem que renovar: o
    contrário é seguir usando um token que talvez já esteja morto e descobrir
    pelo primeiro 401 em produção.
    """
    agora = agora if agora is not None else _t.time()
    try:
        return (float(expira_em) - agora) <= margem
    except (TypeError, ValueError):
        return True


def vencimento(expires_in, agora=None):
    """Epoch em que o token vence, a partir do `expires_in` que o Bling mandou.

    Sem `expires_in` legível não se inventa prazo: devolve o instante atual, o
    que faz `precisa_renovar` responder sim na próxima leitura.
    """
    agora = agora if agora is not None else _t.time()
    try:
        return agora + float(expires_in)
    except (TypeError, ValueError):
        return agora


def state_novo():
    """Valor aleatório do `state`, que amarra o retorno ao pedido.

    Sem ele, qualquer um que descubra a URL de callback pode mandar um `code`
    e o Studio trocaria por um token achando que foi ele quem pediu.
    """
    return _secrets_py.token_urlsafe(24)


def state_confere(esperado, recebido):
    """Comparação de `state` em tempo constante, e falsa quando falta um lado."""
    if not esperado or not recebido:
        return False
    return _secrets_py.compare_digest(str(esperado), str(recebido))


# ── Autorização ───────────────────────────────────────────────────────────────
def url_de_autorizacao(conta):
    """URL para o gestor autorizar o aplicativo. ('', motivo) quando não dá.

    Grava o `state` na planilha ANTES de devolver a URL: ele precisa estar lá
    quando o Bling mandar o navegador de volta, numa sessão que ainda não
    existe. Se a gravação falhar, a URL não sai — autorizar sem poder conferir
    a volta seria abrir a porta e chamar isso de segurança.

    `redirect_uri` e `scope` não são enviados de propósito: a documentação do
    Bling diz que "sempre serão usados os valores inseridos previamente no
    cadastro de aplicativos, mesmo que os mesmos sejam utilizados na
    requisição". Mandar aqui daria a impressão de que este código controla
    algo que ele não controla.
    """
    conta = str(conta).strip().lower()
    if conta not in CONTAS:
        return ("", f"conta desconhecida: {conta}")
    cid, _seg = credenciais(conta)
    if not cid:
        return ("", f"conta '{conta}' sem credenciais configuradas")
    # A conta viaja DENTRO do state: o Bling devolve só `code` e `state`, e sem
    # isso o callback não saberia de qual das duas contas é o code que chegou.
    est = f"{conta}.{state_novo()}"
    if not _gravar_na_planilha(conta, {"state_pendente": est}):
        return ("", "não consegui guardar o state na planilha")
    url = (f"{URL_AUTORIZA}?response_type=code"
           f"&client_id={cid}&state={est}")
    return (url, "")


def processar_callback(params):
    """Trata o retorno `?bling=callback&code=…&state=…`. (conta, erro).

    Chamada no `app.py` a cada rerun, e sai calada quando não é um callback —
    o custo no caminho normal é uma leitura de dicionário.

    O `code` vive um minuto: a troca acontece aqui, no mesmo instante em que o
    navegador chega, sem ninguém copiar nada de lugar nenhum.
    """
    try:
        if str(params.get("bling", "")) != "callback":
            return ("", "")
        code = str(params.get("code", "")).strip()
        recebido = str(params.get("state", "")).strip()
    except Exception:
        return ("", "")
    if not code:
        return ("", "o Bling voltou sem `code` — a autorização foi negada")
    conta = conta_do_state(recebido)
    if not conta:
        return ("", "o `state` que voltou não diz de qual conta é")
    esperado = str((_ler_da_planilha(conta) or {}).get("state_pendente", ""))
    if not state_confere(esperado, recebido):
        # Ou o retorno nao corresponde a nenhum pedido feito por este Studio, ou
        # e um pedido antigo ja usado. Nos dois casos, nao se troca o code.
        return ("", "o `state` não confere com nenhuma autorização pedida")
    _dados, erro = trocar_code_por_token(conta, code)
    if erro:
        return ("", erro)
    # O state e de uso unico: gasto, sai da planilha para nao poder ser reusado.
    _gravar_na_planilha(conta, {"state_pendente": ""})
    return (conta, "")


def conta_do_state(recebido):
    """A conta embutida no `state`. '' quando não dá para ler."""
    try:
        conta = str(recebido).split(".", 1)[0]
        return conta if conta in CONTAS else ""
    except Exception:
        return ""


# ── HTTP ──────────────────────────────────────────────────────────────────────
def _basic(conta):
    """Cabeçalho Basic com client_id:client_secret em base64, como a doc pede.

    As credenciais vão no cabeçalho e não no corpo — a documentação é explícita
    de que não é permitido inseri-las no body.
    """
    import base64 as _b64
    cid, seg = credenciais(conta)
    par = f"{cid}:{seg}".encode("utf-8")
    return "Basic " + _b64.b64encode(par).decode("ascii")


def _post_token(conta, dados):
    """POST no /oauth/token. Devolve (json, erro) — nunca levanta.

    A mensagem de erro que sai daqui vai para a tela do gestor, então ela não
    pode carregar credencial: o corpo da resposta do Bling é lido, mas o
    cabeçalho enviado nunca é ecoado.
    """
    try:
        r = requests.post(
            URL_TOKEN, data=dados, timeout=TIMEOUT,
            headers={"Authorization": _basic(conta),
                     "Content-Type": "application/x-www-form-urlencoded",
                     "Accept": "application/json"})
    except Exception as e:
        return (None, f"Bling não respondeu: {type(e).__name__}")
    try:
        corpo = r.json()
    except Exception:
        return (None, f"Bling respondeu {r.status_code} sem JSON")
    if not r.ok:
        # O formato de erro do Bling e {"error": {"type", "message",
        # "description"}}. O `type` basta para o diagnostico e nao carrega dado.
        tipo = ""
        try:
            tipo = str((corpo.get("error") or {}).get("type") or "")
        except Exception:
            pass
        return (None, f"Bling recusou ({r.status_code}{': ' + tipo if tipo else ''})")
    return (corpo, "")


# ── Planilha ──────────────────────────────────────────────────────────────────
_ABA_CACHE = {}


def _aba():
    """Acessa (ou cria) a aba de tokens do Bling. Mesmo idioma do auth.py:34-46.

    A diferença é o cache: lá é `@st.cache_resource`, aqui é um dicionário de
    módulo. O decorador exigiria `import streamlit` no topo do arquivo, e é
    justamente isso que a conferência do fim não pode depender. O efeito é o
    mesmo — uma aba por processo.
    """
    if "aba" in _ABA_CACHE:
        return _ABA_CACHE["aba"]
    import gspread
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        aba = planilha.worksheet(ABA)
    except gspread.exceptions.WorksheetNotFound:
        aba = planilha.add_worksheet(title=ABA, rows=20, cols=len(COLUNAS))
        aba.append_row(COLUNAS, value_input_option="RAW")
    _ABA_CACHE["aba"] = aba
    return aba


def _ler_da_planilha(conta):
    """{campo: valor} da conta, direto da planilha. {} quando não há linha."""
    try:
        registros = _aba().get_all_records(value_render_option="UNFORMATTED_VALUE")
    except Exception:
        return {}
    for r in registros:
        if str(r.get("conta", "")).strip().lower() == conta:
            return dict(r)
    return {}


def _gravar_na_planilha(conta, dados):
    """Grava (ou substitui) a linha da conta. Uma linha por conta, sempre.

    `append_row` faria a aba crescer a cada renovação — quatro linhas por dia,
    por conta, para sempre — e a leitura passaria a ter que escolher qual das
    versões vale. Uma linha por conta não tem essa dúvida.

    Os campos ausentes em `dados` PRESERVAM o que já estava gravado, em vez de
    apagar. Sem isso, gravar o `state_pendente` zeraria o token da conta — e o
    estrago só apareceria na renovação seguinte, horas depois.
    """
    from datetime import datetime as _dt
    import placar_core as _pc
    try:
        aba = _aba()
        registros = aba.get_all_records(value_render_option="UNFORMATTED_VALUE")
        atual, alvo = {}, 0
        for i, r in enumerate(registros, start=2):   # linha 1 = cabeçalho
            if str(r.get("conta", "")).strip().lower() == conta:
                atual, alvo = dict(r), i
                break
        def _campo(nome):
            return str(dados[nome]) if nome in dados else str(atual.get(nome, ""))
        linha = [conta, _campo("access_token"), _campo("refresh_token"),
                 _campo("expira_em"),
                 _dt.now(_pc.FUSO).strftime("%d/%m/%Y %H:%M"),
                 _campo("escopo"), _campo("state_pendente")]
        if alvo:
            aba.update(f"A{alvo}:G{alvo}", [linha], value_input_option="RAW")
        else:
            aba.append_row(linha, value_input_option="RAW")
        return True
    except Exception:
        return False


# ── Token ─────────────────────────────────────────────────────────────────────
def _guardar(conta, corpo):
    """Normaliza a resposta do /token, grava na planilha e no cache."""
    dados = {
        "access_token": str(corpo.get("access_token", "")),
        # O Bling ROTACIONA o refresh_token a cada renovacao. Guardar o antigo
        # deixa a proxima renovacao sem chave, e aí só reautorizando na mão.
        "refresh_token": str(corpo.get("refresh_token", "")),
        "expira_em": vencimento(corpo.get("expires_in")),
        "escopo": str(corpo.get("scope", "")),
    }
    _gravar_na_planilha(conta, dados)
    _CACHE[conta] = dados
    return dados


def trocar_code_por_token(conta, code):
    """Troca o `code` do callback por tokens. (dados, erro).

    O `code` vive um minuto — por isso esta função é chamada no mesmo instante
    em que o callback chega, e não por alguém colando um valor numa tela.
    """
    if not configurada(conta):
        return ({}, f"conta '{conta}' sem credenciais configuradas")
    corpo, erro = _post_token(conta, {"grant_type": "authorization_code",
                                      "code": code})
    if erro:
        return ({}, erro)
    return (_guardar(conta, corpo), "")


def _renovar(conta, refresh_token):
    """Renova pelo refresh_token. (dados, erro)."""
    corpo, erro = _post_token(conta, {"grant_type": "refresh_token",
                                      "refresh_token": refresh_token})
    if erro:
        return ({}, erro)
    return (_guardar(conta, corpo), "")


def token(conta):
    """O access_token válido da conta, renovando se preciso. ('', motivo).

    A ordem importa: antes de renovar, relê a planilha. O Studio roda em mais
    de um processo (o Streamlit e o tv_worker) e pode ter várias sessões
    abertas; se outra já renovou, o refresh_token que este processo tem em
    memória virou lixo — o Bling rotaciona a cada uso. Reler primeiro faz o
    segundo processo aproveitar o token novo em vez de queimar a chave.
    """
    conta = str(conta).strip().lower()
    if conta not in CONTAS:
        return ("", f"conta desconhecida: {conta}")
    if not configurada(conta):
        return ("", f"conta '{conta}' sem credenciais configuradas")

    dados = _CACHE.get(conta) or {}
    if dados.get("access_token") and not precisa_renovar(dados.get("expira_em")):
        return (dados["access_token"], "")

    dados = _ler_da_planilha(conta) or {}
    if dados:
        _CACHE[conta] = dados
    if dados.get("access_token") and not precisa_renovar(dados.get("expira_em")):
        return (dados["access_token"], "")

    rt = str(dados.get("refresh_token", "")).strip()
    if not rt:
        return ("", f"conta '{conta}' ainda não foi autorizada")
    novos, erro = _renovar(conta, rt)
    if erro:
        return ("", f"não consegui renovar o token: {erro}")
    return (novos.get("access_token", ""), "")


def estado(conta):
    """Um resumo legível do token da conta, para a tela de configuração.

    Não devolve o token. O que o gestor precisa saber é se está valendo e até
    quando — o valor em si só serviria para vazar.
    """
    dados = _ler_da_planilha(conta) or {}
    if not configurada(conta):
        return {"conta": conta, "situacao": "sem credenciais"}
    if not dados.get("refresh_token"):
        return {"conta": conta, "situacao": "não autorizada"}
    falta = 0.0
    try:
        falta = (float(dados.get("expira_em", 0)) - _t.time()) / 60
    except (TypeError, ValueError):
        falta = 0.0
    return {"conta": conta,
            "situacao": "autorizada",
            "minutos_para_vencer": round(falta, 1),
            "renova_sozinho": True,
            "atualizado_em": str(dados.get("atualizado_em", "")),
            "escopo": str(dados.get("escopo", ""))}


# ── Leitura ───────────────────────────────────────────────────────────────────
def get(conta, caminho, params=None):
    """GET num recurso da API. (json, erro) — nunca levanta.

    Só GET, de propósito: o Studio lê o Bling e não escreve nele. Se um dia
    precisar escrever, que seja uma função nova, com nome que diga isso.
    """
    tok, erro = token(conta)
    if erro:
        return (None, erro)
    url = BASE + ("" if caminho.startswith("/") else "/") + caminho
    try:
        r = requests.get(url, params=params or {}, timeout=TIMEOUT,
                         headers={"Authorization": f"Bearer {tok}",
                                  "Accept": "application/json"})
    except Exception as e:
        return (None, f"Bling não respondeu: {type(e).__name__}")
    if r.status_code == 401:
        return (None, "Bling recusou o token (401)")
    if not r.ok:
        return (None, f"Bling respondeu {r.status_code}")
    try:
        return (r.json(), "")
    except Exception:
        return (None, "Bling devolveu resposta que não é JSON")


def pedido(conta, id_pedido):
    """Um pedido de venda pelo ID — é daqui que sai situação e cancelamento."""
    return get(conta, f"/pedidos/vendas/{id_pedido}")


def pedidos(conta, **filtros):
    """Lista de pedidos de venda. Os filtros vão como query string."""
    return get(conta, "/pedidos/vendas", params=filtros)


# ── Conferência ───────────────────────────────────────────────────────────────
# `python3 bling_api.py` roda os casos abaixo. Eles moram aqui, e não num
# arquivo à parte, porque este repositório não tem suíte: teste que não viaja
# junto do código é teste que ninguém roda.
#
# Só o que é decidível sem credencial e sem rede. A troca de token de verdade
# depende de alguém autorizar no navegador, e isso se confere no primeiro uso.
if __name__ == "__main__":
    falhas = 0

    def ok(nome, condicao):
        global falhas
        falhas += not condicao
        print(("ok    " if condicao else "FALHA ") + nome)

    AGORA = 1_000_000.0

    ok("token que vence em 2h não renova",
       precisa_renovar(AGORA + 7200, AGORA) is False)
    ok("token que vence em 5 min renova (margem de 10)",
       precisa_renovar(AGORA + 300, AGORA) is True)
    ok("token vencido renova",
       precisa_renovar(AGORA - 1, AGORA) is True)
    ok("vencimento exatamente na margem renova",
       precisa_renovar(AGORA + 600, AGORA) is True)
    ok("vencimento ilegível renova (não sei = renova)",
       precisa_renovar("", AGORA) is True and precisa_renovar(None, AGORA) is True)

    ok("expires_in de 6h vira epoch de 6h à frente",
       vencimento(21600, AGORA) == AGORA + 21600)
    ok("expires_in em texto também vale",
       vencimento("21600", AGORA) == AGORA + 21600)
    ok("expires_in ausente não inventa prazo",
       vencimento(None, AGORA) == AGORA)

    e1, e2 = state_novo(), state_novo()
    ok("dois states nunca são iguais", e1 != e2)
    ok("state confere consigo mesmo", state_confere(e1, e1) is True)
    ok("state não confere com outro", state_confere(e1, e2) is False)
    ok("state vazio nunca confere",
       state_confere("", "") is False and state_confere(e1, "") is False)

    ok("a conta viaja no state e volta", conta_do_state("lg.abc123") == "lg")
    ok("conta inventada no state é recusada", conta_do_state("xx.abc") == "")
    ok("state sem ponto não derruba", conta_do_state("semponto") == "")

    # Os caminhos do callback que decidem ANTES de tocar na planilha. O caminho
    # feliz depende de credencial e de rede, e se confere no primeiro uso real.
    ok("página normal não é callback: sai calado",
       processar_callback({}) == ("", ""))
    ok("outro parâmetro qualquer não é callback",
       processar_callback({"tv": "abc"}) == ("", ""))
    ok("callback sem code é autorização negada",
       processar_callback({"bling": "callback", "state": "lg.x"})[1].startswith(
           "o Bling voltou sem"))
    ok("callback com state de conta inventada é recusado",
       processar_callback({"bling": "callback", "code": "c", "state": "xx.y"})[1]
       .startswith("o `state` que voltou"))
    ok("callback sem state é recusado",
       processar_callback({"bling": "callback", "code": "c"})[1]
       .startswith("o `state` que voltou"))

    print("\nfalhas:", falhas)
