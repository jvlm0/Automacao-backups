import os
import sys

def ensure_single_instance(mutex_name: str):
    if os.name != "nt":
        return None  # não aplica em Linux/Mac (use lockfile lá)
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    CreateMutexW = kernel32.CreateMutexW
    CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    CreateMutexW.restype = wintypes.HANDLE

    handle = CreateMutexW(None, False, mutex_name)
    if not handle:
        err = ctypes.get_last_error()
        raise OSError(f"CreateMutexW falhou: {err}")
    ERROR_ALREADY_EXISTS = 183
    last = kernel32.GetLastError()
    if last == ERROR_ALREADY_EXISTS:
        # já existe instância
        return None  # sinaliza que já está rodando
    return handle

def release_single_instance(handle):
    if handle and os.name == "nt":
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.ReleaseMutex(handle)
        kernel32.CloseHandle(handle)


def ensureSingleton():
    # usar assim no main:
    MUTEX_HANDLE = None
    mutex_name = "Global\\FirebirdBackup_Mutex_v1"  # nome único no sistema
    MUTEX_HANDLE = ensure_single_instance(mutex_name)
    if MUTEX_HANDLE is None:
        # já existe instância — sair silenciosamente
        print("Outra instância já está em execução. Saindo.")
        sys.exit(0)