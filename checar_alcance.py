"""checar_alcance.py — o sexto verificador: a correção chegou em TODO lugar?

POR QUE ELE EXISTE
------------------
Dono, 28/09: *"só de retrabalho gerado por erros seus é infinitamente superior
a qualquer outra coisa"*. Varrendo a conversa, o retrabalho tem uma forma só,
e ela se repete:

    eu corrijo NO LUGAR ONDE O PROBLEMA APARECEU,
    e não em todos os lugares onde a mesma regra alcança.

Já aconteceu, nesta base, com nome e data:

- `additionalProperties` foi escrito em `imagem.py` e faltou em
  `ambientacao_ref.py`. A tela deu erro 400 — e a linha certa já existia no
  repositório, a três arquivos de distância.
- A paleta azul voltou TRÊS vezes; o "ZERO TEXTO" sobreviveu num preset.
  Nos dois casos procurei pelo TEXTO do sintoma, não pelo ALCANCE da regra.
- O cartão de texto tinha quatro vozes — a regra compartilhada e três presets.
- `pergunta_info` ganhou um segundo dono e as peças 7 e 8 sumiram.

OS QUATRO VERIFICADORES ANTERIORES NÃO PEGAM ISSO. Eles conferem sintaxe,
ordem de nomes, o prompt da IMAGEM, quem lê o que mudou, e se a tela monta.
Nenhum pergunta: *"esta capacidade existe em um lugar e falta no irmão dele?"*

O QUE ELE CONFERE
-----------------
1. Todo campo que recebe IMAGEM aceita todo formato. O sistema tem
   `normalizar_imagem`, que converte HEIC, AVIF, GIF, BMP e TIFF. Um campo
   que lista extensões rejeita o arquivo ANTES de o conversor existir — e o
   colaborador que fotografou no iPhone não tem como saber por quê.
2. Todo caminho que manda imagem ao motor passa pelo conversor.
3. O rótulo não mente sobre o que aceita.
4. O prompt do PLANO é varrido. Ele decide quais peças são viáveis e qual
   ângulo usar, e nenhuma varredura o lia: 60 regras verdes mediam o prompt
   da IMAGEM enquanto o defeito estava no do plano.

ELE NÃO JULGA QUALIDADE. Só pergunta se a mesma capacidade está nos irmãos.
"""

import ast
import os
import re
import sys

# Os campos de upload que recebem IMAGEM. O nome do rótulo é o que identifica:
# extrato, fatura e planilha têm razão para restringir formato — imagem não.
_PALAVRAS_DE_IMAGEM = ("imagem", "imagens", "foto", "fotos", "referência",
                       "referencia", "referências", "referencias", "quadro",
                       "anexar imagem", "print")

# Extensões de imagem. Um `type=[...]` só com estas é uma porta que o
# conversor já sabia abrir.
_EXT_IMAGEM = {"png", "jpg", "jpeg", "webp", "heic", "heif", "avif", "gif",
               "bmp", "tif", "tiff"}

# Rótulo que promete menos do que o campo aceita. Quem lê "(JPG, PNG, WebP)"
# com um HEIC na mão não tenta — e o campo teria aceitado.
_ROTULO_QUE_MENTE = re.compile(r"\((?:[A-Za-z]{3,4}\s*,\s*)+[A-Za-z]{3,4}\)")


# Este arquivo FALA de marcador de conflito para saber achá-lo — procurar o
# texto nele mesmo seria a sexta vez nesta base que uma guarda se encontra.
IGNORAR_CONFLITO = {"checar_alcance.py"}


# Onde o `datetime.now()` cru continua CERTO, e por quê. Comparação de UTC
# com UTC não tem erro de fuso: trocar um lado só é que teria.
#
# `varredura_formas.py` lê esta lista daqui. Duas listas discordam, e a
# questão é só quando — a varredura mostrava como "achado" o que este
# portão já tinha decidido que está certo, e relatório com ruído ninguém
# lê até o fim.
# ISENTA-SE A FUNÇÃO, NUNCA O ARQUIVO.
#
# Esta lista era por arquivo, com UMA exceção escrita à mão para o
# `placar_core.py` — a correção no lugar onde o sintoma apareceu, e os outros
# cinco continuavam isentos inteiros.
#
# O estrago que originou a exceção: isentei `placar_core` "porque é onde
# `agora_br` mora", e isso escondeu `ritmo_do_mes`, que calcula mês e dia — o
# velocímetro da Meta Mensal perdia a cor no fim do mês.
#
# E o mesmo desenho estava vivo aqui: a isenção do `auth.py` dizia
# "expiração de token contra token gravado", que descreve UMA função, e o
# arquivo tem outra que escreve hora legível na planilha. Hoje os dois lados
# são UTC e não há erro; amanhã um terceiro uso entrava sem ninguém ver.
#
# A chave é "arquivo.py:funcao". Uso fora das funções nomeadas reprova, mesmo
# em arquivo que já tem isenção.
CONSISTENTES_UTC = {
    "checar_tela.py:_contexto_do_log": "é a guarda que PROCURA `datetime.now()` no registro",
    "auth.py:_garantir_tokens_carregados": "compara a expiração com o `criado_em` gravado, os dois em UTC",
    "auth.py:_salvar_token_sheets": "grava o `criado_em` que aquela comparação lê; trocar um lado só é que criaria o erro",
    "rhid_api.py:_token_valido": "compara com `rhid_token_exp`, que foi gravado pelo mesmo relógio",
    "gargalos_tela.py:_dentro_do_periodo": "idade do cartão contra a ação do Trello, ambos UTC",
    "fechar_expediente.py:_log": "é o fallback do except; o caminho normal usa FUSO, logo acima",
    "varredura_formas.py:main": "é a varredura que PROCURA este padrão",
}



