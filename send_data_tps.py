import sys
import requests
import time
import pos_config
import random
import uuid
import threading
from urllib.parse import urlparse

from urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)


def get_network_state_from_bootstrap_node():
    peers = {}
    bootstrap_node_url = 'https://127.0.0.1:5001/get_network_state'
    max_retries = 10
    retry_delay = 2

    for attempt in range(max_retries):
        print(f"부트스트랩 노드에서 네트워크 정보를 가져옵니다... (시도 {attempt + 1}/{max_retries})")
        try:
            response = requests.get(bootstrap_node_url, verify=False, timeout=2)
            if response.status_code == 200:
                network_state = response.json()
                peer_info = network_state.get('peers', {})
                
                if len(peer_info) == pos_config.NUM_NODES:
                    print(f"{len(peer_info)}개의 노드 정보를 확보했습니다.")
                    return peer_info
                else:
                    print(f"모든 노드({len(peer_info)}/{pos_config.NUM_NODES})가 네트워크에 참여하지 않았습니다.")

        except requests.exceptions.RequestException as e:
            print(f"부트스트랩 노드({bootstrap_node_url}) 연결에 실패했습니다: {e}")
        
        time.sleep(retry_delay)
            
    return peers

def send_transaction_to_peer(peer_address, payload):
    try:
        response = requests.post(peer_address, json=payload, verify=False, timeout=30)
        if response.status_code != 201:
            print(f"[{time.strftime('%H:%M:%S', time.localtime())}] ❗️ {peer_address}로 전송 실패, 상태 코드: {response.status_code}, 메시지: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"[{time.strftime('%H:%M:%S', time.localtime())}] ❗️ {peer_address}로 전송 중 예외 발생: {e}")

def send_data_in_burst(rate=2):
    interval = 1.0 / rate
    
    peers = get_network_state_from_bootstrap_node()
    
    if not peers:
        print("오류: 네트워크 정보를 가져오는 데 실패했습니다. 노드가 실행 중인지 확인하세요.")
        return
        
    accessible_peers = {}
    for name, address in peers.items():
        parsed_url = urlparse(address)
        new_address = f"https://127.0.0.1:{parsed_url.port}"
        accessible_peers[name] = new_address

    print(f"초당 {rate}건의 트랜잭션을 {len(accessible_peers)}개의 노드에 분산하여 전파합니다...")
    
    try:
        while True:
            random_data_message = f"Random Data: {uuid.uuid4()} @ {time.time()}"
            
            peer_name_to_send = random.choice(list(accessible_peers.keys()))
            peer_address = accessible_peers[peer_name_to_send]
            
            payload = {'transaction_data': random_data_message}
            
            thread = threading.Thread(target=send_transaction_to_peer, args=(f"{peer_address}/add_transaction", payload))
            thread.start()
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\n데이터 전송을 중단합니다.")
    
if __name__ == '__main__':
    rate = 2
    if len(sys.argv) > 1:
        try:
            rate = int(sys.argv[1])
        except ValueError:
            print("오류: TPS 값은 정수여야 합니다. 기본값인 2를 사용합니다.")
            
    print(f"블록체인 노드들에게 데이터를 자동으로 전송하는 스크립트를 시작합니다. (TPS: {rate})")
    send_data_in_burst(rate)

