# ftp_transfer.py
"""
Upload via FTP/FTPS com logging mais explícito (INFO em passos principais),
tenta criar diretórios recursivamente tanto relativos quanto absolutos.
"""

import os
import ftplib
import logging
from typing import Tuple
from datetime import datetime

# usa o logger root (herda configuração do seu main)
logger = logging.getLogger(__name__)

def _ensure_remote_dirs(ftp: ftplib.FTP, path: str) -> None:
    """
    Garante que o diretório remoto exista (tenta criar recursivamente).
    Lança Exception se não puder criar/entrar em algum segmento.
    """
    if not path or path == ".":
        logger.info("remote_dir is '.' or empty — nada a criar.")
        return

    is_absolute = path.startswith("/")
    parts = [p for p in path.replace("\\", "/").split("/") if p]

    if is_absolute:
        try:
            ftp.cwd("/")
            logger.info("Tentativa de cwd('/') bem-sucedida (root).")
        except Exception as e:
            logger.debug(f"cwd('/') falhou (pode ser normal): {e}")

    cur_path = ""
    for i, part in enumerate(parts):
        cur_path = (cur_path + "/" + part) if cur_path else part
        rel = part
        abs_path = "/" + "/".join(parts[: i + 1]) if is_absolute else "/".join(parts[: i + 1])

        logger.info(f"Tentando garantir pasta remota: '{part}' (rel='{rel}' abs='{abs_path}')")

        # 1) tentar entrar no rel
        try:
            ftp.cwd(rel)
            logger.info(f"cwd('{rel}') ok (relativo).")
            continue
        except Exception as e_rel:
            logger.debug(f"cwd('{rel}') falhou: {e_rel}")

        # 2) tentar criar rel
        try:
            ftp.mkd(rel)
            ftp.cwd(rel)
            logger.info(f"mkd('{rel}') + cwd('{rel}') ok (relativo).")
            continue
        except Exception as e_mkd_rel:
            logger.debug(f"mkd('{rel}') falhou: {e_mkd_rel}")

        # 3) tentar criar abs_path
        try:
            ftp.mkd(abs_path)
            ftp.cwd(abs_path)
            logger.info(f"mkd('{abs_path}') + cwd('{abs_path}') ok (absoluto).")
            continue
        except Exception as e_abs:
            logger.debug(f"mkd/cwd abs '{abs_path}' falhou: {e_abs}")

        # 4) tentar apenas cwd(abs_path)
        try:
            ftp.cwd(abs_path)
            logger.info(f"cwd('{abs_path}') ok (absoluto).")
            continue
        except Exception as e_cwd_abs:
            logger.debug(f"cwd('{abs_path}') também falhou: {e_cwd_abs}")

        raise Exception(f"Não foi possível criar/entrar no diretório remoto '{part}' (todas as tentativas falharam).")

def upload_file_to_ftp(local_path: str,
                       host: str,
                       username: str,
                       password: str,
                       remote_dir: str = ".",
                       port: int = 21,
                       secure: bool = False,
                       timeout: int = 30,
                       passive: bool = True) -> Tuple[bool, str]:
    """
    Envia local_path ao servidor FTP/FTPS. Retorna (True,msg) ou (False,msg).
    """
    if not os.path.isfile(local_path):
        return False, f"Arquivo local não encontrado: {local_path}"

    fname = os.path.basename(local_path)
    rd = (remote_dir or ".").replace("\\", "/")

    ftp = None
    try:
        if secure:
            ftp = ftplib.FTP_TLS(timeout=timeout)
            logger.info("Usando FTPS (FTP_TLS).")
        else:
            ftp = ftplib.FTP(timeout=timeout)
            logger.info("Usando FTP simples.")

        logger.info(f"Conectando em {host}:{port} ...")
        ftp.connect(host, port, timeout=timeout)
        logger.info("Conectado. Efetuando login...")
        ftp.login(username, password)
        ftp.set_pasv(passive)
        logger.info(f"Login OK. passive={passive}")

        if secure and isinstance(ftp, ftplib.FTP_TLS):
            try:
                ftp.prot_p()
                logger.info("Canal de dados protegido (PROT P) aplicado.")
            except Exception as e:
                logger.debug(f"prot_p() falhou (não fatal): {e}")

        # tentar criar/entrar no diretório remoto pedido
        try:
            _ensure_remote_dirs(ftp, rd)
        except Exception as e:
            logger.info(f"Tentativa inicial de criar/entrar em '{rd}' falhou: {e}. Tentando a partir da raiz...")
            try:
                ftp.cwd("/")
                _ensure_remote_dirs(ftp, rd)
            except Exception as e2:
                try:
                    ftp.quit()
                except Exception:
                    pass
                logger.error(f"Não foi possível criar/entrar no diretório remoto '{remote_dir}': {e2}")
                return False, f"Não foi possível criar/entrar no diretório remoto '{remote_dir}': {e2}"

        try:
            current = ftp.pwd()
            logger.info(f"Diretório remoto atual após criação: {current}")
        except Exception:
            logger.debug("Não foi possível obter PWD do servidor (não crítico).")

        # enviar o arquivo
        logger.info(f"Enviando '{fname}' -> {host}:{remote_dir}")
        with open(local_path, "rb") as f:
            ftp.storbinary(f"STOR {fname}", f)
        logger.info(f"Upload concluído: {fname}")

        try:
            ftp.quit()
        except Exception:
            try:
                ftp.close()
            except Exception:
                pass

        return True, f"Enviado com sucesso: {fname} -> {host}:{remote_dir}"
    except ftplib.all_errors as e:
        logger.exception("Erro FTP durante upload")
        try:
            if ftp:
                ftp.quit()
        except Exception:
            pass
        return False, f"Erro FTP: {e}"
    except Exception as e:
        logger.exception("Erro inesperado durante upload FTP")
        try:
            if ftp:
                ftp.quit()
        except Exception:
            pass
        return False, f"Erro inesperado: {e}"
    
    
