"""extrato_inter_api.py — o extrato do Inter direto do banco, sem exportar CSV.

Dono, 09/10: "o ideal é que ele conseguisse pegar os extratos (...) e já
atualizasse os gastos do sistema". As integrações foram criadas no internet
banking do Inter (Integrar › Nova Integração, só "Consultar extrato e saldo")
e as credenciais estão nas variáveis do Railway — nunca no código:

    INTER_CLIENT_ID / INTER_CLIENT_SECRET / INTER_CERT / INTER_KEY     (LG)
    INTER2_CLIENT_ID / INTER2_CLIENT_SECRET / INTER2_CERT / INTER2_KEY (MS)
    INTER2_CONTA — opcional: o número da conta MS, se não for o padrão de
                   `CONTAS`. O nome da conta tem de casar com o do CSV
                   ("inter-<número>", `extratos_tela._processar`)

A API (conferida em 09/10, referência do Inter + projetos que a usam):
  token   POST /oauth/v2/token, client_credentials, escopo extrato.read,
          com certificado e chave (mTLS). Vale 60 min; o endpoint aceita 5
          chamadas por minuto — um token por busca, no clique, fica dentro.
  extrato GET /banking/v2/extrato?dataInicio=AAAA-MM-DD&dataFim=AAAA-MM-DD,
          no máximo 90 dias por consulta, 10 consultas por minuto.
          Resposta: {"transacoes": [{dataEntrada, tipoTransacao,
          tipoOperacao (C/D), valor (texto), titulo, descricao}]}.

O FORMATO DA RESPOSTA VEIO DE FONTE DE TERCEIROS — a documentação oficial
exige login. Por isso a primeira versão MOSTRA antes de gravar
(`extratos_tela._buscar_inter`), e `ler` aceita as variações que o texto
pode ter (valor com vírgula, data com hora, sinal no valor ou no C/D).

NÃO DUPLICA O QUE O CSV JÁ GRAVOU. A identidade de `lancamentos` usa o texto
da descrição, e o texto da API pode não ser o do CSV. `novos` casa por conta,
data e valor contra o que está gravado, um a um.
"""
import os
import tempfile

BASE = "https://cdpj.partners.bancointer.com.br"
ESCOPO = "extrato.read"
MAX_DIAS = 90

# (rótulo, prefixo das variáveis, conta padrão). A LG é a 116183837 — o número
# no topo do internet banking, o mesmo que o CSV traz em "Conta ;116183837".
# A MS é a 16751391-5 (dono, 09/10), sem o traço como o CSV escreve.
CONTAS = (("LG", "INTER", "116183837"),
          ("MS", "INTER2", "167513915"))

def configuradas(ambiente=None):
    """[(rótulo, prefixo, nome da conta)] das contas com as 4 credenciais."""
    env = os.environ if ambiente is None else ambiente
    fora = []
    for rotulo, pref, padrao in CONTAS:
        if all(str(env.get(f"{pref}_{c}") or "").strip()
               for c in ("CLIENT_ID", "CLIENT_SECRET", "CERT", "KEY")):
            numero = str(env.get(f"{pref}_CONTA") or padrao).strip()
            fora.append((rotulo, pref, f"inter-{numero}" if numero else ""))
    return fora


def _num(v):
    """'-1.303,00' / '1303.00' / 1303 -> float. None quando não é número."""
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v or "").strip().replace("R$", "").replace(" ", "")
    if not t:
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def ler(resposta):
    """Os lançamentos no formato de `extrato_inter.ler`. Pura.

    [{"data", "descricao", "favorecido", "valor", "sentido"}], valor negativo
    é saída. D (débito) sai, C (crédito) entra; se o valor já vier com sinal,
    o sinal do C/D manda.
    """
    from datetime import datetime
    import extrato_inter as _ei
    fora = []
    for t in (resposta or {}).get("transacoes") or []:
        v = _num(t.get("valor"))
        d = str(t.get("dataEntrada") or t.get("dataLancamento") or "")[:10]
        try:
            data = datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            continue
        if v is None:
            continue
        op = str(t.get("tipoOperacao") or "").strip().upper()
        v = -abs(v) if op == "D" else (abs(v) if op == "C" else v)
        titulo = str(t.get("titulo") or "").strip()
        desc = str(t.get("descricao") or "").strip()
        texto = desc if (not titulo or titulo.lower() in desc.lower()) else (
            f"{titulo}: {desc}" if desc else titulo)
        fora.append({"data": data, "descricao": texto,
                     "favorecido": _ei.favorecido(texto), "valor": round(v, 2),
                     "sentido": "saida" if v < 0 else "entrada"})
    return fora


