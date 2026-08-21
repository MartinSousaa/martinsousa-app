"""Camada única de acesso ao Google Drive do MS Studio.

Por que este módulo existe
--------------------------
O Google removeu a cota de armazenamento das contas de serviço. Uma service
account não pode mais SER DONA de arquivos: qualquer `files().create()` que
resultaria em um arquivo pertencente a ela falha com

    403 storageQuotaExceeded
    "Service Accounts do not have storage quota."

Isso vale mesmo quando a pasta de destino é compartilhada com a service account
como editor — o arquivo criado continua nascendo com ela como dona.

Existem três saídas, e este módulo suporta as três sem mudança de código:

1. UNIDADE COMPARTILHADA (Shared Drive) — exige Workspace Business Standard+.
   Os arquivos pertencem à unidade, não a uma pessoa. Basta apontar
   DRIVE_PASTA_IMAGENS_ID para uma pasta dentro da unidade compartilhada.
   Requer `supportsAllDrives=True` em toda chamada — sem isso a API rejeita
   a operação mesmo com a unidade configurada corretamente.

2. IMPERSONATION (domain-wide delegation) — exige Workspace + Admin Console.
   A service account age como um usuário real e os arquivos usam a cota dele.
   Configure a secret GDRIVE_IMPERSONATE_USER com o e-mail do usuário.

3. REFRESH TOKEN OAUTH — funciona até com conta Google pessoal/Gmail.
   Configure a secret [gdrive_oauth] com client_id, client_secret e
   refresh_token. Tem precedência sobre a service account.

Secrets reconhecidas
--------------------
    gcp_service_account       (obrigatória, salvo se usar gdrive_oauth)
    GDRIVE_IMPERSONATE_USER   (opcional) e-mail a impersonar
    gdrive_oauth              (opcional) bloco com client_id/client_secret/refresh_token
    DRIVE_PASTA_IMAGENS_ID    pasta raiz das imagens geradas
    DRIVE_PASTA_TRIAGENS_ID   pasta das fotos de triagem (cai em IMAGENS se vazia)
"""

import streamlit as st

SCOPE_DRIVE = "https://www.googleapis.com/auth/drive"

# Parâmetros exigidos pela API para operar em Unidades Compartilhadas.
# Sem eles a chamada falha mesmo quando a unidade está configurada certo.
_SHARED = {"supportsAllDrives": True}
_SHARED_LIST = {"supportsAllDrives": True, "includeItemsFromAllDrives": True}


# ── CREDENCIAIS ───────────────────────────────────────────────────────────────

def _secret(nome, padrao=""):
    """Lê uma secret sem estourar quando ela não existe."""
    try:
        return st.secrets.get(nome, padrao)
    except Exception:
        return padrao


def modo_credencial():
    """Retorna qual estratégia está ativa: 'oauth', 'impersonation' ou 'service_account'."""
    try:
        if "gdrive_oauth" in st.secrets:
            return "oauth"
    except Exception:
        pass
    if str(_secret("GDRIVE_IMPERSONATE_USER", "")).strip():
        return "impersonation"
    return "service_account"


def _credenciais():
    modo = modo_credencial()

    if modo == "oauth":
        from google.oauth2.credentials import Credentials as OAuthCreds
        bloco = dict(st.secrets["gdrive_oauth"])
        return OAuthCreds(
            token=None,
            refresh_token=bloco["refresh_token"],
            client_id=bloco["client_id"],
            client_secret=bloco["client_secret"],
            token_uri="https://oauth2.googleapis.com/token",
            scopes=[SCOPE_DRIVE],
        )

    from google.oauth2.service_account import Credentials as SACreds
    creds = SACreds.from_service_account_info(
        dict(st.secrets["gcp_service_account"]), scopes=[SCOPE_DRIVE]
    )
    if modo == "impersonation":
        creds = creds.with_subject(str(_secret("GDRIVE_IMPERSONATE_USER")).strip())
    return creds


def service():
    """Cliente do Drive v3 já configurado conforme as secrets."""
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=_credenciais(), cache_discovery=False)


# ── TRATAMENTO DE ERRO ────────────────────────────────────────────────────────

def erro_amigavel(exc):
    """Converte exceções do Drive em mensagem que o colaborador entende.

    O erro de cota é de CONFIGURAÇÃO, não algo que o colaborador possa resolver —
    então a mensagem precisa direcionar ao admin em vez de despejar o traceback.
    """
    texto = str(exc)
    if "storageQuotaExceeded" in texto or "do not have storage quota" in texto:
        return (
            "O Drive do sistema está sem configuração de armazenamento. "
            "Isso é um ajuste de administrador — avise o Léo. "
            "(Causa: a conta de serviço do Google não pode mais ser dona de arquivos; "
            "é preciso usar Unidade Compartilhada ou delegação OAuth.)"
        )
    if "notFound" in texto or "File not found" in texto:
        return ("A pasta de destino no Drive não foi encontrada ou não está compartilhada "
                "com a conta do sistema. Avise o administrador.")
    if "insufficientFilePermissions" in texto or "forbidden" in texto.lower():
        return ("A conta do sistema não tem permissão de escrita nessa pasta do Drive. "
                "Avise o administrador.")
    return texto


