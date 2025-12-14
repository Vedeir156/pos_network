import hashlib
import json
import random
import os

from cryptography.hazmat.primitives.asymmetric import ec, padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.exceptions import InvalidSignature

from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def calculate_hash(data):
    if not isinstance(data, (str, bytes)):
        data = json.dumps(data, sort_keys=True)
    
    if isinstance(data, str):
        data = data.encode('utf-8')
        
    return hashlib.sha256(data).hexdigest()

# <<< --- 1. 키 생성 --- >>>
def generate_key_pair():
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    return private_key, public_key

def serialize_public_key(public_key):
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

def deserialize_public_key(serialized_public_key):
    return serialization.load_pem_public_key(serialized_public_key)

# <<< --- 2. 암호화/복호화 --- >>>

def encrypt_data(public_key, data):
    ephemeral_private_key = ec.generate_private_key(ec.SECP256R1())
    ephemeral_public_key = ephemeral_private_key.public_key()
    
    shared_key = ephemeral_private_key.exchange(ec.ECDH(), public_key)
    
    derived_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b'handshake data',
    ).derive(shared_key)
    
    aesgcm = AESGCM(derived_key)
    nonce = os.urandom(12)
    data_to_encrypt = data.encode('utf-8')
    ciphertext = aesgcm.encrypt(nonce, data_to_encrypt, None)
    
    ephemeral_public_key_bytes = ephemeral_public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.CompressedPoint
    )
    return ephemeral_public_key_bytes + nonce + ciphertext

def decrypt_data(private_key, encrypted_data):
    ephemeral_public_key_bytes = encrypted_data[:33]
    nonce = encrypted_data[33:45]
    ciphertext = encrypted_data[45:]
    
    ephemeral_public_key = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), ephemeral_public_key_bytes
    )
    
    shared_key = private_key.exchange(ec.ECDH(), ephemeral_public_key)
    
    derived_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b'handshake data',
    ).derive(shared_key)
    
    aesgcm = AESGCM(derived_key)
    decrypted_data = aesgcm.decrypt(nonce, ciphertext, None)
    return decrypted_data.decode('utf-8')

# <<< --- 3. 서명/검증 --- >>>
def sign_data(private_key, data):
    return private_key.sign(
        data,
        ec.ECDSA(hashes.SHA256())
    )

def verify_signature(public_key, data, signature):
    try:
        public_key.verify(
            signature,
            data,
            ec.ECDSA(hashes.SHA256())
        )
        return True
    except InvalidSignature:
        return False

def pos_select_validator(seed, candidates):
    local_random = random.Random(seed)
    return local_random.choice(candidates)