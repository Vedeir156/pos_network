import time

# 노드 수
NUM_NODES = 10
# 전체 지분
TOTAL_STAKE = 1000

# 지분 데이터와 공개키
STAKES = {}
PUBLIC_KEYS = {}

# <<< --- 시간 관련 상수 --- >>>
SECONDS_PER_SLOT = 10
SLOTS_PER_EPOCH = 10

# <<< --- GENESIS_TIME --- >>>
GENESIS_TIME = time.time() + 15