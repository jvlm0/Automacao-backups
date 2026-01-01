import json
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.backends import default_backend
import base64



encrypted = {'salt': 'REMOVIDO', 
                       'nonce': 'REMOVIDO', 
                       'ciphertext': 'REMOVIDO'} 



def derive_key(password: str, salt: bytes) -> bytes:
    kdf = Scrypt(
        salt=salt,
        length=32,          # 32 bytes = 256 bits
        n=2**14,
        r=8,
        p=1,
        backend=default_backend()
    )
    return kdf.derive(password.encode())

def decrypt_dict(encrypted_data: dict, password: str) -> dict:
    salt = base64.b64decode(encrypted_data["salt"])
    nonce = base64.b64decode(encrypted_data["nonce"])
    ciphertext = base64.b64decode(encrypted_data["ciphertext"])

    key = derive_key(password, salt)
    aesgcm = AESGCM(key)

    plaintext = aesgcm.decrypt(nonce, ciphertext, None)

    return json.loads(plaintext.decode())

master_password = "SENHA_MESTRE_REMOVIDA"


def get_decrypted_credential_manager() -> dict:
    """
    Descriptografa o dicionário de credenciais criptografadas usando a senha mestre fornecida.
    
    :param encrypted_cred_manager: Dicionário contendo as credenciais criptografadas.
    :param master_password: Senha mestre para descriptografia.
    :return: Dicionário com as credenciais descriptografadas.
    """
    return decrypt_dict(encrypted, master_password)