import requests
import time
import sys
import json

from urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

def measure_throughput(duration_seconds, node_address):
    print(f"{duration_seconds}초 동안 트랜잭션 처리량을 측정합니다...")
    
    # 1. 측정 시작 전 체인 상태
    try:
        response_before = requests.get(f"{node_address}/get_canonical_chain", verify=False, timeout=5)
        if response_before.status_code != 200:
            print("오류: 노드에 연결할 수 없습니다. 노드가 실행 중인지 확인하세요.")
            return
    except requests.exceptions.RequestException as e:
        print(f"오류: 노드 연결 중 예외 발생 - {e}")
        return
        
    chain_before = response_before.json()
    last_block_before = chain_before[-1] if len(chain_before) > 1 else None
    
    start_time = time.time()
    print(f"측정 시작. (시작 블록 인덱스: {last_block_before['index'] if last_block_before else 'N/A'})")

    # 2. 지정된 시간 동안 대기
    time.sleep(duration_seconds)

    # 3. 측정 종료 후 체인 상태 다시 가져오기
    end_time = time.time()
    try:
        response_after = requests.get(f"{node_address}/get_canonical_chain", verify=False, timeout=5)
        if response_after.status_code != 200:
            print("오류: 측정 후 노드 상태를 가져오는 데 실패했습니다.")
            return
    except requests.exceptions.RequestException as e:
        print(f"오류: 노드 연결 중 예외 발생 - {e}")
        return

    chain_after = response_after.json()
    
    # 4. 새로 추가된 블록들에서 트랜잭션 수 계산
    new_blocks = []
    start_index = last_block_before['index'] if last_block_before else 0
    
    for block in chain_after:
        if block['index'] > start_index:
            new_blocks.append(block)

    processed_transactions = set()
    for block in new_blocks:
        for tx in block['transactions']:
            processed_transactions.add(tx)
    
    total_tx_count = len(processed_transactions)
    actual_duration = end_time - start_time
    tps = total_tx_count / actual_duration
    
    print("\n--- 측정 결과 ---")
    print(f"총 측정 시간: {actual_duration:.2f}초")
    print(f"새로 생성된 블록 수: {len(new_blocks)}")
    print(f"처리된 총 트랜잭션 수 (중복 제거): {total_tx_count}")
    print(f"네트워크 실제 처리량 (TPS): {tps:.2f} tx/s")

if __name__ == '__main__':
    duration = 30  # 기본 측정 시간 30초
    if len(sys.argv) > 1:
        try:
            duration = int(sys.argv[1])
        except ValueError:
            print("오류: 측정 시간은 정수여야 합니다. 기본값인 30초를 사용합니다.")
    
    # 부트스트랩 노드를 사용해 테스트
    node_url = "https://127.0.0.1:5001"
    
    measure_throughput(duration, node_url)