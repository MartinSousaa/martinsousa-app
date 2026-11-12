"""shopee_api.py — Acesso à Open Platform v2 da Shopee: pedidos, ads e promoções.

POR QUE EXISTE (dono, 12/11)
----------------------------
"Além das vendas da Shopee, precisamos ter acesso a ads e promoções. O Bling
traz as vendas, mas pode ser que ele traga com um nome diferente do que está
na plataforma." Daqui saem três coisas:

  1. o NOME do anúncio como a Shopee mostra, ligado ao SKU (`item_list` do
     pedido) — é a ponte entre a plataforma, o Bling e o estoque;
  2. o gasto de ads por dia (`get_all_cpc_ads_daily_performance`);
  3. as promoções ativas (`get_discount_list`) e os cupons (`get_voucher_list`).

O FATURAMENTO NÃO SAI DAQUI. Ele vem da BASE DE VENDAS (`bling_api.py:26-31`).
Somar valor aqui daria duas respostas para a mesma pergunta.

DE ONDE VEM CADA REGRA (conferido em 12/11)
-------------------------------------------
Nos JSON oficiais que as páginas de open.shopee.com carregam (guias 16 "API
calls" e 20 "Authorization and Authentication", e a página de cada API), e no
código de dois SDKs (`@congminh1254/shopee-sdk` 2.14.1 e `pyshopee` 1.4.0):

  - assinatura: HMAC-SHA256 com a partner_key, hexadecimal minúsculo, sobre
    partner_id + caminho + timestamp (pública) ou
    partner_id + caminho + timestamp + access_token + shop_id (loja);
  - o timestamp é em segundos e vale 5 minutos;
  - access_token dura 4 horas; o refresh_token dura 30 dias e vale UMA vez
    (a renovação devolve um novo, que tem de ser gravado);
  - pedidos: janela de no máximo 15 dias, até 100 por página, detalhe de até
    50 por vez, e `item_list` só vem se pedido em `response_optional_fields`;
  - ads: datas DD-MM-AAAA, no máximo 1 mês, início diferente do fim, e não
    mais velho que 6 meses;
  - toda resposta traz `error` (vazio quando deu certo) e `message`.

Nada disso foi testado com chamada real: as chaves só existem no Railway. A
primeira leitura confirma ou desmente, e o erro vem com o texto da Shopee.

DUAS LOJAS
----------
Shopee 1 (CNPJ MS) e Shopee 2 (CNPJ LG), como em `bling_api.py:19-20`. Um
aplicativo (partner) autorizado em cada loja; `SHOPEE_PARTNER_ID` e
`SHOPEE_PARTNER_KEY` moram nas Variáveis do Railway, e os tokens na aba
`shopee_tokens` da planilha, para atravessar deploy.

A AUTORIZAÇÃO
-------------
O link fixo do Brasil (`open.shopee.com.br/auth`) com `state`. A Shopee volta
para a raiz do Studio com `?code=…&shop_id=…`. O `shop_id` é o que separa a
volta da Shopee da volta do Mercado Livre (que não traz `shop_id`). Se o
`state` vier, ele diz qual loja; se não vier, vale a loja com autorização
pendente — e havendo duas pendentes, o Studio recusa em vez de adivinhar.
"""

import hashlib
import hmac
import time as _t
from datetime import datetime, timedelta

import requests
import streamlit as st

from bling_api import precisa_renovar, state_confere, state_novo, vencimento

LOJAS = ("shp1", "shp2")
NOME_DA_LOJA = {"shp1": "Shopee 1 (MS)", "shp2": "Shopee 2 (LG)"}

# Os dois hosts de produção valem; a Shopee pede o mais perto do servidor
# (guia 16). O SDK usa este para o Brasil.
HOST = "https://openplatform.shopee.com.br"
URL_AUTORIZA = "https://open.shopee.com.br/auth"
REDIRECT_URI = "https://app.martinsousa.com.br"
TIMEOUT = (10, 30)

ABA = "shopee_tokens"
COLUNAS = ["conta", "access_token", "refresh_token", "expira_em",
           "atualizado_em", "state_pendente", "shop_id"]

JANELA_PEDIDOS = 15   # dias por chamada de lista de pedidos
POR_PAGINA = 100
DETALHE_POR_VEZ = 50
JANELA_ADS = 30       # dias por chamada de ads (o limite é 1 mês)
MAX_PAGINAS = 50      # por janela / por lista: passou disso, INCOMPLETO