def _arquivos(raiz="."):
    for nome in sorted(os.listdir(raiz)):
        if nome.endswith(".py") and not nome.startswith("checar_"):
            yield nome


def _texto_do_no(no):
    """O literal de um nó, quando ele é um. '' quando não dá para saber."""
    if isinstance(no, ast.Constant) and isinstance(no.value, str):
        return no.value
    if isinstance(no, ast.JoinedStr):
        return "".join(p.value for p in no.values
                       if isinstance(p, ast.Constant) and isinstance(p.value, str))
    return ""


def uploads_de_imagem(fonte, arquivo=""):
    """Todo `file_uploader` cujo rótulo fala de imagem.

    Devolve [{arquivo, linha, rotulo, tipos, restringe, rotulo_mente}].
    `tipos` é None quando o campo aceita qualquer coisa — que é o certo.
    """
    try:
        arvore = ast.parse(fonte)
    except SyntaxError:
        return []
    achados = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        alvo = getattr(no.func, "attr", "")
        if alvo != "file_uploader":
            continue
        rotulo = _texto_do_no(no.args[0]) if no.args else ""
        if not any(p in rotulo.lower() for p in _PALAVRAS_DE_IMAGEM):
            continue
        tipos = None
        for kw in no.keywords:
            if kw.arg != "type":
                continue
            if isinstance(kw.value, ast.List):
                tipos = [_texto_do_no(e).lower() for e in kw.value.elts]
        restringe = bool(tipos) and set(tipos) <= _EXT_IMAGEM
        achados.append({
            "arquivo": arquivo, "linha": no.lineno, "rotulo": rotulo,
            "tipos": tipos, "restringe": restringe,
            "rotulo_mente": bool(tipos is None
                                 and _ROTULO_QUE_MENTE.search(rotulo)),
        })
    return achados


def _conferir_isentos():
    """A lista de isentos tem de ser HONESTA, e `varredura_formas` a lê daqui.

    Isentar é dizer "aqui o `datetime.now()` cru está certo", e uma isenção
    larga demais esconde defeito: eu tinha isentado o ARQUIVO `placar_core`
    inteiro "porque é onde `agora_br` mora", e isso escondeu `ritmo_do_mes`,
    que calcula mês e dia — o velocímetro da Meta Mensal perdia a cor no fim
    do mês.
    """
    fora = []
    for chave, motivo in CONSISTENTES_UTC.items():
        if ":" not in chave:
            fora.append(f"{chave} está isento por ARQUIVO — a isenção é da "
                        "FUNÇÃO, senão um segundo uso se esconde atrás do "
                        "primeiro (foi o que aconteceu com `ritmo_do_mes`)")
            continue
        nome, funcao = chave.split(":", 1)
        if not os.path.exists(nome):
            fora.append(f"{nome} está na lista de isentos e não existe mais")
        elif f"def {funcao}(" not in open(nome, encoding="utf-8").read():
            fora.append(f"{chave}: a função isenta não existe mais em {nome} "
                        "— isenção órfã dá impressão de cobertura")
        if not motivo or len(motivo) < 15:
            fora.append(f"{chave} está isento sem motivo escrito")
    # A exceção escrita à mão para o `placar_core.py` saiu: agora TODA isenção
    # é por função, e a regra que ela representava virou a checagem acima.
    return fora


# Nomes que EXISTEM nos dois arquivos de placar e podem continuar assim: sao
# copias que dao a MESMA resposta, conferidas uma a uma por teste diferencial
# em 28/09. Ficam aqui nomeadas para que a lista nao cresca em silencio.
GEMEAS_TOLERADAS = {
    "_req_get": "identicas, byte a byte",
    "_mes_card_criacao": "identicas, byte a byte",
    "_fmt_tempo": "mesma resposta em 12 entradas",
    "_labels": "mesma resposta em 4 entradas",
    "_users": "mesma resposta em 5 entradas",
    "_num": "mesma resposta em 7 entradas",
    "_data_card": "mesma resposta; difere so no `now()` de fallback",
    "_buscar_board": "o do placar e um envelope do core",
    "_calcular_fila": "contas diferentes, cada tela le a sua",
    "_processar": "o do core faz 3 consultas a mais ao Trello",
}


