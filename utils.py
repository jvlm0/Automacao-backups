from datetime import timedelta
import logging
import os

import ftp_transfer

def list_local_zips(backup_folder, prefix):
    """Retorna set de nomes de arquivos .zip locais começando com prefix (ex: 'empresa1_')."""
    s = set()
    for fn in os.listdir(backup_folder):
        if fn.lower().endswith(".zip") and fn.startswith(prefix):
            s.add(fn)
    return s

def sync_local_zips_to_ftp(backup_folder, name, ftp_config):
    """
    Verifica arquivos locais .zip e compara com arquivos remotos.
    Faz upload dos que estiverem faltando.
    Retorna (uploaded_list, failed_list, message)
    """
    if not ftp_config or not ftp_config.get("host"):
        return [], [], "FTP não configurado"

    # montar remote_dir_bank igual ao upload usual
    remote_root = ftp_config.get("remote_dir", ".") or "."
    remote_root = remote_root.replace("\\", "/").rstrip("/")
    bank_name_safe = name.replace("\\", "_").replace("/", "_").strip()
    if remote_root in (".", ""):
        remote_dir_bank = bank_name_safe
    else:
        remote_dir_bank = f"{remote_root}/{bank_name_safe}"

    prefix = f"{name}_"
    local = list_local_zips(backup_folder, prefix)
    if not local:
        return [], [], "Nenhum zip local encontrado"

    ok, remote_or_msg = ftp_transfer.list_remote_files(
        host=ftp_config.get("host"),
        username=ftp_config.get("user"),
        password=ftp_config.get("password"),
        remote_dir=remote_dir_bank,
        port=int(ftp_config.get("port", 21)),
        secure=bool(ftp_config.get("secure", False)),
        timeout=int(ftp_config.get("timeout", 30)),
        passive=bool(ftp_config.get("passive", True))
    )

    if not ok:
        # se falhou ao listar, tentar criar a pasta explicitamente e prosseguir com upload de todos locais
        logging.warning(f"Falha ao listar remoto {remote_dir_bank}: {remote_or_msg}. Tentando criar o diretório e fazer upload de todos os locais.")
        # garantir diretório remoto / tentativa de upload direto (upload_file_to_ftp cuida de criar)
        remote_files = set()
    else:
        remote_files = remote_or_msg

    missing = sorted(list(local - remote_files))  # nomes que existem local mas faltam no FTP
    uploaded = []
    failed = []

    for fn in missing:
        local_path = os.path.join(backup_folder, fn)
        logging.info(f"Sync: enviando arquivo ausente para FTP: {fn} -> {remote_dir_bank}")
        ok_up, msg = ftp_transfer.upload_file_to_ftp(
            local_path=local_path,
            host=ftp_config.get("host"),
            username=ftp_config.get("user"),
            password=ftp_config.get("password"),
            remote_dir=remote_dir_bank,
            port=int(ftp_config.get("port", 21)),
            secure=bool(ftp_config.get("secure", False)),
            timeout=int(ftp_config.get("timeout", 30)),
            passive=bool(ftp_config.get("passive", True))
        )
        if ok_up:
            uploaded.append(fn)
        else:
            failed.append((fn, msg))
            logging.error(f"Sync: falha ao enviar {fn}: {msg}")

    return uploaded, failed, f"missing={len(missing)} remote_count={len(remote_files)}"