# ── Credenciais ───────────────────────────────────────────────────────────────
def credenciais():
    import chaves
    return (chaves.ler("SHOPEE_PARTNER_ID"), chaves.ler("SHOPEE_PARTNER_KEY"))


def configurado():
    pid, chave = credenciais()
    return bool(pid and chave)


FALTA_CREDENCIAL = "faltam SHOPEE_PARTNER_ID e SHOPEE_PARTNER_KEY nas Variáveis do Railway"


# ── Decisões puras ────────────────────────────────────────────────────────────
def assinar(chave, partner_id, caminho, ts, access_token="", shop_id=""):
    """A assinatura da Shopee. Sem token: pública. Com token: de loja."""
    base = f"{partner_id}{caminho}{ts}{access_token}{shop_id}"
    return hmac.new(str(chave).encode(), base.encode(), hashlib.sha256).hexdigest()


def parametros_comuns(partner_id, chave, caminho, ts, access_token="", shop_id=""):
    p = {"partner_id": int(partner_id), "timestamp": int(ts),
         "sign": assinar(chave, partner_id, caminho, ts, access_token, shop_id)}
    if access_token:
        p.update(access_token=access_token, shop_id=int(shop_id))
    return p


def loja_do_state(recebido):
    try:
        loja = str(recebido).split(".", 1)[0]
        return loja if loja in LOJAS else ""
    except Exception:
        return ""


def eh_callback(params):
    """A volta da Shopee: `code` e `shop_id` na raiz. O ML não traz shop_id."""
    try:
        if str(params.get("bling", "")):
            return False
        return bool(str(params.get("code", "")).strip()
                    and str(params.get("shop_id", "")).strip())
    except Exception:
        return False


def loja_da_volta(params, gravados):
    """(loja, erro). O state decide; sem ele, a ÚNICA loja pendente."""
    recebido = str(params.get("state", "") or "").strip()
    if recebido:
        loja = loja_do_state(recebido)
        esperado = str((gravados.get(loja) or {}).get("state_pendente", ""))
        if not loja or not state_confere(esperado, recebido):
            return ("", "o `state` não confere com nenhuma autorização pedida")
        return (loja, "")
    pendentes = [l for l in LOJAS if str((gravados.get(l) or {}).get("state_pendente", ""))]
    if len(pendentes) == 1:
        return (pendentes[0], "")
    if not pendentes:
        return ("", "a Shopee voltou sem nenhuma autorização pedida pelo Studio")
    return ("", "as duas lojas estavam esperando autorização e a Shopee não disse qual "
                "é esta. Gere o link de uma loja por vez.")


def loja_repetida(loja, shop_id, gravados):
    sid = str(shop_id or "").strip()
    for outra, d in (gravados or {}).items():
        if sid and outra != loja and str((d or {}).get("shop_id", "")).strip() == sid:
            return outra
    return ""


def url_montada(partner_id, est):
    from urllib.parse import urlencode
    return URL_AUTORIZA + "?" + urlencode({"partner_id": partner_id, "auth_type": "seller",
                                           "redirect_uri": REDIRECT_URI,
                                           "response_type": "code", "state": est})


def janelas(de, ate, dias):
    """[(início, fim)] de no máximo `dias`, cobrindo [de, ate] sem buraco."""
    saida, ini = [], de
    while ini < ate:
        fim = min(ini + timedelta(days=dias), ate)
        saida.append((ini, fim))
        ini = fim
    return saida


def erro_da_resposta(corpo):
    """'' quando deu certo; senão o erro com a mensagem da Shopee."""
    if not isinstance(corpo, dict):
        return "a Shopee devolveu resposta que não é JSON"
    e = str(corpo.get("error") or "").strip()
    if not e:
        return ""
    msg = str(corpo.get("message") or "").strip()
    return f"Shopee: {e}" + (f" — {msg}" if msg else "")


# ── Planilha ──────────────────────────────────────────────────────────────────
@st.cache_resource
def _aba():
    import gspread
    import sheets as _sh
    planilha = _sh.planilha()
    try:
        return planilha.worksheet(ABA)
    except gspread.exceptions.WorksheetNotFound:
        aba = planilha.add_worksheet(title=ABA, rows=10, cols=len(COLUNAS))
        aba.append_row(COLUNAS, value_input_option="RAW")
        return aba


def _reler():
    getattr(_todas, "clear", lambda: None)()


