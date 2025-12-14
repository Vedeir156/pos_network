# --- 1. 이전 컨테이너 및 네트워크 정리 ---
echo "Cleaning up old docker containers and networks..."
docker stop $(docker ps -aq) > /dev/null 2>&1
docker rm $(docker ps -aq) > /dev/null 2>&1
docker network rm blockchain-net > /dev/null 2>&1
echo "Cleanup complete."
echo ""

# --- 2. 도커 이미지 빌드 ---
echo "Building blockchain-node docker image..."
docker build -t blockchain-node .
echo ""


# --- 3. 도커 가상 네트워크 생성 ---
echo "Creating virtual network 'blockchain-net'..."
docker network create blockchain-net
echo ""


# --- 4. 부트스트랩 노드(node_0) 실행 ---
BOOTSTRAP_PORT=5001
echo "Starting Bootstrap Node (node_0) on port $BOOTSTRAP_PORT..."
docker run -d --name node_0 --network blockchain-net -p 5001:5001 blockchain-node python3 node.py $BOOTSTRAP_PORT

echo "Waiting for Bootstrap Node to be active..."
while ! curl -s "https://localhost:$BOOTSTRAP_PORT/get_chain" --insecure > /dev/null; do
  sleep 1
done
echo "Bootstrap Node is active."
echo ""


# --- 5. 나머지 노드들 실행 ---
echo "Starting nodes in parallel..."
for i in $(seq 1 9); do
  port=$((5001 + i))
  node_name="node_$i"
  docker run -d --name $node_name --network blockchain-net -p ${port}:${port} blockchain-node python3 node.py $port
  echo "Node $i (port: $port) has been launched in a container."
done
echo ""

echo "All nodes are running in docker containers."
echo "You can view logs with: docker logs -f [container_name] (e.g., docker logs -f node_0)"
echo "To stop all containers, run: docker stop \$(docker ps -aq)"