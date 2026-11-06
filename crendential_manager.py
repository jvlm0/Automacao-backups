"""
Credenciais do FTP.

Lidas de variáveis de ambiente para não ficarem no código-fonte nem no executável:

    NORTUS_FTP_SERVER    host do servidor FTP (vazio = upload desativado)
    NORTUS_FTP_USER      usuário
    NORTUS_FTP_PASSWORD  senha

No Windows, defina-as para o sistema (vale para o Agendador de Tarefas) com:

    setx /M NORTUS_FTP_SERVER   "ftp.exemplo.com"
    setx /M NORTUS_FTP_USER     "usuario"
    setx /M NORTUS_FTP_PASSWORD "senha"
"""
import os


def get_ftp_credentials() -> dict:
    """Retorna {'ftp_server', 'ftp_user', 'ftp_password'} a partir do ambiente."""
    return {
        "ftp_server": os.environ.get("NORTUS_FTP_SERVER", "").strip(),
        "ftp_user": os.environ.get("NORTUS_FTP_USER", "").strip(),
        "ftp_password": os.environ.get("NORTUS_FTP_PASSWORD", ""),
    }