@st.cache_data(ttl=300, show_spinner=False)
def _todas():
    try:
        regs = _aba().get_all_records(value_render_option="UNFORMATTED_VALUE")
    except Exception:
        return {}
    return {str(r.get("conta", "")).strip().lower(): dict(r) for r in regs
            if str(r.get("conta", "")).strip()}


def linha_mesclada(loja, atual, dados, agora_txt):
    """Campo ausente PRESERVA o gravado — gravar o state não zera o token."""
    def campo(nome):
        return str(dados[nome]) if nome in dados else str((atual or {}).get(nome, ""))
    return [loja] + [agora_txt if c == "atualizado_em" else campo(c) for c in COLUNAS[1:]]


def _gravar(loja, dados):
    import placar_core as _pc
    try:
        aba = _aba()
        registros = aba.get_all_records(value_render_option="UNFORMATTED_VALUE")
        atual, alvo = {}, 0
        for i, r in enumerate(registros, start=2):
            if str(r.get("conta", "")).strip().lower() == loja:
                atual, alvo = dict(r), i
                break
        linha = linha_mesclada(loja, atual, dados,
                               datetime.now(_pc.FUSO).strftime("%d/%m/%Y %H:%M"))
        if alvo:
            fim = chr(ord("A") + len(COLUNAS) - 1)
            aba.update(f"A{alvo}:{fim}{alvo}", [linha], value_input_option="RAW")
        else:
            aba.append_row(linha, value_input_option="RAW")
        _reler()
        return True
    except Exception:
        return False


# ── HTTP ──────────────────────────────────────────────────────────────────────
def _ida(metodo, caminho, params, corpo=None):
    """A ÚNICA ida à Shopee. (json, erro), nunca levanta, nunca ecoa segredo.
    Não lê session_state: pode rodar dentro de thread."""
    for tentativa in range(2):
        try:
            r = requests.request(metodo, HOST + caminho, params=params, json=corpo,
                                 timeout=TIMEOUT)
        except Exception as e:
            return (None, f"Shopee não respondeu: {type(e).__name__}")
        try:
            dado = r.json()
        except Exception:
            dado = None
        limite = r.status_code == 429 or (isinstance(dado, dict) and "rate_limit" in
                                          str(dado.get("error", "")))
        if limite and tentativa == 0:
            _t.sleep(1.5)
            continue
        break
    if dado is None:
        return (None, f"Shopee respondeu {r.status_code} sem JSON")
    erro = erro_da_resposta(dado)
    if erro:
        return (None, erro)
    if not r.ok:
        return (None, f"Shopee respondeu {r.status_code}")
    return (dado, "")


def _post_publico(caminho, corpo):
    pid, chave = credenciais()
    ts = int(_t.time())
    return _ida("POST", caminho, parametros_comuns(pid, chave, caminho, ts),
                {**corpo, "partner_id": int(pid)})


# ── Autorização e token ───────────────────────────────────────────────────────
def url_de_autorizacao(loja):
    loja = str(loja).strip().lower()
    if loja not in LOJAS:
        return ("", f"loja desconhecida: {loja}")
    if not configurado():
        return ("", FALTA_CREDENCIAL)
    est = f"{loja}.{state_novo()}"
    if not _gravar(loja, {"state_pendente": est}):
        return ("", "não consegui guardar o state na planilha")
    return (url_montada(credenciais()[0], est), "")


def _guardar(loja, corpo, extra=None):
    dados = {"access_token": str(corpo.get("access_token", "")),
             # vale UMA vez: guardar o velho deixa a próxima renovação sem chave
             "refresh_token": str(corpo.get("refresh_token", "")),
             "expira_em": vencimento(corpo.get("expire_in"))}
    dados.update(extra or {})
    _gravar(loja, dados)
    return dados


def processar_callback(params):
    """(loja, shop_id, erro) — calado fora do callback."""
    if not eh_callback(params):
        return ("", "", "")
    if not configurado():
        return ("", "", FALTA_CREDENCIAL)
    _reler()
    gravados = _todas()
    loja, erro = loja_da_volta(params, gravados)
    if erro:
        return ("", "", erro)
    shop_id = str(params.get("shop_id", "")).strip()
    outra = loja_repetida(loja, shop_id, gravados)
    if outra:
        return ("", "", f"esta loja (shop_id {shop_id}) já está ligada como "
                        f"{NOME_DA_LOJA[outra]}. Entre na outra loja e autorize de novo.")
    corpo, erro = _post_publico("/api/v2/auth/token/get",
                                {"code": str(params.get("code", "")).strip(),
                                 "shop_id": int(shop_id)})
    if erro:
        return ("", "", erro)
    _guardar(loja, corpo, {"shop_id": shop_id, "state_pendente": ""})
    return (loja, shop_id, "")


