from flask import Flask, jsonify, request
import json
import requests
import uuid
import sys
import threading
import time
import os
import random
from concurrent.futures import ThreadPoolExecutor
import hashlib

from blockchain import Blockchain, Block
import pos_config
from blockchain_utils import *
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
import datetime

from urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

app = Flask(__name__)

private_key, public_key = generate_key_pair()
serialized_public_key = serialize_public_key(public_key).decode('utf-8')
blockchain = Blockchain()

PEERS = {}
attestations = {}

executor = ThreadPoolExecutor(max_workers=20)
GENESIS_TIME = 0.0
last_processed_slot = -1

def get_validator_for_slot(slot):
    current_epoch = slot // pos_config.SLOTS_PER_EPOCH
    seed = hashlib.sha256(str(current_epoch).encode()).digest()
    with blockchain.lock:
        validators = sorted(list(pos_config.PUBLIC_KEYS.keys()))
    if not validators: return None
    random.Random(seed).shuffle(validators)
    validator_index = slot % len(validators)
    return validators[validator_index]

def get_head():
    root = blockchain.chain[0]
    weights = {block.hash: 0 for block in blockchain.chain}
    
    latest_attestations = {}
    sorted_slots = sorted(attestations.keys(), reverse=True)
    for slot in sorted_slots:
        for validator, block_hash in attestations[slot].items():
            if validator not in latest_attestations:
                latest_attestations[validator] = block_hash
    
    for validator, block_hash in latest_attestations.items():
        stake = pos_config.STAKES.get(validator, 0)
        curr_hash = block_hash
        while True:
            if curr_hash in weights:
                weights[curr_hash] += stake
            block = blockchain.get_block_by_hash(curr_hash)
            if not block or block.hash == root.hash:
                break
            curr_hash = block.previous_hash

    head_hash = root.hash
    while True:
        children = blockchain.get_children(head_hash)
        if not children:
            break
        head_hash = max(children, key=lambda b: weights.get(b.hash, 0)).hash
        
    return blockchain.get_block_by_hash(head_hash)

def broadcast_gossip(payload, exclude_self=True):
    with blockchain.lock:
        peers_copy = dict(PEERS)
    my_address = peers_copy.get(node_name)
    for peer_address in peers_copy.values():
        if exclude_self and my_address == peer_address:
            continue
        try:
            executor.submit(requests.post, f"{peer_address}/gossip", json=payload, verify=False, timeout=1)
        except requests.exceptions.RequestException:
            pass