def novos(da_api, gravados, conta):
    """Os da API que ainda não estão gravados nesta conta. Pura.

    Casa por (data, valor), um para um: dois PIX de R$ 50 no mesmo dia são
    dois, e o terceiro que a API trouxer é novo.
    """
    import lancamentos as _lan
    sobra = {}
    for g in (gravados or []):
        if str(g.get("conta") or "") != conta:
            continue
        k = (_lan._txt_data(g.get("data")), f"{float(g.get('valor') or 0):.2f}")
        sobra[k] = sobra.get(k, 0) + 1
    fora = []
    for l in (da_api or []):
        k = (_lan._txt_data(l.get("data")), f"{float(l.get('valor') or 0):.2f}")
        if sobra.get(k):
            sobra[k] -= 1
            continue
        fora.append(l)
    return fora


def ja_trazidos(do_csv, gravados, conta):
    """Ids das linhas do CSV que a API já gravou com outro texto. Pura.

    O contrário de `novos`: subir o CSV de um período que a API já trouxe
    gravaria tudo de novo, porque a identidade usa o texto e o texto da API
    não é o do CSV. Vai em `lancamentos.gravar(pular=...)`. As que já estão
    gravadas com a MESMA identidade ficam de fora — `gravar` as conta como
    repetidas sozinho.
    """
    import lancamentos as _lan
    itens = _lan.com_identidade(do_csv, conta)
    ja = {str(g.get("id") or "") for g in (gravados or [])}
    restam = novos(itens, gravados, conta)
    fica = {id(x) for x in restam}
    return {it["id"] for it in itens
            if id(it) not in fica and it["id"] not in ja}


def periodos(inicio, fim, max_dias=MAX_DIAS):
    """[(início, fim)] em fatias de até `max_dias` — o limite da API."""
    from datetime import timedelta
    fora, a = [], inicio
    while a <= fim:
        b = min(a + timedelta(days=max_dias - 1), fim)
        fora.append((a, b))
        a = b + timedelta(days=1)
    return fora


# ── Rede ────────────────────────────────────────────────────────────────────

def _arquivos(pref):
    """(crt, key) em arquivos temporários só do processo, lidos do ambiente.

    O `requests` pede caminho de arquivo para o mTLS. O conteúdo fica com
    permissão 600 e é apagado quando o processo termina.
    """
    caminhos = []
    for c in ("CERT", "KEY"):
        conteudo = os.environ[f"{pref}_{c}"].replace("\\n", "\n").strip() + "\n"
        f = tempfile.NamedTemporaryFile("w", suffix=f".{c.lower()}",
                                        delete=False)
        os.chmod(f.name, 0o600)
        f.write(conteudo)
        f.close()
        caminhos.append(f.name)
    return tuple(caminhos)


def _token(pref):
    """Um token novo a cada busca. NÃO fica guardado no módulo: no Streamlit
    o módulo é de todo o processo, e a busca só acontece no clique — um token
    por clique fica bem dentro das 5 chamadas por minuto do endpoint."""
    import requests
    crt, key = _arquivos(pref)
    try:
        r = requests.post(f"{BASE}/oauth/v2/token", cert=(crt, key), timeout=30,
                          data={"client_id": os.environ[f"{pref}_CLIENT_ID"],
                                "client_secret": os.environ[f"{pref}_CLIENT_SECRET"],
                                "grant_type": "client_credentials",
                                "scope": ESCOPO})
    finally:
        for p in (crt, key):
            try:
                os.remove(p)
            except OSError:
                pass
    if r.status_code != 200:
        raise RuntimeError(f"token recusado ({r.status_code})")
    j = r.json()
    # O Inter às vezes emite token SEM o escopo pedido (escopo não habilitado
    # na integração) e responde 200 assim mesmo.
    if ESCOPO not in str(j.get("scope", ESCOPO)).split():
        raise RuntimeError("a integração não tem a permissão de extrato")
    return j["access_token"]


def buscar(pref, inicio, fim):
    """(lançamentos, erro) do período, já no formato de `ler`."""
    import requests
    try:
        tok = _token(pref)
        crt, key = _arquivos(pref)
        fora = []
        try:
            for a, b in periodos(inicio, fim):
                r = requests.get(f"{BASE}/banking/v2/extrato", cert=(crt, key),
                                 timeout=60,
                                 headers={"Authorization": f"Bearer {tok}"},
                                 params={"dataInicio": a.isoformat(),
                                         "dataFim": b.isoformat()})
                if r.status_code != 200:
                    return [], f"o Inter respondeu {r.status_code} ao extrato"
                fora += ler(r.json())
        finally:
            for p in (crt, key):
                try:
                    os.remove(p)
                except OSError:
                    pass
        return fora, ""
    except Exception as e:
        # Só o tipo e a mensagem curta: nunca o corpo, que pode ecoar credencial.
        return [], f"{type(e).__name__}: {str(e)[:120]}"


