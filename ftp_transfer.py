# ftp_transfer.py
"""
Upload via FTP/FTPS com logging mais explícito (INFO em passos principais),
tenta criar diretórios recursivamente tanto relativos quanto absolutos.
"""

import os
import ftplib
import logging
from typing import Tuple

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