def token(loja):
    """(access_token, shop_id, erro), renovando se preciso."""
    loja = str(loja).strip().lower()
    if loja not in LOJAS:
        return ("", "", f"loja desconhecida: {loja}")
    if not configurado():
        return ("", "", FALTA_CREDENCIAL)
    d = _todas().get(loja) or {}
    if d.get("access_token") and not precisa_renovar(d.get("expira_em")):
        return (str(d["access_token"]), str(d.get("shop_id", "")), "")
    _reler()       # outra sessão pode ter renovado; o refresh velho já não vale
    d = _todas().get(loja) or {}
    if d.get("access_token") and not precisa_renovar(d.get("expira_em")):
        return (str(d["access_token"]), str(d.get("shop_id", "")), "")
    rt, sid = str(d.get("refresh_token", "")).strip(), str(d.get("shop_id", "")).strip()
    if not rt or not sid:
        return ("", "", f"{NOME_DA_LOJA[loja]} ainda não foi autorizada")
    corpo, erro = _post_publico("/api/v2/auth/access_token/get",
                                {"refresh_token": rt, "shop_id": int(sid)})
    if erro:
        return ("", "", f"não consegui renovar o token da {NOME_DA_LOJA[loja]}: {erro}")
    return (_guardar(loja, corpo).get("access_token", ""), sid, "")


def estados():
    todas = _todas() if configurado() else {}
    saida = {}
    for l in LOJAS:
        d = todas.get(l, {})
        if not configurado():
            saida[l] = {"situacao": "sem credenciais"}
        elif not d.get("refresh_token"):
            saida[l] = {"situacao": "não autorizada"}
        else:
            saida[l] = {"situacao": "autorizada", "shop_id": str(d.get("shop_id", "")),
                        "atualizado_em": str(d.get("atualizado_em", ""))}
    return saida


# ── Leitura ───────────────────────────────────────────────────────────────────
def chamar(credencial, caminho, params=None, ida=None):
    """GET de loja, com a credencial JÁ em mãos: (partner_id, chave, token, shop_id).
    Separada de `token` para poder rodar em thread."""
    ida = ida or _ida
    pid, chave, tok, sid = credencial
    ts = int(_t.time())
    return ida("GET", caminho, {**(params or {}),
                                **parametros_comuns(pid, chave, caminho, ts, tok, sid)})


def credencial_da_loja(loja):
    """((partner_id, chave, token, shop_id), erro). Na thread da tela."""
    tok, sid, erro = token(loja)
    if erro:
        return (None, erro)
    pid, chave = credenciais()
    return ((pid, chave, tok, sid), "")


def pedidos(credencial, de, ate, ida=None):
    """Itens vendidos entre `de` e `ate` (datetime com fuso).

    {"itens": [...], "pedidos": n, "erro": str, "incompleto": bool}
    Cada item: order_sn, criado (epoch), status, item_id, item_name,
    model_name, item_sku, model_sku, sku (o do modelo, senão o do anúncio), qtd.
    """
    sns, erro, incompleto = [], "", False
    for ini, fim in janelas(de, ate, JANELA_PEDIDOS):
        cursor = ""
        for pagina in range(MAX_PAGINAS):
            corpo, erro = chamar(credencial, "/api/v2/order/get_order_list",
                                 {"time_range_field": "create_time",
                                  "time_from": int(ini.timestamp()),
                                  "time_to": int(fim.timestamp()),
                                  "page_size": POR_PAGINA, "cursor": cursor,
                                  "response_optional_fields": "order_status"}, ida)
            if erro:
                break
            r = corpo.get("response") or {}
            sns.extend(o.get("order_sn") for o in r.get("order_list") or [] if o.get("order_sn"))
            cursor = str(r.get("next_cursor") or "")
            if not r.get("more"):
                break
        else:
            incompleto = True
        if erro:
            break
    itens = []
    for i in range(0, len(sns), DETALHE_POR_VEZ):
        if erro:
            break
        corpo, erro = chamar(credencial, "/api/v2/order/get_order_detail",
                             {"order_sn_list": ",".join(sns[i:i + DETALHE_POR_VEZ]),
                              "response_optional_fields": "item_list"}, ida)
        if erro:
            break
        for o in (corpo.get("response") or {}).get("order_list") or []:
            for it in o.get("item_list") or []:
                msku, isku = str(it.get("model_sku") or "").strip(), str(it.get("item_sku") or "").strip()
                itens.append({"order_sn": o.get("order_sn"), "criado": o.get("create_time"),
                              "status": o.get("order_status"), "item_id": it.get("item_id"),
                              "item_name": str(it.get("item_name") or ""),
                              "model_name": str(it.get("model_name") or ""),
                              "item_sku": isku, "model_sku": msku, "sku": msku or isku,
                              "qtd": int(it.get("model_quantity_purchased") or 0)})
    return {"itens": itens, "pedidos": len(sns), "erro": erro,
            "incompleto": incompleto or bool(erro)}