def list_remote_files(host: str,
                      username: str,
                      password: str,
                      remote_dir: str = ".",
                      port: int = 21,
                      secure: bool = False,
                      timeout: int = 30,
                      passive: bool = True):
    """
    Lista arquivos no diretório remoto (não recursivo).
    Retorna (True, set(filenames)) em sucesso, ou (False, mensagem) em falha.
    Filenames são apenas os nomes (ex: 'empresa1_20251231_170608.zip').
    """
    try:
        if secure:
            ftp = ftplib.FTP_TLS(timeout=timeout)
        else:
            ftp = ftplib.FTP(timeout=timeout)

        ftp.connect(host, port, timeout=timeout)
        ftp.login(username, password)
        ftp.set_pasv(passive)

        if secure and isinstance(ftp, ftplib.FTP_TLS):
            try:
                ftp.prot_p()
            except Exception:
                pass

        # garantir que entramos no remote_dir (reusar a mesma lógica de criação/entrada)
        try:
            _ensure_remote_dirs(ftp, remote_dir)
        except Exception:
            # tentar partir da raiz
            try:
                ftp.cwd("/")
                _ensure_remote_dirs(ftp, remote_dir)
            except Exception as e:
                try:
                    ftp.quit()
                except Exception:
                    pass
                return False, f"Não foi possível entrar em remote_dir '{remote_dir}': {e}"

        # tentar listar (nlst é geralmente suportado)
        try:
            names = ftp.nlst()
        except ftplib.error_perm as e_perm:
            # servidor pode devolver erro 550 se diretório vazio; tratar como vazio
            if str(e_perm).startswith("550"):
                names = []
            else:
                ftp.quit()
                return False, f"Erro ao listar arquivos (nlst): {e_perm}"
        except Exception as e:
            ftp.quit()
            return False, f"Erro ao listar arquivos: {e}"

        # finalizar conexão
        try:
            ftp.quit()
        except Exception:
            pass

        # filtrar para apenas nomes (nem todos servidores devolvem caminho completo)
        basenames = {os.path.basename(n) for n in names if n}
        return True, basenames

    except ftplib.all_errors as e:
        try:
            ftp.quit()
        except Exception:
            pass
        return False, f"Erro FTP ao listar: {e}"
    except Exception as e:
        try:
            ftp.quit()
        except Exception:
            pass
        return False, f"Erro inesperado ao listar remoto: {e}"


