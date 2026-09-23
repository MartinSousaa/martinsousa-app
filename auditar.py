"""auditar.py — procurar o PRÓXIMO erro, e não o que já apareceu.

A PERGUNTA DO DONO
------------------
*"Não tem como pegar esses erros seus sem que um problema aconteça? Você não
consegue analisar os códigos considerando o histórico de tudo que já
corrigimos e considerar possíveis situações?"*

Tem. E é o que eu não estava fazendo: eu corrigia o caso, escrevia um teste
para aquele caso, e o mesmo DEFEITO DE FORMA continuava vivo em outro arquivo,
esperando alguém esbarrar nele.

COMO ELE FUNCIONA
-----------------
Cada defeito desta base virou uma CLASSE, com a marca que ela deixa no código.
O auditor procura a marca, não o sintoma. Exemplo: o que derrubou a
colaboradora não foi "a variável `img_fotos_sao_arte` estava errada" — foi
"marca de estado que só é ligada e nunca desligada". Essa forma se procura.

O QUE É ACHADO NÃO É NECESSARIAMENTE DEFEITO
---------------------------------------------
Um `except: pass` pode ser deliberado — a régua da imagem tem um, e está
certo: falha de medição não pode impedir a entrega do que já foi pago. Por
isso o auditor SEPARA em "revisar" e "conhecido", e cada exceção conhecida
carrega o motivo por escrito. Auditor que grita em tudo vira auditor que
ninguém roda.

    python3 auditar.py           só o que precisa de revisão
    python3 auditar.py --tudo    com os casos já revisados
"""

import os
import re
import sys

# O proprio auditor e a varredura de prompts CITAM as marcas que procuram.
# Incluí-los faz o auditor se acusar — e foi o que ele fez na primeira
# execucao, apontando as proprias linhas.
_FORA = {"auditar.py", "checar_prompts.py", "checar_ordem.py"}

ARQUIVOS = sorted(f for f in os.listdir(".")
                  if f.endswith(".py") and f not in _FORA
                  and not f.startswith("teste"))

# Os arquivos por onde a IMAGEM DO PRODUTO passa. A paleta da marca em CSS de
# tela e correta — ela E a identidade do Studio. O que nao pode e ela chegar na
# FOTO, e so estes arquivos podem faze-la chegar.
CAMINHO_DA_IMAGEM = ("imagem.py", "chat_assistente.py", "medir_imagem.py")

# ── Exceções já revisadas, com o motivo ─────────────────────────────────────
# (arquivo, trecho da linha) -> por que está certo assim.
CONHECIDOS = {
    ("medir_imagem.py", "except Exception:"):
        "a régua nunca pode impedir a entrega do que já foi pago",
    ("rascunho.py", "except Exception:"):
        "rascunho é conveniência; disco cheio não pode travar a geração",
    ("saude.py", "except Exception:"):
        "diário de reinícios é apoio, não requisito",
    ("log_imagem.py", "except Exception:"):
        "registro não pode impedir o colaborador de gerar imagem",
    # ── Revisados em 23/09, um a um ─────────────────────────────────────
    ("imagem.py", "except Exception:"):
        "registro em log e limpeza de cache; a gravação de verdade passa "
        "por guardar_rascunho, que mostra a falha na tela",
    ("chat_assistente.py", "except Exception:"):
        "registro do comando na planilha — nunca interrompe o fluxo",
    ("base_vendas.py", "except Exception:"):
        "limpar cache que talvez nem exista não é erro",
    ("cheques.py", "except Exception:"):
        "idem — invalidar cache de outro módulo é melhor-esforço",
    ("controle_ms.py", "except Exception:"): "limpeza de cache",
    ("metas_config.py", "except Exception:"): "limpeza de cache",
    ("financeiro.py", "except Exception:"): "limpeza de cache",
    ("placar.py", "except Exception:"): "limpeza de cache",
    ("analise_metas.py", "except Exception:"): "limpeza de cache",
    ("app.py", "_trabalho_restaurado"):
        "guarda de 'uma vez por sessão' — ligar e nunca desligar É o "
        "comportamento pedido",
    ("admin.py", "cms_testar"):
        "botão de teste; a marca morre com o rerun",
    ("admin.py", "adm_parados"):
        "botão de listagem; a marca morre com o rerun",
}