# ── OPERAÇÕES ─────────────────────────────────────────────────────────────────

def pasta_imagens_id():
    return str(_secret("DRIVE_PASTA_IMAGENS_ID", "")).strip()


def pasta_triagens_id():
    """Pasta das fotos de triagem. Cai na pasta de imagens se não configurada."""
    return (str(_secret("DRIVE_PASTA_TRIAGENS_ID", "")).strip()
            or pasta_imagens_id())


def tornar_publico(svc, file_id):
    """Libera leitura pública (necessário para os thumbnails).

    Não é fatal: em Workspace com compartilhamento externo bloqueado isso falha,
    mas o arquivo já foi salvo. Retorna True/False em vez de estourar.
    """
    try:
        svc.permissions().create(
            fileId=file_id,
            body={"role": "reader", "type": "anyone"},
            **_SHARED,
        ).execute()
        return True
    except Exception:
        return False


def upload(imagem_bytes, nome_arquivo, pasta_id, mimetype="image/png", publico=True):
    """Envia bytes para uma pasta do Drive. Retorna (info, erro).

    info = {"id": ..., "webViewLink": ..., "publico": bool}
    """
    from googleapiclient.http import MediaInMemoryUpload
    try:
        svc = service()
        metadata = {"name": nome_arquivo}
        if pasta_id:
            metadata["parents"] = [pasta_id]

        arquivo = svc.files().create(
            body=metadata,
            media_body=MediaInMemoryUpload(imagem_bytes, mimetype=mimetype),
            fields="id, webViewLink",
            **_SHARED,
        ).execute()

        publicado = tornar_publico(svc, arquivo["id"]) if publico else False
        return {
            "id": arquivo["id"],
            "webViewLink": arquivo.get("webViewLink"),
            "publico": publicado,
        }, None
    except Exception as e:
        return None, erro_amigavel(e)


def criar_pasta(nome_pasta, pasta_pai_id):
    """Cria pasta no Drive. Retorna (id, erro)."""
    try:
        svc = service()
        pasta = svc.files().create(
            body={
                "name": nome_pasta,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [pasta_pai_id],
            },
            fields="id",
            **_SHARED,
        ).execute()
        return pasta["id"], None
    except Exception as e:
        return None, erro_amigavel(e)


def listar(q, fields="files(id,name)"):
    """Lista arquivos/pastas. Retorna lista de dicts (vazia em caso de erro)."""
    try:
        res = service().files().list(q=q, fields=fields, **_SHARED_LIST).execute()
        return res.get("files", [])
    except Exception:
        return []


def mimetype_por_nome(nome_arquivo, padrao="image/jpeg"):
    ext = nome_arquivo.rsplit(".", 1)[-1].lower() if "." in nome_arquivo else ""
    return {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "webp": "image/webp",
    }.get(ext, padrao)


def url_thumbnail(file_id, tamanho=200):
    """URL de thumbnail do Drive (exige o arquivo público)."""
    if not file_id:
        return None
    return f"https://drive.google.com/thumbnail?id={file_id}&sz=w{tamanho}"


# ── DIAGNÓSTICO ───────────────────────────────────────────────────────────────

def diagnostico(pasta_id=None):
    """Checa a configuração de Drive ponta a ponta e devolve um relatório.

    Faz um upload de teste real e apaga em seguida — é a única forma de saber
    com certeza se a gravação funciona.

    Retorna dict com: modo, conta, pasta, shared_drive, escrita_ok, erro.
    """
    rel = {
        "modo": modo_credencial(),
        "conta": "",
        "impersonando": str(_secret("GDRIVE_IMPERSONATE_USER", "")).strip(),
        "pasta_id": pasta_id or pasta_imagens_id(),
        "pasta_nome": "",
        "shared_drive": False,
        "escrita_ok": False,
        "publico_ok": False,
        "erro": "",
    }

    try:
        rel["conta"] = dict(st.secrets["gcp_service_account"]).get("client_email", "")
    except Exception:
        pass

    if not rel["pasta_id"]:
        rel["erro"] = "DRIVE_PASTA_IMAGENS_ID não está configurada nas secrets."
        return rel

    try:
        svc = service()
        meta = svc.files().get(
            fileId=rel["pasta_id"],
            fields="id, name, driveId, mimeType",
            **_SHARED,
        ).execute()
        rel["pasta_nome"] = meta.get("name", "")
        rel["shared_drive"] = bool(meta.get("driveId"))
    except Exception as e:
        rel["erro"] = f"Não consegui ler a pasta de destino: {erro_amigavel(e)}"
        return rel

    # Upload de teste — 1x1 PNG transparente
    png_teste = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
    )
    info, err = upload(png_teste, "_teste_ms_studio.png", rel["pasta_id"], "image/png")
    if err:
        rel["erro"] = err
        return rel

    rel["escrita_ok"] = True
    rel["publico_ok"] = info.get("publico", False)

    try:
        service().files().delete(fileId=info["id"], **_SHARED).execute()
    except Exception:
        rel["erro"] = "Upload funcionou, mas não consegui apagar o arquivo de teste."

    return rel
