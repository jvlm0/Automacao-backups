#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import subprocess
import configparser
from datetime import datetime, date
import logging
import zipfile

# importa o módulo de upload (arquivo ftp_transfer.py ao lado)
import ftp_transfer

# ---------- CONFIG ----------
BACKUP_ROOT = r"C:\Backups"
LOG_FILE = os.path.join(BACKUP_ROOT, "backup_script.log")
CHECK_INTERVAL_SECONDS = 30  # checa horários a cada 30 segundos
# ----------------------------

# Setup logging
os.makedirs(BACKUP_ROOT, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

def load_config(ini_path):
    config = configparser.ConfigParser()
    read = config.read(ini_path, encoding="utf-8")
    if not read:
        raise FileNotFoundError(f"Arquivo INI não encontrado ou vazio: {ini_path}")
    return config

def find_gbak(gbak_path_from_ini):
    if gbak_path_from_ini:
        gbak = gbak_path_from_ini
        if not os.path.isfile(gbak):
            raise FileNotFoundError(f"gbak não encontrado em: {gbak}")
        return gbak
    else:
        return "gbak"  # assume que está no PATH

def ensure_backup_folder(db_name):
    path = os.path.join(BACKUP_ROOT, db_name)
    os.makedirs(path, exist_ok=True)
    return path

def run_gbak_backup(gbak, user, password, source, dest_backup_path, timeout=None):
    cmd = [gbak, "-b", "-v"]
    if user:
        cmd += ["-user", user]
    if password:
        cmd += ["-password", password]
    cmd += [source, dest_backup_path]
    logging.info(f"Iniciando backup: {' '.join(cmd)}")
    try:
        if timeout:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
        else:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except subprocess.TimeoutExpired as te:
        logging.error(f"gbak timeout: {te}")
        return False, str(te)
    logging.info(result.stdout)
    return result.returncode == 0, result.stdout

def verify_backup_by_restore(gbak, user, password, backup_file, restore_db_path, timeout=None):
    cmd = [gbak, "-c", "-v"]
    if user:
        cmd += ["-user", user]
    if password:
        cmd += ["-password", password]
    cmd += [backup_file, restore_db_path]
    logging.info(f"Verificando backup (tentando restaurar): {' '.join(cmd)}")
    try:
        if timeout:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
        else:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except subprocess.TimeoutExpired as te:
        logging.error(f"gbak (restore) timeout: {te}")
        return False, str(te)
    logging.info(result.stdout)
    success = result.returncode == 0
    return success, result.stdout

def zip_file(file_path, zip_path):
    """
    Compacta file_path num zip_path (substitui se já existir).
    O arquivo dentro do zip manterá apenas o nome base (sem caminho).
    """
    try:
        with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(file_path, arcname=os.path.basename(file_path))
        logging.info(f"Arquivo zipado: {zip_path}")
        return True
    except Exception as e:
        logging.error(f"Falha ao zipar {file_path} -> {zip_path}: {e}")
        return False

def remove_old_backups_zip(backup_folder, prefix, max_keep):
    """
    Mantém apenas os N zips mais recentes que começam com prefix (prefix inclui name_).
    """
    files = []
    for fn in os.listdir(backup_folder):
        if fn.lower().endswith(".zip") and fn.startswith(prefix):
            full = os.path.join(backup_folder, fn)
            files.append((os.path.getmtime(full), full))
    files.sort()  # do mais antigo para o mais novo
    while len(files) > max_keep:
        oldest = files.pop(0)[1]
        try:
            os.remove(oldest)
            logging.info(f"Removido zip antigo: {oldest}")
        except Exception as e:
            logging.error(f"Erro removendo {oldest}: {e}")

def make_timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def backup_now(gbak, db_cfg, backup_folder, gbak_timeout=None, verify_timeout=None, ftp_config=None):
    """
    Executa gbak (gera .fbk), verifica restaurando para um .fdb com o MESMO timestamp
    do .fbk, zipa o .fdb com o MESMO nome base do .fbk (extensão .zip), e então
    remove o .fbk e o .fdb, deixando apenas o .zip. Se ftp_config for fornecido,
    tenta enviar o zip ao servidor FTP/FTPS.
    """
    name = db_cfg.get("name")
    source = db_cfg.get("source")
    user = db_cfg.get("user", "")
    password = db_cfg.get("password", "")
    max_backups = int(db_cfg.get("max_backups", "7"))

    ts = make_timestamp()
    fbk_filename = f"{name}_{ts}.fbk"
    fbk_path = os.path.join(backup_folder, fbk_filename)

    start = datetime.now()
    ok, out = run_gbak_backup(gbak, user, password, source, fbk_path, timeout=gbak_timeout)
    duration = (datetime.now() - start).total_seconds()
    logging.info(f"Duração do gbak (backup) para {name}: {duration:.1f}s")

    if not ok:
        logging.error(f"Falha no gbak ao gerar backup para {name}. Arquivo possivelmente criado está inválido.")
        if os.path.exists(fbk_path):
            try:
                os.remove(fbk_path)
            except Exception:
                pass
        return False

    # Verificação: restaurar para um .fdb com MESMO timestamp (nome igual ao .fbk, exceto extensão)
    fdb_filename = f"{name}_{ts}.fdb"
    fdb_path = os.path.join(backup_folder, fdb_filename)

    start_v = datetime.now()
    ver_ok, ver_out = verify_backup_by_restore(gbak, user, password, fbk_path, fdb_path, timeout=verify_timeout)
    duration_v = (datetime.now() - start_v).total_seconds()
    logging.info(f"Duração da verificação (restore) para {name}: {duration_v:.1f}s")

    if not ver_ok:
        logging.error(f"Verificação falhou para backup {fbk_path}. Removendo arquivos inválidos (se existirem).")
        try:
            if os.path.exists(fbk_path):
                os.remove(fbk_path)
        except Exception as e:
            logging.warning(f"Não foi possível remover {fbk_path}: {e}")
        try:
            if os.path.exists(fdb_path):
                os.remove(fdb_path)
        except Exception as e:
            logging.warning(f"Não foi possível remover {fdb_path}: {e}")
        return False

    # Se ver_ok: zipar o fdb com o mesmo nome base e manter apenas o zip
    zip_filename = f"{name}_{ts}.zip"
    zip_path = os.path.join(backup_folder, zip_filename)

    zipped = zip_file(fdb_path, zip_path)
    if not zipped:
        logging.error(f"Falha ao criar zip para {fdb_path}. Não removerei arquivos automaticamente para investigação.")
        return False

    # remover .fbk e .fdb (ficará apenas o zip)
    try:
        if os.path.exists(fbk_path):
            os.remove(fbk_path)
    except Exception as e:
        logging.warning(f"Não foi possível remover {fbk_path}: {e}")
    try:
        if os.path.exists(fdb_path):
            os.remove(fdb_path)
    except Exception as e:
        logging.warning(f"Não foi possível remover {fdb_path}: {e}")

    logging.info(f"Backup finalizado e armazenado como zip: {zip_path}")

    # Se FTP configurado, tentar enviar
    if ftp_config and ftp_config.get("host"):
        try:
            # monta diretório remoto específico para o banco: <remote_root>/<nome_do_banco>
            remote_root = ftp_config.get("remote_dir", ".") or "."
            # normaliza barras e remove barra final
            remote_root = remote_root.replace("\\", "/").rstrip('/')
            # sanitize do nome do banco (evita barras acidentais)
            bank_name_safe = name.replace("\\", "_").replace("/", "_").strip()
            # monta remote_dir final
            if remote_root in (".", ""):
                remote_dir_bank = bank_name_safe
            else:
                # se remote_root começar com '/', preserva (para caminho absoluto)
                remote_dir_bank = f"{remote_root}/{bank_name_safe}"

            logging.info(f"Preparando upload FTP para diretório remoto: {remote_dir_bank}")

            ok_upload, msg = ftp_transfer.upload_file_to_ftp(
                local_path=zip_path,
                host=ftp_config.get("host"),
                username=ftp_config.get("user"),
                password=ftp_config.get("password"),
                remote_dir=remote_dir_bank,
                port=int(ftp_config.get("port", 21)),
                secure=bool(ftp_config.get("secure", False)),
                timeout=int(ftp_config.get("timeout", 30)),
                passive=bool(ftp_config.get("passive", True))
            )
            if ok_upload:
                logging.info(f"Upload FTP bem-sucedido: {msg} -> remote_dir={remote_dir_bank}")
                # opcional: remover zip local após upload (descomente se quiser)
                # try:
                #     os.remove(zip_path)
                #     logging.info(f"Zip local removido após upload: {zip_path}")
                # except Exception as e:
                #     logging.warning(f"Falha ao remover zip local: {e}")
            else:
                logging.error(f"Falha no upload FTP: {msg} -> attempted remote_dir={remote_dir_bank}")
        except Exception as e:
            logging.exception(f"Exceção ao tentar enviar por FTP: {e}")

    # aplicar política de retenção sobre zips
    prefix_for_keep = f"{name}_"
    remove_old_backups_zip(backup_folder, prefix_for_keep, max_backups)

    return True

def parse_times(times_value):
    parts = [p.strip() for p in times_value.split(",") if p.strip()]
    normalized = []
    for p in parts:
        try:
            datetime.strptime(p, "%H:%M")
            normalized.append(p)
        except ValueError:
            logging.warning(f"Formato de horário inválido ignorado: {p}")
    return normalized

def backup_exists_on_or_after(backup_folder, name, scheduled, today):
    """
    Verifica se já existe backup para `name` no dia `today` com horário igual ou posterior
    ao horário `scheduled` (formato "HH:MM").
    Procura primeiro por .zip (preferência), depois por .fbk (compatibilidade).
    Exige que arquivos sigam o padrão: <name>_YYYYMMDD_HHMMSS.(zip|fbk) ou <name>_YYYYMMDD_HHMM.
    """
    target_date = today.strftime("%Y%m%d")
    sched_time = datetime.strptime(scheduled, "%H:%M").time()

    candidates = []
    # Reunir zips e fbks
    for fn in os.listdir(backup_folder):
        lower = fn.lower()
        if not (lower.endswith(".zip") or lower.endswith(".fbk")):
            continue
        base = os.path.splitext(fn)[0]
        parts = base.rsplit("_", 2)
        if len(parts) < 3:
            continue
        name_part, date_part, time_part = parts
        if date_part != target_date:
            continue
        if name_part != name:
            continue
        # tentar extrair hora do time_part
        try:
            if len(time_part) == 6:
                file_time = datetime.strptime(time_part, "%H%M%S").time()
            elif len(time_part) == 4:
                file_time = datetime.strptime(time_part, "%H%M").time()
            else:
                continue
        except Exception:
            continue
        # coletar candidato (arquivo que esteja >= agendamento)
        if file_time >= sched_time:
            candidates.append((file_time, fn))

    if not candidates:
        return False, None

    # se houver candidatos, escolher o mais próximo (menor horário >= sched_time)
    candidates.sort(key=lambda x: (x[0].hour * 60 + x[0].minute, getattr(x[0], "second", 0)))
    chosen = candidates[0][1]
    return True, os.path.join(backup_folder, chosen)

def main(ini_path):
    config = load_config(ini_path)
    gbak_path_ini = config["DEFAULT"].get("gbak_path", "").strip()
    gbak = find_gbak(gbak_path_ini)

    # Carregar configuração FTP (opcional). Se host vazio => não faz upload.
    ftp_host = config["DEFAULT"].get("ftp_server", "").strip()
    ftp_config = None
    if ftp_host:
        ftp_config = {
            "host": ftp_host,
            "port": int(config["DEFAULT"].get("ftp_port", "21")),
            "user": config["DEFAULT"].get("ftp_user", ""),
            "password": config["DEFAULT"].get("ftp_password", ""),
            "remote_dir": config["DEFAULT"].get("ftp_remote_dir", "."),
            "secure": config["DEFAULT"].getboolean("ftp_secure", False),
            "timeout": int(config["DEFAULT"].get("ftp_timeout", "30")),
            "passive": config["DEFAULT"].getboolean("ftp_passive", True)
        }

    dbs = []
    for section in config.sections():
        cfg = {}
        cfg['name'] = config[section].get("name", section).strip()
        cfg['source'] = config[section].get("source")
        if not cfg['source']:
            logging.warning(f"Seção {section} não tem 'source' definido. Ignorando.")
            continue
        cfg['user'] = config[section].get("user", config["DEFAULT"].get("user", "")).strip()
        cfg['password'] = config[section].get("password", config["DEFAULT"].get("password", "")).strip()
        cfg['max_backups'] = config[section].get("max_backups", config["DEFAULT"].get("max_backups", "7")).strip()
        times_str = config[section].get("times", "")
        cfg['times'] = parse_times(times_str)
        if not cfg['times']:
            logging.warning(f"Nenhum horário válido encontrado para {cfg['name']} (seção {section}). Ignorando.")
            continue
        dbs.append(cfg)

    if not dbs:
        logging.error("Nenhum banco configurado corretamente no INI. Saindo.")
        return

    db_control = {}
    for db in dbs:
        folder = ensure_backup_folder(db['name'])
        db_control[db['name']] = {
            "cfg": db,
            "folder": folder,
            # last_run[HH:MM] = date() quando executado
            "last_run": {t: None for t in db['times']}
        }

    logging.info("Agendador iniciado. Entradas:")
    for name, info in db_control.items():
        logging.info(f" - {name} | source={info['cfg']['source']} | times={','.join(info['cfg']['times'])} | folder={info['folder']}")

    try:
        while True:
            now = datetime.now()
            today = date.today()

            # Para cada banco, verificamos TODOS os horários agendados.
            for name, info in db_control.items():
                cfg = info['cfg']
                # limpar marcações de dias anteriores
                for t, last_date in list(info['last_run'].items()):
                    if last_date and last_date != today:
                        info['last_run'][t] = None

                for scheduled in cfg['times']:
                    # se já foi executado hoje para este horário, pular
                    if info['last_run'].get(scheduled) == today:
                        continue

                    scheduled_time_obj = datetime.strptime(scheduled, "%H:%M").time()
                    scheduled_dt = datetime.combine(today, scheduled_time_obj)

                    # se o horário já passou (ou é exatamente agora), considerar execução
                    if now >= scheduled_dt:
                        # primeiro: verificar nos arquivos se já existe backup para o mesmo dia em horário igual ou posterior
                        exists, existing_path = backup_exists_on_or_after(
                            info['folder'],
                            name,
                            scheduled,
                            today
                        )
                        if exists:
                            logging.info(f"Backup encontrado (>= agendamento) para {name} agendado em {scheduled}: {os.path.basename(existing_path)} — marcando como executado e pulando.")
                            info['last_run'][scheduled] = today
                            continue

                        logging.info(f"Hora de rodar backup para {name} agendado em {scheduled} (agora é {now.strftime('%H:%M:%S')})")
                        success = backup_now(gbak, cfg, info['folder'], ftp_config=ftp_config)
                        if success:
                            info['last_run'][scheduled] = today
                        else:
                            logging.warning(f"Backup para {name} em {scheduled} falhou. Não marcar como executado; tentará novamente se aplicável.")
            time.sleep(CHECK_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logging.info("Encerrando por solicitação do usuário (KeyboardInterrupt).")
    except Exception as e:
        logging.exception(f"Erro crítico no agendador: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python firebird_backup.py caminho_para/backups.ini")
        sys.exit(1)
    ini = sys.argv[1]
    main(ini)