def _linhas(arq, so_producao=True):
    """As linhas do arquivo. Sem o bloco de conferencia, por padrao.

    Teste CITA o defeito para provar que ele nao voltou — a linha que procura
    pela cor da marca contem a cor da marca. Auditar o teste e auditar a
    propria prova, e foi o que encheu a primeira execucao de falso positivo.
    """
    with open(arq, encoding="utf-8") as fh:
        texto = fh.read()
    if so_producao:
        texto = texto.split('if __name__ == "__main__":')[0]
    return texto.split("\n")


def _e_comentario(l):
    """Comentario OU linha de texto corrido de docstring.

    Sem a segunda parte o auditor acusava a propria explicacao de por que a
    cor da marca nao pode ser usada — texto que cita a cor para proibi-la.
    """
    t = l.lstrip()
    if t.startswith("#"):
        return True
    # Linha de prosa dentro de docstring. A regra tem de ser ESTREITA: a
    # primeira versao classificava `if st.session_state.pop(...)` como prosa
    # — comeca com minuscula e nao tem "=" — e o auditor passou a nao
    # enxergar metade do codigo. Auditor cego e pior que auditor barulhento:
    # o barulhento incomoda, o cego da "ok" em cima de defeito.
    if not t or not t[0].islower():
        return False
    _PALAVRAS = ("if ", "for ", "while ", "with ", "def ", "class ", "try",
                 "elif ", "else", "return", "import ", "from ", "raise ",
                 "assert ", "yield ", "lambda", "print(", "del ", "pass",
                 "continue", "break", "except", "finally", "global ",
                 "not ", "and ", "or ")
    if t.startswith(_PALAVRAS):
        return False
    return "(" not in t and "=" not in t.split("#")[0] and "[" not in t


# ── CLASSE 1: marca de estado que só liga ───────────────────────────────────
# O caso real: `img_fotos_sao_arte` era ligada pelo Ajuste Fino e nunca
# desligada. Quem usasse o modo uma vez carregava a marca pela sessão inteira,
# e o Studio passava a recusar refazer dizendo uma coisa que não era verdade.
#
# Defeito de tempo: não erra quando é criado, erra na próxima vez que alguém
# faz outra coisa.
def classe_marca_so_liga():
    achados = []
    # O desligamento pode morar em OUTRO arquivo: `chat_assistente` liga e
    # `imagem` apaga com pop. Procurar so no proprio arquivo acusava cinco
    # marcas saudaveis — a sessao do Streamlit e uma so, o repositorio
    # inteiro e o escopo certo.
    tudo = "\n".join("\n".join(l for l in _linhas(a) if not _e_comentario(l))
                     for a in ARQUIVOS)
    for arq in ARQUIVOS:
        texto = "\n".join(l for l in _linhas(arq) if not _e_comentario(l))
        for chave in set(re.findall(r'session_state\["(\w+)"\]\s*=\s*True',
                                    texto)):
            # `.pop(chave)` TAMBEM desliga — e e como metade da base faz.
            # A primeira versao nao sabia disso e acusou cinco marcas
            # saudaveis. Auditor com falso positivo vira auditor ignorado.
            desligada = (f'session_state["{chave}"] = False' in tudo
                         or f'session_state.pop("{chave}"' in tudo
                         or f'del st.session_state["{chave}"]' in tudo)
            if not desligada:
                achados.append((arq, f'{chave} é ligada e nunca desligada'))
    return achados


# ── CLASSE 2: valor fixo de marca fora do prompt ────────────────────────────
# A paleta azul sobreviveu QUATRO vezes. Nas três primeiras estava no texto do
# prompt; na quarta estava num `bg_color`, pintada no pós-processamento, a
# duzentas linhas de qualquer palavra como "paleta" ou "visual".
def classe_cor_de_marca():
    achados = []
    cores = ("232, 238, 245", "#E8EEF5", "#1A3A6B", "#4A7EC7",
             "26, 58, 107", "74, 126, 199")
    for arq in CAMINHO_DA_IMAGEM:
        if not os.path.exists(arq):
            continue
        for n, l in enumerate(_linhas(arq), 1):
            if _e_comentario(l) or "ok(" in l:
                continue
            for c in cores:
                if c in l:
                    achados.append((arq, f"linha {n}: cor fixa da marca ({c})"))
    return achados


