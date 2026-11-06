# Backup Nortus

Programa em Python para Windows que faz **backup agendado de bancos Firebird**. Ele valida cada backup restaurando o arquivo, compacta em `.zip`, mantém só os N mais recentes e **envia uma cópia para um servidor FTP/FTPS**. Roda em segundo plano, sem janela, e registra tudo em log.

## Como funciona

A cada 30 segundos, o agendador verifica os horários configurados de cada banco. Quando chega a hora:

```
1. gbak -b    banco ──▶ <nome>_AAAAMMDD_HHMMSS.fbk          (backup)
2. gbak -c    .fbk  ──▶ <nome>_AAAAMMDD_HHMMSS.fdb          (restore de teste: valida o backup)
3. zip        .fdb  ──▶ <nome>_AAAAMMDD_HHMMSS.zip          (o .fbk e o .fdb são apagados)
4. FTP        apaga os zips remotos mais antigos e envia o novo
5. retenção   mantém localmente apenas os `max_backups` zips mais recentes
```

- **Validação real**: o backup só é aceito se o `gbak` conseguir restaurá-lo. Se a restauração falhar, os arquivos inválidos são descartados e o horário é tentado de novo no próximo ciclo.
- **Sem execuções duplicadas**: antes de rodar, ele procura na pasta um backup do mesmo dia com horário igual ou posterior ao agendado. Se o computador estava desligado na hora marcada, o backup roda assim que o serviço voltar.
- **Sincronização com o FTP**: a cada `ftp_sync_interval_minutes`, compara os zips locais com os remotos e reenvia os que faltam (por exemplo, depois de uma queda de internet).
- **Instância única**: um mutex do Windows impede que duas cópias rodem ao mesmo tempo ([winSingleton.py](winSingleton.py)).
- **Log**: grava em `C:\Backups\backup_script.log`. O arquivo é truncado ao passar de 10 MB e o gbak roda sem abrir janela de terminal.

### Estrutura gerada

```
C:\Backups\
├── backup_script.log
├── empresa1\
│   ├── empresa1_20260105_120000.zip
│   └── empresa1_20260105_180000.zip
└── empresa2\
    └── ...

FTP: <ftp_remote_dir>/empresa1/empresa1_20260105_120000.zip
```

## Arquivos

| Arquivo | Função |
|---|---|
| [main.py](main.py) | agendador, backup/restore com `gbak`, zip e retenção local |
| [ftp_transfer.py](ftp_transfer.py) | upload, listagem, exclusão e retenção no FTP/FTPS |
| [utils.py](utils.py) | sincronização dos zips locais que faltam no FTP |
| [crendential_manager.py](crendential_manager.py) | lê as credenciais do FTP das variáveis de ambiente |
| [winSingleton.py](winSingleton.py) | garante uma única instância no Windows |
| [backups.example.ini](backups.example.ini) | modelo da configuração dos bancos e horários |

## Requisitos

- Windows
- Python 3.10+ (só biblioteca padrão, sem dependências externas)
- Firebird instalado com o `gbak` disponível (no `PATH` ou em `gbak_path`)

## Configuração

### Credenciais do FTP (variáveis de ambiente)

| Variável | Conteúdo |
|---|---|
| `NORTUS_FTP_SERVER` | host do servidor FTP. Se ficar vazio, o upload é desativado e o backup fica só local |
| `NORTUS_FTP_USER` | usuário |
| `NORTUS_FTP_PASSWORD` | senha |

Defina-as para o sistema, para que valham também quando o programa roda pelo Agendador de Tarefas. Use um prompt **como administrador**:

```bat
setx /M NORTUS_FTP_SERVER   "ftp.exemplo.com"
setx /M NORTUS_FTP_USER     "usuario"
setx /M NORTUS_FTP_PASSWORD "senha"
```

### Bancos e horários (`backups.ini`)

Copie [backups.example.ini](backups.example.ini) para `backups.ini` e ajuste. O `backups.ini` real está no `.gitignore`, porque contém a senha do Firebird e os caminhos dos bancos.

A seção `[DEFAULT]` define os valores gerais. Cada outra seção representa um banco e pode sobrescrever `user`, `password` e `max_backups`.

```ini
[DEFAULT]
# vazio = usa o gbak do PATH
gbak_path =
user = SYSDBA
password = <senha-do-firebird>
max_backups = 7
ftp_sync_interval_minutes = 60

ftp_port = 21
ftp_remote_dir = /backups
# True = FTPS (TLS explícito)
ftp_secure = True
ftp_timeout = 30
ftp_passive = True

[banco1]
# nome da pasta e prefixo dos arquivos
name = empresa1
source = localhost:C:\Dados\empresa1.fdb
max_backups = 4
# horários diários (HH:MM, 24h)
times = 08:00,12:00,18:00

[banco2]
name = empresa2
source = 192.168.0.20:C:\Dados\empresa2.gdb
times = 22:00
```

> Comentários precisam ficar em linha própria. O `configparser` não aceita comentário depois do valor na mesma linha.

## Como rodar

```bash
python main.py backups.ini
```

Não aparece nada no console. Acompanhe pelo arquivo `C:\Backups\backup_script.log`.

### Gerar o executável

```bash
pip install pyinstaller
pyinstaller --onefile --noconsole --name nortus_backup main.py
```

Copie `dist\nortus_backup.exe` e o `backups.ini` para a máquina do servidor e configure o **Agendador de Tarefas do Windows** para executar na inicialização:

```
Programa:   C:\NortusBackup\nortus_backup.exe
Argumentos: C:\NortusBackup\backups.ini
```

## Segurança

- Use **`ftp_secure = True`** sempre que o servidor aceitar. Com FTP simples, a senha e os arquivos de backup (que contêm o banco inteiro do cliente) trafegam sem criptografia.
- Nunca coloque credenciais no código nem no `backups.ini` versionado. O FTP usa variáveis de ambiente, e o `backups.ini` real fica fora do git.
- Troque a senha padrão `masterkey` do `SYSDBA` nos servidores Firebird.