def main_loop():
    global last_processed_slot
    print(f"\n[{node_name}] GENESIS TIME 도달! 메인 루프를 시작합니다.")
    while True:
        current_time = time.time()
        time_since_genesis = current_time - GENESIS_TIME
        current_slot = int(time_since_genesis // pos_config.SECONDS_PER_SLOT)

        if current_slot > last_processed_slot:
            last_processed_slot = current_slot
            print(f"\n--- [{node_name}] 슬롯 #{current_slot} 시작 ---")

            head_block = get_head()
            if head_block and current_slot > 0:
                attestation_data = {'slot': current_slot - 1, 'block_hash': head_block.hash, 'validator': node_name}
                signature = sign_data(private_key, json.dumps(attestation_data, sort_keys=True).encode())
                gossip_payload = {'type': 'attestation', 'data': attestation_data, 'signature': signature.hex()}
                broadcast_gossip(gossip_payload)
                print(f"[{node_name}] 증명: 슬롯 #{current_slot - 1}의 헤드({head_block.hash[:8]}...)에 투표.")

            validator = get_validator_for_slot(current_slot)
            print(f"[{node_name}] 정보: 슬롯 #{current_slot}의 검증자: {validator}")
            
            if validator == node_name:
                    print(f"[{node_name}] 블록 생성을 시도합니다.")
                    
                    start_creation_time = time.time()
                    
                    parent_block = get_head()
                    
                    with blockchain.lock:
                        new_block = blockchain.create_block_candidate(parent_block, node_name, current_slot)
                        blockchain.chain.append(new_block)
                    
                    gossip_payload = {'type': 'block', 'data': new_block.to_dict()}
                    broadcast_gossip(gossip_payload)

                    end_creation_time = time.time()
                    duration = end_creation_time - start_creation_time
                    
                    print(f"[{node_name}] 블록 제안: 블록 #{new_block.index} (TXs: {len(new_block.transactions)}) 전파 완료 (소요 시간: {duration:.2f}초)")

        next_slot_time = GENESIS_TIME + (current_slot + 1) * pos_config.SECONDS_PER_SLOT
        sleep_duration = next_slot_time - time.time()
        if sleep_duration > 0:
            time.sleep(sleep_duration)

# --- API 엔드포인트 ---
@app.route('/gossip', methods=['POST'])
def gossip():
    payload = request.get_json()
    gossip_type = payload.get('type')
    data = payload.get('data')

    if gossip_type == 'block':
        new_block = Block.from_dict(data)
        with blockchain.lock:
            if not blockchain.get_block_by_hash(new_block.hash) and blockchain.get_block_by_hash(new_block.previous_hash):
                blockchain.chain.append(new_block)
                print(f"\n[{node_name}] 블록 수신: 블록 #{new_block.index} 수신.")
                
                for tx in new_block.transactions:
                    tx_hash = hashlib.sha256(tx.encode()).hexdigest()
                    blockchain.committed_transactions.add(tx_hash)
                    if tx in blockchain.pending_transactions:
                        blockchain.pending_transactions.remove(tx)
                        
        return jsonify({'message': 'Block received'}), 200

    elif gossip_type == 'attestation':
        validator = data.get('validator')
        with blockchain.lock:
            public_key_obj = pos_config.PUBLIC_KEYS.get(validator)
        if not public_key_obj: return jsonify({'message': 'Validator not found'}), 400
        try:
            is_valid = verify_signature(public_key_obj, json.dumps(data, sort_keys=True).encode(), bytes.fromhex(payload.get('signature')))
            if not is_valid: return jsonify({'message': 'Invalid attestation signature'}), 400
        except (ValueError, InvalidSignature):
            return jsonify({'message': 'Invalid signature format or value.'}), 400
        slot = data.get('slot')
        with blockchain.lock:
            if slot not in attestations: attestations[slot] = {}
            if validator not in attestations[slot]:
                attestations[slot][validator] = data.get('block_hash')
                print(f"\n[{node_name}] 증명 수신: {validator}로부터 슬롯 #{slot} 증명 수신.")
        return jsonify({'message': 'Attestation received'}), 200

    elif gossip_type == 'transaction':
        with blockchain.lock:
            tx_hash = hashlib.sha256(data.encode()).hexdigest()
            if tx_hash not in blockchain.committed_transactions and data not in blockchain.pending_transactions:
                blockchain.add_transaction(data)
                print(f"\n[{node_name}] 트랜잭션 수신: {data[:40]}...")
        return jsonify({'message': 'Transaction gossiped'}), 200
    
    elif gossip_type == 'new_peer':
        name, address, key_pem = data.get('name'), data.get('address'), data.get('public_key')
        with blockchain.lock:
            if name not in PEERS:
                PEERS[name] = address
                pos_config.PUBLIC_KEYS[name] = deserialize_public_key(key_pem.encode('utf-8'))
                print(f"\n[{node_name}] 새로운 피어 발견: {name}. 현재 {len(PEERS)}명.")
        return jsonify({'message': 'Peer info received'}), 200

    return jsonify({'message': 'Invalid gossip type'}), 400

@app.route('/add_transaction', methods=['POST'])
def add_transaction():
    values = request.get_json()
    if 'transaction_data' in values:
        tx_data = values['transaction_data']
        with blockchain.lock:
            blockchain.add_transaction(tx_data)
        print(f"\n[{node_name}] 외부 트랜잭션 수신: {tx_data[:40]}...")
        broadcast_gossip({'type': 'transaction', 'data': tx_data})
        return jsonify({'message': 'Transaction added and gossiped.'}), 201
    return jsonify({'message': 'Invalid transaction payload.'}), 400

@app.route('/get_network_state', methods=['GET'])
def get_network_state():
    with blockchain.lock:
        return jsonify({
            'peers': PEERS,
            'public_keys': {name: serialize_public_key(key).decode('utf-8') for name, key in pos_config.PUBLIC_KEYS.items()},
            'stakes': pos_config.STAKES
        }), 200

@app.route('/get_chain', methods=['GET'])
def get_chain():
    with blockchain.lock:
        return jsonify([b.to_dict() for b in blockchain.chain]), 200

@app.route('/get_canonical_chain', methods=['GET'])
def get_canonical_chain():
    with blockchain.lock:
        head_block = get_head()
        if not head_block:
            return jsonify({'message': 'Chain head not found.'}), 404
        canonical_chain = []
        current_block = head_block
        while current_block:
            canonical_chain.append(current_block.to_dict())
            if current_block.previous_hash == '1':
                break
            current_block = blockchain.get_block_by_hash(current_block.previous_hash)
        canonical_chain.reverse()
        return jsonify(canonical_chain), 200

def generate_initial_stakes_centralized(total_stake, num_nodes):
    stakes = {f"node_{i}": 1 for i in range(num_nodes)}
    remaining = total_stake - num_nodes
    for _ in range(remaining):
        stakes[f"node_{random.randint(0, num_nodes - 1)}"] += 1
    return dict(sorted(stakes.items()))

def bootstrap_network():
    global GENESIS_TIME
    GENESIS_TIME = pos_config.GENESIS_TIME

    if node_name == 'node_0':
        print(f"[{node_name}] 부트스트랩 노드로 실행됩니다. 모든 피어({pos_config.NUM_NODES}개)가 등록될 때까지 기다립니다.")
        with blockchain.lock:
            pos_config.STAKES = generate_initial_stakes_centralized(pos_config.TOTAL_STAKE, pos_config.NUM_NODES)
        while True:
            with blockchain.lock:
                peer_count = len(PEERS)
            if peer_count < pos_config.NUM_NODES:
                print(f"[{node_name}] 현재 {peer_count}/{pos_config.NUM_NODES} 노드 발견. 대기 중...")
                time.sleep(1)
            else:
                break
    
    else:
        bootstrap_node_url = "https://node_0:5001" # 포트번호에 맞게 변경
        is_synced = False
        while not is_synced:
            try:
                print(f"[{node_name}] 부트스트랩 노드({bootstrap_node_url})에 접속하여 네트워크 정보 요청 중...")
                response = requests.get(f"{bootstrap_node_url}/get_network_state", verify=False, timeout=2)
                if response.status_code == 200:
                    data = response.json()
                    with blockchain.lock:
                        PEERS.update(data['peers'])
                        for name, key_pem in data['public_keys'].items():
                            if name not in pos_config.PUBLIC_KEYS:
                                pos_config.PUBLIC_KEYS[name] = deserialize_public_key(key_pem.encode('utf-8'))
                        pos_config.STAKES.update(data['stakes'])
                    print(f"[{node_name}] 부트스트랩 완료. 현재 {len(PEERS)}명의 피어 정보를 수신했습니다.")
                    my_info_payload = {'type': 'new_peer', 'data': {'name': node_name, 'address': node_address, 'public_key': serialized_public_key}}
                    broadcast_gossip(my_info_payload, exclude_self=True)
                    is_synced = True
                else:
                    time.sleep(2)
            except requests.exceptions.RequestException:
                print(f"[{node_name}] 부트스트랩 노드 연결 실패. 2초 후 재시도...")
                time.sleep(2)
        
        print(f"[{node_name}] 네트워크 동기화 완료. 전체 피어 목록 수신을 기다립니다...")
        while True:
            with blockchain.lock:
                peer_count = len(PEERS)
            if peer_count < pos_config.NUM_NODES:
                print(f"[{node_name}] 현재 {peer_count}/{pos_config.NUM_NODES} 노드 발견. 대기 중...")
                time.sleep(1)
            else:
                break
    
    print(f"[{node_name}] 모든 노드({len(PEERS)}개)의 등록을 확인했습니다. 네트워크가 형성되었습니다.")
    main_loop()

if __name__ == '__main__':
    port = int(sys.argv[1])
    node_name = f"node_{port - 5001}"
    node_address = f"https://{node_name}:{port}"
    
    CERT_DIR, CERT_PATH, KEY_PATH = "certs", f"certs/{node_name}.crt", f"certs/{node_name}.key"
    os.makedirs(CERT_DIR, exist_ok=True)
    if not os.path.exists(CERT_PATH):
        private_key_pem = private_key.private_bytes(encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.TraditionalOpenSSL, encryption_algorithm=serialization.NoEncryption())
        with open(KEY_PATH, "wb") as f: f.write(private_key_pem)
        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"node_{port}")])
        cert = x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(public_key).serial_number(x509.random_serial_number()).not_valid_before(datetime.datetime.now(datetime.timezone.utc)).not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365)).sign(private_key, hashes.SHA256())
        with open(CERT_PATH, "wb") as f: f.write(cert.public_bytes(serialization.Encoding.PEM))

    with blockchain.lock:
        PEERS[node_name] = node_address
        pos_config.PUBLIC_KEYS[node_name] = public_key

    threading.Thread(target=bootstrap_network, daemon=True).start()
    
    print(f"노드 {node_name}이(가) {node_address} 에서 실행됩니다.")
    app.run(host='0.0.0.0', port=port, debug=False, ssl_context=(CERT_PATH, KEY_PATH), use_reloader=False)