# ── CLASSE 3: medida feita e ignorada ───────────────────────────────────────
# O Studio media que tinha preenchido faixa, anotava no diagnóstico e
# entregava assim mesmo. Medir sem agir é gastar o cálculo e o retrabalho.
def classe_mede_e_entrega():
    achados = []
    for arq in ARQUIVOS:
        linhas = _linhas(arq)
        for n, l in enumerate(linhas, 1):
            if _e_comentario(l) or "diagnostico[" not in l or "=" not in l:
                continue
            # Diagnostico informativo (motor, tamanho, peso) nao e defeito
            # anotado: e registro. So interessa a anotacao que descreve algo
            # ERRADO — e aí seguir sem agir e o defeito.
            if not re.search(r"(falha|erro|problema|enquadr|medida|faixa|"
                             r"torta|recus|sem_credito)", l, re.I):
                continue
            # Depois de anotar um problema, algo tem de acontecer: repetir,
            # avisar na tela ou devolver erro. Só anotar é o defeito.
            # Janela larga o bastante para atravessar o comentario que
            # explica a decisao. Com 12 linhas o auditor acusava o proprio
            # enquadramento do imagem.py, que REPETE — so que 14 linhas
            # abaixo, depois do bloco que conta por que.
            janela = "\n".join(linhas[n:n + 30])
            if not re.search(r"(repet|st\.(warning|error)|return None|raise)",
                             janela):
                achados.append((arq, f"linha {n}: anota no diagnóstico e "
                                     "segue sem agir"))
    return achados


# ── CLASSE 4: casamento por pedaço de palavra ───────────────────────────────
# "CANVA" casava com "CANVAS ARTESANAL LTDA" e um fornecedor de tecido virava
# assinatura. Nome curto é prefixo de muita coisa.
def classe_substring():
    achados = []
    suspeito = re.compile(r'if\s+\w*(nome|chave|alvo|termo|fav\w*)\w*\s+in\s+'
                          r'\w*(texto|descricao|linha|conteudo)\w*\s*:')
    for arq in ARQUIVOS:
        for n, l in enumerate(_linhas(arq), 1):
            if _e_comentario(l):
                continue
            if suspeito.search(l):
                achados.append((arq, f"linha {n}: casa por pedaço de palavra"))
    return achados


# ── CLASSE 5: cache gravado sem invalidar ───────────────────────────────────
# Gravar na planilha sem limpar o cache faz a tela mostrar o valor velho e o
# usuário salvar de novo, achando que o clique não pegou.
def classe_cache_sem_clear():
    achados = []
    for arq in ARQUIVOS:
        texto = "\n".join(_linhas(arq))
        if "cache_data" not in texto:
            continue
        cacheadas = re.findall(r"@st\.cache_data[^\n]*\ndef (\w+)", texto)
        grava = re.search(r"def (salvar|gravar|atualizar|apagar)\w*\(", texto)
        if cacheadas and grava and ".clear()" not in texto:
            achados.append((arq, f"grava e tem cache ({', '.join(cacheadas)}) "
                                 "sem nenhum .clear()"))
    return achados


# ── CLASSE 6: except que engole sem deixar rastro ───────────────────────────
def classe_except_mudo():
    achados = []
    for arq in ARQUIVOS:
        linhas = _linhas(arq)
        for n, l in enumerate(linhas, 1):
            if _e_comentario(l) or "except" not in l:
                continue
            seguinte = linhas[n].strip() if n < len(linhas) else ""
            if seguinte not in ("pass", "continue"):
                continue
            if any(k[0] == arq and k[1] in l for k in CONHECIDOS):
                continue
            # So interessa o `except` que engole uma ESCRITA — gravar,
            # salvar, registrar. Engolir uma LEITURA que tem valor padrao e
            # decisao comum e barata; engolir uma escrita perde dado, e foi
            # assim que a copia de seguranca das imagens falhou calada.
            _antes = "\n".join(linhas[max(0, n - 12):n])
            if not re.search(r"\.(salvar|gravar|append_row|update|registrar|"
                             r"put|write|clear)\(", _antes):
                continue
            # Comentário logo acima explicando conta como decisão tomada.
            explicado = any(_e_comentario(x) for x in linhas[max(0, n - 4):n - 1])
            if not explicado:
                achados.append((arq, f"linha {n}: engole o erro sem explicar"))
    return achados