def _gemeas_do_placar():
    """Funcao de topo com o mesmo nome em `placar.py` e `placar_core.py`.

    A Forma 5 do CLAUDE.md: `_processar` ja discordou em 330 PONTOS no mesmo
    mes e na mesma sessao. A lista das gemeas nao pode CRESCER sem alguem
    olhar, e uma delas nunca pode ficar MORTA — funcao sem chamador, com o
    nome de outra que existe ao lado e faz a conta certa, e uma armadilha
    esperando o proximo a chamar sem saber qual das duas pegou.

    `placar._mes_card` era exatamente isso: zero chamadores, e por baixo a
    conta que causou os 330 pontos, com o proprio docstring dizendo
    "OBSOLETA — nao use".
    """
    fora = []
    try:
        with open("placar.py", encoding="utf-8") as fh:
            src_a = fh.read()
        with open("placar_core.py", encoding="utf-8") as fh:
            src_b = fh.read()
    except OSError:
        return fora
    try:
        arv_a, arv_b = ast.parse(src_a), ast.parse(src_b)
    except SyntaxError:
        return fora
    topo_a = {n.name: n for n in arv_a.body if isinstance(n, ast.FunctionDef)}
    topo_b = {n.name for n in arv_b.body if isinstance(n, ast.FunctionDef)}
    gemeas = sorted(set(topo_a) & topo_b)

    # Chamadas LOCAIS, sem prefixo de modulo: sao as que pegam a copia daqui.
    chamadas = {}
    for no in ast.walk(arv_a):
        if isinstance(no, ast.Call):
            nome = getattr(no.func, "id", None)
            if nome:
                chamadas[nome] = chamadas.get(nome, 0) + 1

    for g in gemeas:
        if g not in GEMEAS_TOLERADAS:
            fora.append(
                f"placar.py:{topo_a[g].lineno} — `{g}` passou a existir nos "
                f"DOIS arquivos de placar e nao esta em GEMEAS_TOLERADAS. "
                f"Duas respostas para a mesma pergunta discordam, e a questao "
                f"e so quando: `_processar` ja custou 330 pontos.")
        elif chamadas.get(g, 0) == 0:
            fora.append(
                f"placar.py:{topo_a[g].lineno} — `{g}` nao tem chamador "
                f"nenhum em placar.py e existe igual no core. Copia morta com "
                f"o nome da viva e armadilha: apague, ou diga por que fica.")
    # E a lista nao pode guardar nome que ja sumiu dos dois.
    for g in GEMEAS_TOLERADAS:
        if g not in gemeas:
            fora.append(f"`{g}` esta em GEMEAS_TOLERADAS e ja nao e gemea — "
                        f"tire da lista para ela nao virar decoracao")
    return fora