def nomes_por_sku(itens, sku_do_estoque=None):
    """[{sku, nomes, vendidos, no_estoque}] — a ponte plataforma ↔ SKU.

    `sku_do_estoque`: o conjunto de SKUs normalizados do estoque, ou None.
    Item sem SKU entra com sku "" e o nome dele: é exatamente o que falta
    cadastrar na Shopee.
    """
    import estoque as _e
    por = {}
    for it in itens:
        if str(it.get("status", "")).upper() in ("CANCELLED", "IN_CANCEL", "UNPAID"):
            continue
        sku = _e.normalizar_sku(it.get("sku", ""))
        nome = it["item_name"] + (f" · {it['model_name']}" if it.get("model_name") else "")
        d = por.setdefault(sku, {"sku": sku, "nomes": set(), "vendidos": 0})
        d["nomes"].add(nome)
        d["vendidos"] += it.get("qtd", 0)
    saida = []
    for sku, d in sorted(por.items(), key=lambda kv: -kv[1]["vendidos"]):
        saida.append({"sku": sku, "nomes": sorted(d["nomes"]), "vendidos": d["vendidos"],
                      "no_estoque": (None if sku_do_estoque is None or not sku
                                     else sku in sku_do_estoque)})
    return saida


def _data_ads(dt):
    return dt.strftime("%d-%m-%Y")


def ads_diario(credencial, de, ate, ida=None):
    """{"dias": [{data, expense, broad_gmv, broad_order, clicks, impression}],
    "erro": str}. Janela de até 30 dias por chamada; início ≠ fim."""
    dias, erro = [], ""
    for ini, fim in janelas(de, ate, JANELA_ADS):
        if ini.date() == fim.date():
            continue
        corpo, erro = chamar(credencial, "/api/v2/ads/get_all_cpc_ads_daily_performance",
                             {"start_date": _data_ads(ini), "end_date": _data_ads(fim)}, ida)
        if erro:
            break
        for d in corpo.get("response") or []:
            dias.append({k: d.get(k) for k in ("date", "expense", "broad_gmv", "broad_order",
                                                "direct_gmv", "clicks", "impression")})
    vistos, unicos = set(), []
    for d in dias:              # janelas encostam no dia da emenda
        if d["date"] not in vistos:
            vistos.add(d["date"])
            unicos.append(d)
    return {"dias": unicos, "erro": erro}


def _lista_paginada(credencial, caminho, chave_lista, params, ida=None):
    lista, erro = [], ""
    for pagina in range(1, MAX_PAGINAS + 1):
        corpo, erro = chamar(credencial, caminho, {**params, "page_no": pagina,
                                                   "page_size": POR_PAGINA}, ida)
        if erro:
            return {"lista": lista, "erro": erro, "incompleto": True}
        r = corpo.get("response") or {}
        lista.extend(r.get(chave_lista) or [])
        if not r.get("more"):
            return {"lista": lista, "erro": "", "incompleto": False}
    return {"lista": lista, "erro": "", "incompleto": True}