# ── CLASSE 7: cifrão cru em texto que passa pelo markdown ───────────────────
# O markdown do Streamlit lê `$...$` como LaTeX. Uma frase com DOIS cifrões
# perde tudo o que está entre eles dentro de uma fórmula matemática — e é
# justamente a frase que compara dois valores, que é sempre a mais importante.
# Aconteceu com o alerta de ICMS-DIFAL da fatura do ML (o aviso central da
# tela saiu ilegível), e a varredura achou o mesmo defeito vivo em outras
# duas telas que ninguém tinha reclamado ainda.
#
# Procura a FORMA — dois cifrões não escapados no mesmo texto —, e não a
# palavra "DIFAL": a TV escapa porque monta a página sem markdown.
_MD_ST = ("markdown", "caption", "warning", "info", "success", "error",
          "write")


def _texto_do_argumento(no, ast):
    if isinstance(no, ast.Constant):
        return no.value if isinstance(no.value, str) else "\x00"
    if isinstance(no, ast.JoinedStr):
        return "".join(_texto_do_argumento(v, ast) for v in no.values)
    if isinstance(no, ast.BinOp) and isinstance(no.op, ast.Add):
        return (_texto_do_argumento(no.left, ast)
                + _texto_do_argumento(no.right, ast))
    return "\x00"


def classe_cifrao_vira_formula():
    import ast
    achados = []
    for arq in ARQUIVOS:
        try:
            arvore = ast.parse(open(arq, encoding="utf-8").read())
        except (SyntaxError, OSError):
            continue
        for no in ast.walk(arvore):
            if not (isinstance(no, ast.Call)
                    and isinstance(no.func, ast.Attribute)
                    and no.func.attr in _MD_ST
                    and isinstance(no.func.value, ast.Name)
                    and no.func.value.id in ("st", "_st") and no.args):
                continue
            # HTML cru não passa pelo LaTeX do markdown.
            if any(k.arg == "unsafe_allow_html" for k in no.keywords):
                continue
            texto = _texto_do_argumento(no.args[0], ast)
            crus = len(re.findall(r"(?<!\\)\$", texto))
            campos = texto.count("\x00")
            # Dois crus já fecham a fórmula. Um cru mais um campo também: o
            # campo costuma trazer outro "R$" formatado.
            if crus >= 2 or (crus >= 1 and campos):
                achados.append((arq, f"linha {no.lineno}: cifrão cru em "
                                     "markdown — vira fórmula LaTeX"))
    return achados


CLASSES = [
    ("marca de estado que só liga", classe_marca_so_liga),
    ("cor fixa da marca fora do prompt", classe_cor_de_marca),
    ("mede o defeito e entrega assim mesmo", classe_mede_e_entrega),
    ("casamento por pedaço de palavra", classe_substring),
    ("grava em planilha sem limpar o cache", classe_cache_sem_clear),
    ("except que engole o erro sem explicar", classe_except_mudo),
    ("cifrão cru em markdown vira fórmula", classe_cifrao_vira_formula),
]


def main():
    total = 0
    for nome, fn in CLASSES:
        try:
            achados = fn()
        except Exception as e:
            print(f"!! a classe '{nome}' quebrou: {type(e).__name__}: {e}")
            continue
        if not achados:
            print(f"ok    {nome}: nada")
            continue
        print(f"\n>> {nome}: {len(achados)}")
        for arq, det in achados[:12]:
            print(f"      {arq} — {det}")
        if len(achados) > 12:
            print(f"      … e mais {len(achados) - 12}")
        total += len(achados)
    print(f"\npontos para revisar: {total}")
    # Auditoria NÃO reprova build: ela levanta suspeita, e suspeita se
    # confirma lendo o código. Fazê-la travar o push transformaria cada falso
    # positivo em pressão para silenciar o auditor.
    return 0


if __name__ == "__main__":
    sys.exit(main())