def main():
    falhas = []

    def reprova(msg):
        falhas.append(msg)
        print("FALHA  " + msg)

    # ── 1 e 3. OS CAMPOS DE IMAGEM ──────────────────────────────────────────
    total = 0
    for nome in _arquivos():
        with open(nome, encoding="utf-8") as fh:
            achados = uploads_de_imagem(fh.read(), nome)
        for a in achados:
            total += 1
            if a["restringe"]:
                reprova(
                    f"{a['arquivo']}:{a['linha']} — o campo {a['rotulo']!r} só "
                    f"aceita {a['tipos']}, mas o sistema tem "
                    f"`normalizar_imagem`, que converte HEIC, AVIF, GIF, BMP e "
                    f"TIFF. Use type=None: quem fotografa no iPhone manda HEIC "
                    f"e este campo recusa antes de o conversor existir.")
            if a["rotulo_mente"]:
                reprova(
                    f"{a['arquivo']}:{a['linha']} — o rótulo {a['rotulo']!r} "
                    f"promete menos do que o campo aceita (ele aceita "
                    f"qualquer formato). Quem lê a lista com um HEIC na mão "
                    f"não tenta.")
    print(f"ok    {total} campo(s) de imagem varrido(s)")

    # ── 1-bis. TODA CHAMADA AO MOTOR LEVA O TIPO E AS REFERENCIAS ──────────
    #
    # ACHADO EM PRODUCAO, 05/10, e e a Forma 1 na forma mais cara: a
    # capacidade existia em UM caminho e faltava nos outros tres.
    #
    # O laco que gera as oito pecas chamava `_gerar_imagem_thread` com
    # `tipo`, `refs_layout` e `refs_layout_nomes`. O refazer pelo chat, a
    # conferencia dele, o botao "Regenerar esta imagem" e a conferencia DELE
    # passavam so tres argumentos posicionais — e nenhum dos tres chegava.
    #
    # DOIS ESTRAGOS, os dois medidos no teste do dono:
    #   1. sem `refs_layout`, `ref_layout_do_tipo` nao casa nada e a peca
    #      refeita vem SEM o padrao aprovado da empresa. A peca 6 voltou com
    #      os cartoes nos quatro cantos em vez da coluna unica — o defeito
    #      que o dono ja tinha mandado corrigir uma vez.
    #   2. sem `tipo`, `numero_do_tipo("")` devolve "" e o registro sai como
    #      "peca ?", com `tipo:` vazio. O historico perde de qual peca a
    #      geracao era.
    #
    # A guarda e por AST e estrutural: ela nao sabe o que e certo, sabe que
    # os irmaos tem de receber o mesmo.
    import ast as _ast_mot
    _vistas = {}
    for _nome in _arquivos():
        try:
            _arv = _ast_mot.parse(open(_nome, encoding="utf-8").read())
        except SyntaxError:
            continue
        for _no in _ast_mot.walk(_arv):
            if not isinstance(_no, _ast_mot.Call):
                continue
            _d = _ast_mot.dump(_no.func)
            if "Thread" not in _d:
                continue
            _inteiro = _ast_mot.dump(_no)
            if "_gerar_imagem_thread" not in _inteiro:
                continue
            # `Thread(kwargs={...})` — o que chega a funcao-alvo esta DENTRO
            # do dicionario, e nao e keyword do Thread. A primeira versao
            # desta guarda olhava `_no.keywords` e reprovou as quatro
            # chamadas CERTAS: alarme falso em cima de codigo corrigido, que
            # e o jeito mais rapido de ensinar alguem a ignorar verificador.
            _chaves = set()
            for _k in _no.keywords:
                if _k.arg == "kwargs" and isinstance(_k.value, _ast_mot.Dict):
                    _chaves |= {_c.value for _c in _k.value.keys
                                if isinstance(_c, _ast_mot.Constant)}
                elif _k.arg:
                    _chaves.add(_k.arg)
            _faltam = [c for c in ("tipo", "refs_layout", "refs_layout_nomes")
                       if c not in _chaves]
            _vistas[(_nome, _no.lineno)] = _faltam
    print(f"ok    {len(_vistas)} chamada(s) ao motor de imagem varrida(s)")
    for (_nome, _lin), _faltam in sorted(_vistas.items()):
        if _faltam:
            reprova(
                f"{_nome}:{_lin} — a thread do motor de imagem nao recebe "
                f"{', '.join(_faltam)}. Sem `tipo` o registro sai como "
                f"'peca ?' e a regra do tipo nao casa; sem `refs_layout` a "
                f"peca e gerada IGNORANDO o padrao aprovado da empresa. O "
                f"laco da geracao passa os tres — este caminho e irmao dele.")
    if not _vistas:
        reprova("nenhuma chamada ao motor de imagem foi encontrada — a "
                "guarda ficou cega, e guarda cega e pior que nenhuma")

    # ── 2. O CONVERSOR NO CAMINHO ───────────────────────────────────────────
    #
    # Quem recebe imagem e manda para um modelo tem de passar por
    # `normalizar_imagem`. O chat mandava os bytes crus.
    # SÓ QUEM MANDA A IMAGEM A UM MODELO. Subir a foto para o Drive aceita
    # qualquer formato — exigir o conversor ali seria alarme falso, e
    # verificador que grita à toa ensina a ser ignorado. Foi o que aconteceu
    # com a primeira versão de `checar_tela.py`, que acusou o inocente.
    _SINAIS_DE_MODELO = ("anthropic.Anthropic", "messages.create",
                         "chat.completions", "images.generate",
                         "generate_content", "_chamar_ia")
    def _nomes_de_alvo(no):
        """Todo nome de funcao que pode acabar rodando como alvo da thread.

        O ALVO PODE VIR EMBRULHADO, E O EMBRULHO CEGAVA ESTA REGRA.
        `target=_gerar_imagem_thread` era lido com um `.split(".")[-1]`, que
        so enxerga um nome cru. Quando o alvo passou a ser
        `target=_li_thread.alvo_com_contexto(_gerar_imagem_thread)` — para a
        thread herdar o contexto do log —, o que sobrava era
        "alvo_com_contexto(_gerar_imagem_thread)", que nao e funcao nenhuma
        deste arquivo: as NOVE threads da tela de imagem sumiram do alcance
        de uma vez, e a regra ficou verde sem medir nada.

        Foi `checar_mutacao` que pegou, e e exatamente para isso que ele
        existe: a mutacao 'o aviso do motor reserva volta para dentro da
        thread' ficou VERDE com o defeito de volta.

        Entao o alvo se le por dentro: o nome, e tambem os argumentos quando
        ele e uma chamada — que e onde a funcao de verdade viaja.
        """
        fora = set()
        if isinstance(no, ast.Call):
            for arg in list(no.args) + [k.value for k in no.keywords]:
                fora |= _nomes_de_alvo(arg)
            fora |= _nomes_de_alvo(no.func)
            return fora
        if isinstance(no, (ast.Name, ast.Attribute)):
            fora.add(ast.unparse(no).split(".")[-1])
        return fora

    for nome in _arquivos():
        with open(nome, encoding="utf-8") as fh:
            fonte = fh.read()
        if not uploads_de_imagem(fonte, nome):
            continue
        if not any(sinal in fonte for sinal in _SINAIS_DE_MODELO):
            continue
        if "normalizar_imagem" not in fonte:
            reprova(
                f"{nome} recebe imagem por upload, manda para um modelo e "
                f"nunca chama `normalizar_imagem`. O arquivo cru vai ao "
                f"motor, e formato que ele não aceita vira erro genérico de "
                f"geração — sem dizer ao colaborador qual é o problema.")

    # ── 5. `session_state` LIDO DE DENTRO DE UMA THREAD ────────────────────
    #
    # Forma 6 do CLAUDE.md, e a que gerou o retrabalho de 28/09.
    #
    # `st.session_state` e ILEGIVEL dentro de `threading.Thread`. Eu sabia
    # disso, apliquei ao numero da peca (`_PECA_EM_AJUSTE`) e escrevi ate uma
    # guarda com Thread de verdade para provar. E deixei `produto` e `usuario`
    # lendo do session_state NO MESMO append_row, duas linhas ao lado.
    #
    # Resultado: toda linha do log gravou produto vazio, o filtro por nome
    # nunca bateu, e o historico de prompts voltava sempre vazio — em
    # silencio, porque `registrar` engole a propria excecao de proposito.
    #
    # Esta varredura acha o padrao: funcao que grava registro e le
    # `session_state` no corpo. Ela nao adivinha a pilha de chamadas; olha
    # quem ESCREVE e quem LE, que e onde o dano mora.
    _GRAVAM_REGISTRO = ("log_imagem.py", "atividades.py")
    for nome in _arquivos():
        if nome not in _GRAVAM_REGISTRO:
            continue
        with open(nome, encoding="utf-8") as fh:
            fonte = fh.read()
        try:
            arvore = ast.parse(fonte)
        except SyntaxError:
            continue
        for no in ast.walk(arvore):
            if not isinstance(no, ast.FunctionDef):
                continue
            trecho = ast.get_source_segment(fonte, no) or ""
            if "append_row" not in trecho:
                continue
            if "session_state" in trecho:
                reprova(
                    f"{nome}:{no.lineno} — `{no.name}` grava registro E lê "
                    f"`st.session_state`. A geração roda em "
                    f"`threading.Thread` (imagem.py:7162), e de lá o "
                    f"session_state volta VAZIO: o campo é gravado em branco, "
                    f"sem erro nenhum. Leia de um global de módulo, como "
                    f"`_PECA_EM_AJUSTE` faz.")

    # ── 5-bis. CHAMADA DE TELA DE DENTRO DE UMA THREAD ────────────────────
    #
    # A MESMA FORMA 6, E EU A APLIQUEI A UM LEITOR SÓ.
    #
    # Em 28/09 descobri que `st.session_state` é ilegível dentro de uma
    # `threading.Thread`, varri o session_state — e parei ali. A restrição
    # não é do session_state: é do Streamlit inteiro. `st.warning` chamado de
    # uma thread não desenha nada, e não levanta erro nenhum.
    #
    # O QUE ISSO CUSTOU (achado em 30/09): havia EXATAMENTE UMA chamada de
    # tela dentro de `gerar_imagem_ia` — `st.warning("OpenAI falhou → usando
    # Gemini como fallback")`. Ela nunca apareceu para ninguém.
    #
    # E era a única frase que explicava os quatro defeitos que o dono relatou
    # no mesmo dia: "fotos menores que a dimensão da imagem, informações
    # recortadas, fotos nada a ver com o produto original, imagens com
    # margem". Os quatro são o mesmo estado — o motor reserva em campo, que
    # não aceita `size` nem `input_fidelity`. O sistema sabia, tentou contar,
    # e a frase morreu na thread.
    #
    # A regra: quem roda em thread escreve no DIAGNÓSTICO; quem desenha é a
    # tela, do lado certo do balcão.
    # ── ONDE A THREAD NAO QUER FALAR COM NINGUEM, E POR QUE ───────────
    #
    # A primeira versao desta regra deu ALARME FALSO em `placar.py`, com 9
    # linhas: o regenerador da TV chama `pagina_placar(headless=True)` de
    # dentro de uma thread DE PROPOSITO, para gravar o retrato da parede. O
    # proprio codigo diz (placar.py:3555): "as chamadas de UI viram no-op".
    #
    # Verificador que da alarme falso ensina a ignora-lo — foi por pouco que
    # eu nao reescrevi codigo certo. A isencao e por THREAD, com motivo
    # escrito, e nao por arquivo: isentar `placar.py` inteiro esconderia a
    # proxima thread de la que QUEIRA falar com alguem.
    THREADS_SEM_TELA = {
        "_loop_regenerador_tv":
            "desenha a pagina em modo headless para gravar o retrato da TV; "
            "as chamadas de tela sao no-op de proposito, e nao ha ninguem "
            "olhando do outro lado",
    }
    _UI_ST = {"warning", "error", "info", "success", "toast", "write",
              "markdown", "caption", "progress", "rerun", "image", "code"}
    for nome in _arquivos():
        with open(nome, encoding="utf-8") as fh:
            fonte = fh.read()
        try:
            arvore = ast.parse(fonte)
        except SyntaxError:
            continue
        funcs = {n.name: n for n in ast.walk(arvore)
                 if isinstance(n, ast.FunctionDef)}
        alvos = set()
        for n in ast.walk(arvore):
            if isinstance(n, ast.Call) and "Thread" in ast.unparse(n.func):
                for kw in n.keywords:
                    if kw.arg == "target":
                        alvos |= _nomes_de_alvo(kw.value)
        # fecho transitivo: quem a thread chama, e quem esses chamam
        alcanca, fila = set(), [a for a in alvos
                                if a in funcs and a not in THREADS_SEM_TELA]
        while fila:
            f = fila.pop()
            if f in alcanca:
                continue
            alcanca.add(f)
            for c in ast.walk(funcs[f]):
                if (isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                        and c.func.id in funcs):
                    fila.append(c.func.id)
        for f in sorted(alcanca):
            for c in ast.walk(funcs[f]):
                if (isinstance(c, ast.Call)
                        and isinstance(c.func, ast.Attribute)
                        and c.func.attr in _UI_ST
                        and ast.unparse(c.func.value) == "st"):
                    reprova(
                        f"{nome}:{c.lineno} — `st.{c.func.attr}` dentro de "
                        f"`{f}`, que roda em `threading.Thread`. De uma "
                        "thread o Streamlit NÃO desenha e NÃO levanta erro: "
                        "a mensagem some em silêncio. Grave no diagnóstico e "
                        "deixe a tela desenhar.")

    # ISENCAO ORFA MENTE PARA QUEM LE DEPOIS.
    _threads_existentes = set()
    for nome in _arquivos():
        try:
            _arv = ast.parse(open(nome, encoding="utf-8").read())
        except (SyntaxError, OSError):
            continue
        for n in ast.walk(_arv):
            if isinstance(n, ast.Call) and "Thread" in ast.unparse(n.func):
                for kw in n.keywords:
                    if kw.arg == "target":
                        _threads_existentes |= _nomes_de_alvo(kw.value)
    for _isenta in sorted(THREADS_SEM_TELA):
        if _isenta not in _threads_existentes:
            reprova(f"a isencao de tela para `{_isenta}` sobrou: essa thread "
                    "nao existe mais, e a isencao passa a mentir para quem "
                    "ler depois")

    # ── 5-quater. ESTADO DE PESSOA GUARDADO NUMA CAIXA DO PROCESSO ───────
    #
    # 30/09. Esta e a familia de defeito mais cara do dia, e ela apareceu
    # QUATRO vezes em tres arquivos diferentes:
    #
    #   log_imagem._CONTEXTO ....... produto e usuario trocados entre
    #                                colaboradores; o historico do «Compasso
    #                                Cortador» voltou com pecas de OUTRO
    #                                produto dentro, e a analise feita em cima
    #                                dele apontou um defeito que nao existia
    #   imagem._PECA_EM_AJUSTE ..... a peca do ajuste trocada entre duas
    #                                pessoas; o custo estava DECLARADO na
    #                                docstring e nao consertado
    #   relogio_ponto.TOLERANCIA_DETALHE  o detalhe da tolerancia escrito por
    #                                uma sessao e lido por outra — e esses
    #                                numeros entram na conta do bonus
    #
    # O Streamlit atende TODOS os colaboradores no MESMO processo. Um
    # dicionario de modulo nao e "uma variavel": e uma caixa compartilhada por
    # toda a equipe. O defeito nao e raro nem teorico — e so questao de duas
    # pessoas usarem a tela ao mesmo tempo, que e o dia normal aqui.
    #
    # POR QUE UMA LISTA, E NAO UM JULGAMENTO AUTOMATICO
    #
    # Cache de board, modelo descoberto na conta, nome de campo que a API usa:
    # esses SAO do processo por natureza, e acusa-los seria alarme falso —
    # verificador que da alarme falso ensina a ignora-lo. O que a maquina nao
    # consegue decidir e se aquele valor e de UMA PESSOA ou de TODAS.
    #
    # Entao cada caixa e classificada UMA vez, com o motivo escrito, igual ao
    # que esta base ja faz com `MUDAS_POR_ESCOLHA` e `THREADS_SEM_TELA`. Caixa
    # nova reprova ate alguem responder a pergunta — e a pergunta e sempre a
    # mesma: "dois colaboradores ao mesmo tempo trocam isto entre si?".
    ESTADO_DE_PROCESSO = {
        # Caches e memorias de consulta: a resposta e a mesma para todo mundo.
        "auth.py:_ULTIMOS_USUARIOS_OK": "lista de usuarios da planilha, igual para todos",
        "batidas.py:_CACHE": "cache da RHiD com chave propria",
        "bling_api.py:_ABA_CACHE": "aba da planilha, uma por processo",
        "bling_api.py:_CACHE": "token do Bling, da conta e nao da pessoa",
        "bling_api.py:_CANAIS_CACHE": "canais de venda da conta",
        "bling_api.py:_MES_CACHE": "faturamento do mes, com chave de mes",
        "bling_api.py:_SITUACOES_CACHE": "situacoes de pedido da conta",
        "imagem.py:_DESCRICAO_CACHE": "descricao de visao, com chave do produto",
        "placar_core.py:_acoes_cache": "acoes do Trello, com chave de janela",
        "placar_core.py:_board_cache": "board do Trello, um so",
        "placar_core.py:_tempos_cache": "tempos do board, com chave",
        "placar_core.py:_MAPA_LABELS": "etiquetas do board, iguais para todos",
        "sheets.py:ID_RECUSADO": "id de planilha que o Drive recusou",
        # Capacidades da CONTA e da API: nao variam por pessoa.
        "imagem.py:_MODELO_DESCOBERTO": "modelo de imagem que a conta tem",
        "imagem.py:_FORMA_PROPORCAO": "qual campo de proporcao esta API aceita",
        "rhid_api.py:ULTIMA_ORIGEM_ABONO": "nome do campo que a RHiD usa",
        "rhid_api.py:ULTIMA_ORIGEM_BATIDAS": "nome do campo que a RHiD usa",
        "placar_core.py:ALINHAMENTO_OLD": "formato que a API do Trello devolve",
        "placar_core.py:AMOSTRA_ACAO_ETIQUETA": "amostra do formato da acao",
        "placar_core.py:DIAGNOSTICO_POR_FILTRO": "diagnostico da consulta ao Trello",
        "placar_core.py:ULTIMO_DIAGNOSTICO_ACOES": "idem, da ultima consulta",
        # Cadastro e tabelas: sao da EMPRESA, nao de quem esta olhando.
        "placar_core.py:MEMBROS_ATIVOS": "a equipe cadastrada na planilha",
        "placar_core.py:MAPA_RHID": "de nome na RHiD para usuario do Trello",
        "metas_config.py:COLUNAS": "colunas da aba de metas",
        "metas_config.py:DEFAULTS": "padroes das metas",
        "metas_config.py:LABELS": "rotulos dos campos de meta",
        "cor_pedido.py:CORES": "registro de cores, montado no import",
        "fechar_expediente_conferencia.py:POSTS": "registro de conferencias",
        "placar.py:TV_STATUS": "estado da TV, que e uma tela so para todos",
        "placar_snapshot.py:_ULTIMO_DIA": "dia do ultimo retrato gravado",
        # POR THREAD, que e o conserto desta familia.
        "log_imagem.py:_CONTEXTO": "guardado POR THREAD (ident), nao por processo",
        # DECLARADO COM O CUSTO, e nao escondido.
        "imagem.py:_ULTIMO_DESCARTE_LAYOUT":
            "escrito DENTRO da thread e lido pela tela depois — por thread "
            "quebraria, porque a heranca e so de quem cria para quem e criado. "
            "O pior caso e um aviso a mais na tela de alguem; o prompt enviado "
            "nao depende dele. Consertar de vez pede o valor viajando no "
            "retorno por tres assinaturas.",
    }
    _caixas = {}
    for nome in _arquivos():
        try:
            _arv_ep = ast.parse(open(nome, encoding="utf-8").read())
        except (SyntaxError, OSError):
            continue
        _mut = {}
        for _n in _arv_ep.body:
            if isinstance(_n, ast.Assign) and isinstance(
                    _n.value, (ast.Dict, ast.List, ast.Set)):
                for _t in _n.targets:
                    if isinstance(_t, ast.Name):
                        _mut[_t.id] = _n.lineno
        for _fn in [x for x in ast.walk(_arv_ep)
                    if isinstance(x, ast.FunctionDef)]:
            for _c in ast.walk(_fn):
                _alvo = None
                if (isinstance(_c, ast.Call)
                        and isinstance(_c.func, ast.Attribute)
                        and _c.func.attr in ("update", "clear", "append",
                                             "pop", "setdefault", "add")
                        and isinstance(_c.func.value, ast.Name)):
                    _alvo = _c.func.value.id
                elif isinstance(_c, ast.Assign):
                    for _t in _c.targets:
                        if (isinstance(_t, ast.Subscript)
                                and isinstance(_t.value, ast.Name)):
                            _alvo = _t.value.id
                if _alvo and _alvo in _mut:
                    _caixas[f"{nome}:{_alvo}"] = (_mut[_alvo], _fn.name)
    for _chave in sorted(_caixas):
        if _chave not in ESTADO_DE_PROCESSO:
            _ln, _quem = _caixas[_chave]
            reprova(
                f"{_chave.replace(':', ':' + str(_ln) + ' — ')} e escrito em "
                f"execucao por `{_quem}`, e e um dicionario de MODULO: no "
                "Streamlit ele e compartilhado por TODA a equipe no mesmo "
                "processo. Responda se isto e de uma pessoa ou de todas: "
                "se e de uma, guarde por thread (ver `log_imagem`) ou "
                "devolva no retorno; se e de todas, declare em "
                "ESTADO_DE_PROCESSO com o motivo.")
    # ISENCAO ORFA MENTE PARA QUEM LE DEPOIS — igual as outras duas listas.
    for _chave in sorted(ESTADO_DE_PROCESSO):
        if _chave not in _caixas:
            reprova(f"a declaracao de ESTADO_DE_PROCESSO para `{_chave}` "
                    "sobrou: essa caixa nao existe mais, e a declaracao passa "
                    "a mentir para quem ler depois")

    # ── 5-ter. O ACHADO QUE FOI MAPEADO E NAO FOI TRATADO ─────────────────
    #
    # Dono, 30/09: "eu sinceramente ainda nao entendi como mapeou isso e nao
    # resolveu (...) como me garante que nao ha outros erros que mapeou e nao
    # tratou?".
    #
    # A resposta honesta e que eu nao garanto por promessa. Naquele dia varri
    # a cadeia Studio -> Gemini, achei treze defeitos, escrevi todos numa
    # lista minha, corrigi onze e DEIXEI DOIS — entre eles o `_tem_fotos`,
    # que e uma das causas de "produto nada a ver com o original". Ficou
    # aberto por horas enquanto eu relatava "APROVADO".
    #
    # Os oito verificadores guardam o CODIGO. Nada guardava a LISTA. Achado
    # anotado num bilhete depende de eu lembrar, e a mao eu nao faco igual
    # duas vezes — e a mesma razao pela qual `checar_mutacao.py` existe.
    #
    # Entao a lista deixa de ser bilhete: `ACHADOS_ABERTOS.md` fica no
    # repositorio, e todo item aberto tem de dizer POR QUE AINDA NAO foi
    # tratado. Sem o motivo escrito, a conferencia REPROVA. "Esqueci" nao e
    # motivo — mas escrito, ele para de ser esquecimento.
    _raiz_ab = os.path.dirname(os.path.abspath(__file__))
    _lista = os.path.join(_raiz_ab, "ACHADOS_ABERTOS.md")
    if not os.path.exists(_lista):
        reprova("ACHADOS_ABERTOS.md sumiu do repositorio — e a trava que "
                "impede um defeito mapeado de ficar aberto em silencio")
    else:
        with open(_lista, encoding="utf-8") as fh:
            _txt = fh.read()
        _itens, _atual = [], None
        for _ln in _txt.split("\n"):
            if _ln.startswith("### "):
                _atual = {"titulo": _ln[4:].strip(), "onde": False,
                          "porque": False}
                _itens.append(_atual)
            elif _atual is not None:
                if _ln.startswith("ONDE:"):
                    _atual["onde"] = bool(_ln[5:].strip())
                elif _ln.startswith("POR QUE AINDA NÃO:"):
                    _atual["porque"] = bool(_ln[18:].strip())
        for _it in _itens:
            if not _it["porque"]:
                reprova(f"o achado aberto «{_it['titulo'][:60]}» nao diz POR "
                        "QUE AINDA NAO foi tratado. Achado sem motivo escrito "
                        "e defeito esperando ser esquecido — foi assim que o "
                        "`_tem_fotos` ficou aberto enquanto eu dizia verde")
            if not _it["onde"]:
                reprova(f"o achado aberto «{_it['titulo'][:60]}» nao diz ONDE "
                        "— sem arquivo nem linha, quem ler depois nao acha")

    # ── 6. O CARIMBO QUE GENTE LÊ, E O MÊS QUE O SISTEMA CALCULA ───────────
    #
    # Forma 6a. O container roda em UTC. `datetime.now()` cru SERVE quando os
    # dois lados da conta são UTC — expiração de token contra token gravado,
    # idade de cartão do Trello contra ação do Trello. Não serve em dois
    # casos, e são estes que esta varredura reprova:
    #
    #   1. o valor é LIDO POR GENTE. O Histórico carimbava 17h em cima do que
    #      o colaborador gerou às 14h.
    #   2. o valor vira MÊS ou DIA. Às 21h do dia 30 o container já está no
    #      dia 1º: o chat respondia a pontuação do mês errado, e o retrato do
    #      placar seria gravado com a data de amanhã.
    #
    # A porta única é `placar_core.agora_br()` / `hoje_br()`.
    _CARIMBO = re.compile(r"datetime\.now\(\s*\)\s*\.(strftime|date)\b")
    _VIRA_MES = re.compile(r"datetime\.now\(\s*\)(?![^\n]*timedelta)")
    # Onde o `datetime.now()` cru continua CERTO, e por quê. Comparação de
    # UTC com UTC não tem erro de fuso: trocar um lado só é que teria.
    _CONSISTENTES = CONSISTENTES_UTC
    # ── ISENTA-SE A FUNÇÃO, NUNCA O ARQUIVO ────────────────────────────
    #
    # A isenção era por ARQUIVO, com UMA exceção escrita à mão para o
    # `placar_core.py`. Isso é corrigir onde o sintoma apareceu: os outros
    # cinco continuavam isentos inteiros.
    #
    # O estrago já documentado: isentei `placar_core` "porque é onde
    # `agora_br` mora", e isso escondeu `ritmo_do_mes`, que calcula mês e dia
    # — o velocímetro da Meta Mensal perdia a cor no fim do mês.
    #
    # E o mesmo desenho estava vivo no `auth.py`: a isenção dele diz
    # "expiração de token contra token gravado, os dois em UTC", que cobre a
    # comparação — e o arquivo tem OUTRO `datetime.now()`, que escreve hora
    # legível na planilha. Hoje os dois lados são UTC e não há erro; amanhã,
    # um terceiro uso entra sem ninguém ver.
    #
    # Agora cada isenção nomeia a FUNÇÃO: "arquivo.py:funcao". Uso fora das
    # funções isentas reprova, mesmo em arquivo isento.
    import ast as _ast_utc
    for nome, fonte in ((n, f) for n in _arquivos()
                        for f in [open(n, encoding="utf-8").read()]):
        # Fora do bloco de conferência: a guarda que procura `datetime.now()`
        # contém o texto `datetime.now()`. É a sexta vez nesta base.
        corpo = fonte.split('if __name__ == "__main__":')[0]
        _isentas = {c.split(":", 1)[1] for c in _CONSISTENTES
                    if c.startswith(nome + ":")}
        # De que função é cada linha — por AST, e não por indentação.
        _dona = {}
        try:
            for _n in _ast_utc.walk(_ast_utc.parse(corpo)):
                if isinstance(_n, (_ast_utc.FunctionDef,
                                   _ast_utc.AsyncFunctionDef)):
                    for _l in range(_n.lineno,
                                    (_n.end_lineno or _n.lineno) + 1):
                        _dona.setdefault(_l, _n.name)
        except SyntaxError:
            pass
        for i, linha in enumerate(corpo.splitlines(), 1):
            codigo = re.sub(r"`[^`]*`", "", linha.split("#", 1)[0])
            if not _VIRA_MES.search(codigo):
                continue
            if _dona.get(i) in _isentas:
                continue
            reprova(
                f"{nome}:{i} (em `{_dona.get(i) or 'fora de função'}`) — "
                f"`datetime.now()` sem fuso. O container roda em "
                f"UTC: se este valor é lido por gente, sai 3h adiantado; se "
                f"vira mês ou dia, erra depois das 21h. Use "
                f"`placar_core.agora_br()` ou `hoje_br()`.")

    # ── 7. MARCADOR DE CONFLITO COMMITADO ──────────────────────────────────
    #
    # 28/09: resolvi um merge nos tres arquivos `.py` que o git listou e NAO
    # olhei o `CLAUDE.md` — que tambem estava em conflito. O arquivo subiu com
    # `<<<<<<< HEAD` dentro, e nenhum dos seis verificadores leu: todos olham
    # codigo. E a Forma 1 na resolucao de conflito.
    #
    # Varre TODO arquivo de texto, e nao so `.py`: o defeito nasceu justamente
    # no que nao e codigo.
    import glob as _glob
    for _nome in sorted(_glob.glob("*.py") + _glob.glob("*.md")
                        + _glob.glob("*.txt") + _glob.glob("*.toml")):
        if _nome in IGNORAR_CONFLITO:
            continue
        try:
            with open(_nome, encoding="utf-8") as fh:
                _linhas = fh.read().splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for _i, _l in enumerate(_linhas, 1):
            if _l.startswith(("<<<<<<< ", ">>>>>>> ")):
                reprova(
                    f"{_nome}:{_i} — marcador de conflito de merge no arquivo "
                    f"commitado. Resolver os `.py` que o git listou e esquecer "
                    f"o resto e a Forma 1 na resolucao de conflito.")
                break

    # ── 4. O PROMPT DO PLANO ────────────────────────────────────────────────
    #
    # 28/09: as peças 7 e 8 sumiram e o produto saiu torto. A causa estava no
    # prompt do PLANO, que varredura nenhuma lia — `checar_prompts.py` monta o
    # prompt da IMAGEM. Sessenta regras verdes mediam outro texto.
    with open("checar_prompts.py", encoding="utf-8") as fh:
        varredura = fh.read()
    if "gerar_triagem_ia" not in varredura:
        reprova(
            "checar_prompts.py não lê o prompt do PLANO "
            "(`gerar_triagem_ia`). Ele decide quais peças são viáveis e qual "
            "ângulo usar — e foi ali que as peças 7 e 8 sumiram em 28/09, com "
            "os cinco verificadores verdes.")

    for _m in _conferir_isentos():
        reprova(_m)
    for _m in _gemeas_do_placar():
        reprova(_m)

    print()
    if falhas:
        print(f"FALHA  {len(falhas)} correção(ões) que não chegaram em todo "
              f"lugar.\n       A correção se aplica ao ALCANCE da regra, não "
              f"ao lugar onde o sintoma apareceu.")
        return 1
    print("ok    toda capacidade existe em todos os irmãos dela")
    return 0


if __name__ == "__main__":
    sys.exit(main())