def promocoes(credencial, situacao="ongoing", ida=None):
    """Descontos (`discount_list`) e cupons (`voucher_list`) da loja."""
    return {"descontos": _lista_paginada(credencial, "/api/v2/discount/get_discount_list",
                                         "discount_list", {"discount_status": situacao}, ida),
            "cupons": _lista_paginada(credencial, "/api/v2/voucher/get_voucher_list",
                                      "voucher_list", {"status": situacao}, ida)}


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from datetime import timezone
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    BR = timezone(timedelta(hours=-3))

    # Assinatura: HMAC-SHA256 hexadecimal minúsculo sobre a base da Shopee.
    _s = assinar("chave", "2001", "/api/v2/order/get_order_list", 1700000000, "tok", "77")
    _esp = hmac.new(b"chave", b"2001/api/v2/order/get_order_list1700000000tok77",
                    hashlib.sha256).hexdigest()
    ok("assinatura de loja: partner_id+caminho+ts+token+shop_id", _s == _esp)
    ok("e sai em hexadecimal minúsculo", _s == _s.lower() and len(_s) == 64)
    ok("assinatura pública não leva token nem loja",
       assinar("chave", "2001", "/api/v2/auth/token/get", 5) ==
       hmac.new(b"chave", b"2001/api/v2/auth/token/get5", hashlib.sha256).hexdigest())
    _p = parametros_comuns("2001", "chave", "/x", 5, "tok", "77")
    ok("parâmetros de loja levam token e shop_id numéricos",
       _p["partner_id"] == 2001 and _p["shop_id"] == 77 and _p["access_token"] == "tok")
    ok("parâmetros públicos não levam token", "access_token" not in parametros_comuns("1", "k", "/x", 5))

    # A volta: shop_id separa da do ML; state decide a loja.
    ok("volta da Shopee reconhecida pelo shop_id", eh_callback({"code": "c", "shop_id": "77"}))
    ok("volta do ML (sem shop_id) não é da Shopee", not eh_callback({"code": "c", "state": "ml1.x"}))
    ok("volta do Bling não é da Shopee", not eh_callback({"code": "c", "shop_id": "1", "bling": "callback"}))
    import ml_api as _ml
    ok("e o ML não toma a volta da Shopee como dele",
       not _ml.eh_callback({"code": "c", "shop_id": "77", "state": "shp1.abc"}))
    _grav = {"shp1": {"state_pendente": "shp1.abc"}, "shp2": {"state_pendente": ""}}
    ok("state que confere diz a loja", loja_da_volta({"state": "shp1.abc"}, _grav) == ("shp1", ""))
    ok("state que não confere é recusado", loja_da_volta({"state": "shp1.zzz"}, _grav)[1] != "")
    ok("sem state, vale a única pendente", loja_da_volta({}, _grav) == ("shp1", ""))
    ok("sem state e duas pendentes, recusa em vez de adivinhar",
       loja_da_volta({}, {"shp1": {"state_pendente": "a"}, "shp2": {"state_pendente": "b"}})[0] == "")
    ok("loja já ligada com outro nome é apontada",
       loja_repetida("shp2", "77", {"shp1": {"shop_id": 77}}) == "shp1")
    _u = url_montada("2001", "shp1.abc")
    ok("o link é o fixo do Brasil, com state e redirect",
       _u.startswith(URL_AUTORIZA + "?") and "state=shp1.abc" in _u and "auth_type=seller" in _u
       and "redirect_uri=https%3A%2F%2Fapp.martinsousa.com.br" in _u)
    ok("linha mesclada preserva o token ao gravar o state",
       linha_mesclada("shp1", {"access_token": "T"}, {"state_pendente": "s"}, "agora")[1:3] == ["T", ""])

    # Janelas: sem buraco, no máximo N dias.
    _de, _ate = datetime(2026, 10, 1, tzinfo=BR), datetime(2026, 11, 12, tzinfo=BR)
    _j = janelas(_de, _ate, 15)
    ok("janelas cobrem tudo sem buraco",
       _j[0][0] == _de and _j[-1][1] == _ate and all(a[1] == b[0] for a, b in zip(_j, _j[1:])))
    ok("e nenhuma passa de 15 dias", all((f - i).days <= 15 for i, f in _j))
    ok("erro da Shopee vem com a mensagem dela",
       erro_da_resposta({"error": "error_sign", "message": "Wrong sign"}) == "Shopee: error_sign — Wrong sign")
    ok("sem erro, vazio", erro_da_resposta({"error": "", "response": {}}) == "")

    # Pedidos, na forma das páginas oficiais.
    _cred = ("2001", "chave", "tok", "77")

    def _ida_falsa(chamadas, mais_paginas=1, quebra=None):
        def ida(metodo, caminho, params, corpo=None):
            chamadas.append((caminho, params))
            if quebra and quebra in caminho:
                return (None, "Shopee: error_auth — Invalid access_token")
            if caminho.endswith("get_order_list"):
                n = sum(1 for c, _p in chamadas if c == caminho)
                ultimo = n % mais_paginas == 0
                return ({"error": "", "response": {
                    "more": not ultimo, "next_cursor": "" if ultimo else f"c{n}",
                    "order_list": [{"order_sn": f"SN{n}", "order_status": "COMPLETED"}]}}, "")
            if caminho.endswith("get_order_detail"):
                lst = params["order_sn_list"].split(",")
                return ({"error": "", "response": {"order_list": [
                    {"order_sn": s, "order_status": "CANCELLED" if s == "SN2" else "COMPLETED",
                     "create_time": 1700000000,
                     "item_list": [{"item_id": 1, "item_name": "Porta 2 Relógio + Jóias",
                                    "item_sku": "PR-2", "model_id": 0, "model_name": "",
                                    "model_sku": "", "model_quantity_purchased": 2,
                                    "model_original_price": 99.9,
                                    "model_discounted_price": 89.9}]} for s in lst]}}, "")
            if caminho.endswith("get_all_cpc_ads_daily_performance"):
                return ({"error": "", "response": [
                    {"date": params["start_date"], "expense": 10.5, "broad_gmv": 80.0,
                     "broad_order": 2, "direct_gmv": 50.0, "clicks": 30, "impression": 900}]}, "")
            if caminho.endswith("get_discount_list"):
                return ({"error": "", "response": {"more": params["page_no"] < 2, "discount_list": [
                    {"discount_id": params["page_no"], "discount_name": "Black", "status": "ongoing"}]}}, "")
            if caminho.endswith("get_voucher_list"):
                return ({"error": "", "response": {"more": False, "voucher_list": [
                    {"voucher_id": 9, "voucher_name": "CUPOM10", "reward_type": 2, "percentage": 10}]}}, "")
            return (None, "caminho inesperado")
        return ida

    _ch = []
    _ped = pedidos(_cred, _de, _ate, _ida_falsa(_ch, mais_paginas=2))
    _listas = [p for c, p in _ch if c.endswith("get_order_list")]
    ok("cada janela de 15 dias pede a lista, seguindo o cursor",
       len(_listas) == 2 * len(_j) and _listas[1]["cursor"] == "c1"
       and all(p["time_range_field"] == "create_time" and p["page_size"] == 100 for p in _listas))
    _det = [p for c, p in _ch if c.endswith("get_order_detail")]
    ok("o detalhe pede item_list, até 50 pedidos por vez, separados por vírgula",
       _det and all(p["response_optional_fields"] == "item_list"
                    and len(p["order_sn_list"].split(",")) <= 50 for p in _det))
    ok("os itens trazem o nome da plataforma e o SKU",
       _ped["itens"][0]["item_name"] == "Porta 2 Relógio + Jóias" and _ped["itens"][0]["sku"] == "PR-2"
       and not _ped["incompleto"] and _ped["pedidos"] == 2 * len(_j))
    ok("a assinatura de cada chamada é a do caminho dela",
       _listas[0]["sign"] == assinar("chave", "2001", "/api/v2/order/get_order_list",
                                     _listas[0]["timestamp"], "tok", "77"))
    _ch2 = []
    _ped2 = pedidos(_cred, _de, _ate, _ida_falsa(_ch2, quebra="get_order_detail"))
    ok("erro no detalhe: diz o erro e marca incompleto",
       "Invalid access_token" in _ped2["erro"] and _ped2["incompleto"])
    _ch3 = []
    _ped3 = pedidos(_cred, _de, _de + timedelta(days=3), _ida_falsa(_ch3, mais_paginas=10 ** 6))
    ok("lista que não acaba no teto sai INCOMPLETA", _ped3["incompleto"])

    _ponte = nomes_por_sku(_ped["itens"], {"PR-2"})
    ok("a ponte agrupa por SKU, sem os cancelados, e diz se está no estoque",
       _ponte[0]["sku"] == "PR-2" and _ponte[0]["no_estoque"] is True
       and _ponte[0]["vendidos"] == 2 * (len(_ped["itens"]) - 1)
       and _ponte[0]["nomes"] == ["Porta 2 Relógio + Jóias"])
    _sem = nomes_por_sku([{"sku": "", "item_name": "Caneca", "model_name": "Azul",
                           "qtd": 1, "status": "COMPLETED"}], set())
    ok("item sem SKU aparece com o nome, para cadastrar", _sem[0]["sku"] == ""
       and _sem[0]["nomes"] == ["Caneca · Azul"] and _sem[0]["no_estoque"] is None)

    _ch4 = []
    _ads = ads_diario(_cred, _de, _ate, _ida_falsa(_ch4))
    _pa = [p for c, p in _ch4]
    ok("ads em janelas de até 30 dias, datas DD-MM-AAAA",
       _pa[0]["start_date"] == "01-10-2026" and len(_pa) == 2
       and all(datetime.strptime(p["end_date"], "%d-%m-%Y") - datetime.strptime(p["start_date"], "%d-%m-%Y")
               <= timedelta(days=30) for p in _pa))
    ok("ads devolve gasto e venda por dia", _ads["dias"][0]["expense"] == 10.5 and not _ads["erro"])
    _pr = promocoes(_cred, ida=_ida_falsa([]))
    ok("descontos seguem as páginas até more=false",
       [d["discount_id"] for d in _pr["descontos"]["lista"]] == [1, 2])
    ok("cupons vêm da lista de vouchers", _pr["cupons"]["lista"][0]["voucher_name"] == "CUPOM10")

    _sem_fim = lambda m, c, p, corpo=None: ({"error": "", "response": {"more": True, "discount_list": [1]}}, "")
    _r = _lista_paginada(_cred, "/api/v2/discount/get_discount_list", "discount_list", {}, _sem_fim)
    ok("lista que não acaba para em MAX_PAGINAS e diz INCOMPLETO",
       _r["incompleto"] and len(_r["lista"]) == MAX_PAGINAS)

    # Lojas e nomes: os mesmos canais do Bling (bling_api.py:19-20).
    ok("toda loja tem nome, e são a Shopee 1 e a Shopee 2",
       set(NOME_DA_LOJA) == set(LOJAS) and NOME_DA_LOJA["shp1"].startswith("Shopee 1")
       and NOME_DA_LOJA["shp2"].startswith("Shopee 2"))
    ok("a aba dos tokens é a da Shopee, não a do ML", ABA == "shopee_tokens" and callable(_aba))

    # Sem credencial: cada porta diz a mesma frase, e nenhuma vai à rede.
    import os
    _env = {k: os.environ.pop(k, None) for k in ("SHOPEE_PARTNER_ID", "SHOPEE_PARTNER_KEY")}
    try:
        ok("sem credencial, o link diz o que falta", url_de_autorizacao("shp1") == ("", FALTA_CREDENCIAL))
        ok("e o token também", token("shp1") == ("", "", FALTA_CREDENCIAL))
        ok("e a credencial da loja também", credencial_da_loja("shp2") == (None, FALTA_CREDENCIAL))
        os.environ.update(SHOPEE_PARTNER_ID="2001", SHOPEE_PARTNER_KEY="k")
        _tk = token
        token = lambda l: ("tok", "77", "")
        ok("com token, a credencial vai inteira para a thread",
           credencial_da_loja("shp1") == (("2001", "k", "tok", "77"), ""))
        token = _tk
    finally:
        for k, v in _env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # A cadeia real: requests.request trocado, _ida de verdade.
    _rq = requests.request

    class _R:
        status_code, ok = 200, True

        def json(self):
            return {"error": "", "message": "", "response": {"more": False, "discount_list": []}}

    _vistos = []
    requests.request = lambda m, url, **kw: (_vistos.append((m, url, kw)), _R())[1]
    try:
        _r = _lista_paginada(_cred, "/api/v2/discount/get_discount_list", "discount_list",
                             {"discount_status": "ongoing"})
    finally:
        requests.request = _rq
    ok("a cadeia real vai ao host do Brasil com a assinatura na URL",
       _vistos[0][1] == HOST + "/api/v2/discount/get_discount_list"
       and "sign" in _vistos[0][2]["params"] and not _r["erro"])

    class _RErr(_R):
        def json(self):
            return {"error": "error_sign", "message": "Wrong sign", "request_id": "x"}
    requests.request = lambda m, url, **kw: _RErr()
    try:
        ok("erro da Shopee com HTTP 200 não passa como sucesso",
           _ida("GET", "/x", {})[1] == "Shopee: error_sign — Wrong sign")
    finally:
        requests.request = _rq

    print("\nfalhas:", falhas)
    raise SystemExit(1 if falhas else 0)