# ── Conferência ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    from datetime import date
    falhas = 0

    def ok(nome, cond):
        global falhas
        falhas += not cond
        print(("ok    " if cond else "FALHA ") + nome)

    _env = {"INTER_CLIENT_ID": "x", "INTER_CLIENT_SECRET": "y",
            "INTER_CERT": "c", "INTER_KEY": "k",
            "INTER2_CLIENT_ID": "x", "INTER2_CLIENT_SECRET": "y",
            "INTER2_CERT": "c", "INTER2_KEY": "k", "INTER2_CONTA": "999"}
    ok("as duas contas com as 4 credenciais aparecem, com o nome do CSV",
       configuradas(_env) == [("LG", "INTER", "inter-116183837"),
                              ("MS", "INTER2", "inter-999")])
    ok("conta sem alguma credencial não aparece",
       configuradas({"INTER_CLIENT_ID": "x"}) == [])
    ok("MS sem número na variável usa o da conta: 16751391-5, sem traço",
       configuradas({**_env, "INTER2_CONTA": ""})[1][2] == "inter-167513915")

    # A resposta na forma descrita para /banking/v2/extrato.
    _resp = {"transacoes": [
        {"dataEntrada": "2026-10-08", "tipoTransacao": "PIX",
         "tipoOperacao": "D", "valor": "1303.00", "titulo": "Pix enviado",
         "descricao": 'Pix enviado: "Cp :60701190-APEXIMP"'},
        {"dataEntrada": "2026-10-08", "tipoTransacao": "PIX",
         "tipoOperacao": "C", "valor": "250,50", "titulo": "Pix recebido",
         "descricao": "MERCADO LIVRE"},
        {"dataEntrada": "lixo", "tipoOperacao": "D", "valor": "1"},
    ]}
    _l = ler(_resp)
    ok("débito sai negativo, crédito entra positivo, com vírgula ou ponto",
       [x["valor"] for x in _l] == [-1303.0, 250.5])
    ok("o favorecido sai pela mesma regra do CSV",
       _l[0]["favorecido"] == "APEXIMP")
    ok("título que já está na descrição não se repete",
       _l[0]["descricao"] == 'Pix enviado: "Cp :60701190-APEXIMP"'
       and _l[1]["descricao"] == "Pix recebido: MERCADO LIVRE")
    ok("linha sem data válida é ignorada", len(_l) == 2)

    # Os gravados na forma de `lancamentos.carregar` (o CSV já subido).
    _grav = [{"conta": "inter-116183837", "data": "2026-10-08",
              "valor": -1303.0, "descricao": "texto do CSV"},
             {"conta": "itau-1", "data": "2026-10-08", "valor": 250.5}]
    _n = novos(_l, _grav, "inter-116183837")
    ok("o que o CSV já gravou não volta — casa por data e valor",
       [x["valor"] for x in _n] == [250.5])
    ok("dois iguais no mesmo dia: o segundo da API é novo",
       len(novos(_l[:1] * 2, _grav, "inter-116183837")) == 1)

    # O CSV subido DEPOIS da API: a linha que a API já gravou (outro texto)
    # vai para `pular`; a nova, não.
    _csv = [{"data": date(2026, 10, 8), "valor": 250.5,
             "descricao": 'Pix recebido: "MERCADO LIVRE"'},
            {"data": date(2026, 10, 9), "valor": -40.0, "descricao": "nova"}]
    import lancamentos as _lan_t
    _api_grav = [dict(x, conta="inter-116183837",
                      id=_lan_t.identidade(x, "inter-116183837"))
                 for x in _l]
    _pj = ja_trazidos(_csv, _api_grav, "inter-116183837")
    _ids_csv = [i["id"] for i in _lan_t.com_identidade(_csv, "inter-116183837")]
    ok("o CSV não grava de novo o que a API já trouxe com outro texto",
       _pj == {_ids_csv[0]})
    ok("e o que já está gravado com a mesma identidade fica para o gravar",
       ja_trazidos(_csv, [dict(c, id=i, conta="inter-116183837")
                          for c, i in zip(_csv, _ids_csv)],
                   "inter-116183837") == set())

    _p = periodos(date(2026, 1, 1), date(2026, 6, 30))
    ok("o período é fatiado em até 90 dias",
       _p[0] == (date(2026, 1, 1), date(2026, 3, 31))
       and _p[-1][1] == date(2026, 6, 30)
       and all((b - a).days < 90 for a, b in _p))

    print("\nfalhas:", falhas)
    sys.exit(1 if falhas else 0)
