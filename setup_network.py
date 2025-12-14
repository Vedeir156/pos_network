import requests
import time
import sys
import pos_config
from blockchain_utils import serialize_public_key

def sync_all_public_keys():
    print("\n[공개키 교환 시작]")
    print("모든 노드가 시작될 때까지 대기 중...")
    
    all_keys = {}
    while len(all_keys) < pos_config.NUM_NODES:
        try:
            response = requests.get("http://127.0.0.1:5001/get_public_keys_from_node")
            if response.status_code == 200:
                all_keys = response.json()
            else:
                all_keys = {}
        except requests.exceptions.RequestException:
            all_keys = {}
        time.sleep(1)
    
    print("\n[전파] 모든 노드에게 전체 공개키 목록을 전송합니다...")
    for i in range(pos_config.NUM_NODES):
        node_address = f"http://127.0.0.1:{5001 + i}"
        try:
            requests.post(f"{node_address}/register_public_key", json=all_keys)
        except requests.exceptions.RequestException as e:
            print(f"Warning: Failed to sync keys for node_{i}: {e}")
            
    print("[공개키 교환 완료]")


if __name__ == '__main__':
    sync_all_public_keys()