def delete_remote_file(host: str,
                       username: str,
                       password: str,
                       remote_dir: str,
                       filename: str,
                       port: int = 21,
                       secure: bool = False,
                       timeout: int = 30,
                       passive: bool = True):
    """
    Deleta 'filename' dentro de 'remote_dir' no servidor FTP. Retorna (True,msg) ou (False,msg).
    """
    try:
        if secure:
            ftp = ftplib.FTP_TLS(timeout=timeout)
        else:
            ftp = ftplib.FTP(timeout=timeout)
        ftp.connect(host, port, timeout=timeout)
        ftp.login(username, password)
        ftp.set_pasv(passive)
        if secure and isinstance(ftp, ftplib.FTP_TLS):
            try:
                ftp.prot_p()
            except Exception:
                pass

        # entrar no diretório (não criar)
        rd = (remote_dir or ".").replace("\\", "/")
        try:
            ftp.cwd(rd)
        except Exception as e:
            try:
                ftp.quit()
            except Exception:
                pass
            return False, f"Não foi possível entrar no diretório remoto '{remote_dir}' para deletar: {e}"

        try:
            ftp.delete(filename)
        except ftplib.all_errors as e:
            try:
                ftp.quit()
            except Exception:
                pass
            return False, f"Erro ao deletar remoto '{filename}': {e}"
        try:
            ftp.quit()
        except Exception:
            pass
        return True, f"Deletado: {filename} em {remote_dir}"
    except ftplib.all_errors as e:
        try:
            ftp.quit()
        except Exception:
            pass
        return False, f"Erro FTP ao deletar '{filename}': {e}"
    except Exception as e:
        try:
            ftp.quit()
        except Exception:
            pass
        return False, f"Erro inesperado ao deletar '{filename}': {e}"


def enforce_remote_retention(host: str,
                             username: str,
                             password: str,
                             remote_dir: str,
                             db_name: str,
                             max_keep: int,
                             port: int = 21,
                             secure: bool = False,
                             timeout: int = 30,
                             passive: bool = True):
    """
    Garante que no remote_dir (pasta do banco) existam no máximo 'max_keep' arquivos do padrão
    <db_name>_YYYYMMDD_HHMMSS.zip (ou HHMM). Se houver mais, deleta os mais antigos primeiro.
    Retorna (True, deleted_list) em sucesso, ou (False, mensagem) em falha.
    """
    try:
        # listar arquivos remotos (reaproveita list_remote_files)
        ok, result = list_remote_files(host=host, username=username, password=password,
                                       remote_dir=remote_dir, port=port, secure=secure,
                                       timeout=timeout, passive=passive)
        if not ok:
            return False, f"Falha ao listar remoto {remote_dir}: {result}"

        remote_files = result  # set de nomes
        # selecionar apenas os zips com prefixo db_name_
        candidates = []
        prefix = f"{db_name}_"
        for fn in remote_files:
            if not fn.lower().endswith(".zip"):
                continue
            if not fn.startswith(prefix):
                continue
            base = os.path.splitext(fn)[0]
            parts = base.rsplit("_", 2)
            if len(parts) < 3:
                continue
            name_part, date_part, time_part = parts
            if name_part != db_name:
                continue
            # tentar parsear data+hora
            try:
                if len(time_part) == 6 and len(date_part) == 8:
                    dt = datetime.strptime(date_part + time_part, "%Y%m%d%H%M%S")
                elif len(time_part) == 4 and len(date_part) == 8:
                    dt = datetime.strptime(date_part + time_part + "00", "%Y%m%d%H%M%S")
                else:
                    # formato inesperado, usar epoch 0 para empurrar para o início (ou pular)
                    continue
                candidates.append((dt, fn))
            except Exception:
                # pular arquivos que não casam o padrão
                continue

        # ordenar do mais antigo para o mais novo
        candidates.sort(key=lambda x: x[0])

        current_count = len(candidates)
        logging.info(f"enforce_remote_retention: {current_count} arquivos encontrados para '{db_name}' em '{remote_dir}'. max_keep={max_keep}")
        if current_count <= max_keep:
            return True, []  # nada a fazer

        # quantos deletar
        to_delete_count = current_count - max_keep + 1
        deleted = []
        for i in range(to_delete_count):
            fname = candidates[i][1]
            # deletar via delete_remote_file
            ok_del, msg_del = delete_remote_file(host=host, username=username, password=password,
                                                 remote_dir=remote_dir, filename=fname,
                                                 port=port, secure=secure, timeout=timeout, passive=passive)
            if ok_del:
                deleted.append(fname)
            else:
                # se não conseguiu deletar, retornar erro (parcial ou total)
                return False, f"Falha ao deletar antigo '{fname}': {msg_del}"

        return True, deleted

    except Exception as e:
        return False, f"Erro inesperado em enforce_remote_retention: {e}"
