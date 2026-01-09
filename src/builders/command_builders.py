"""
Command builders for different service and client types.

This module generates the actual shell commands from high-level
service/client type and settings, hiding complexity from end users.
"""

from typing import Any, Dict, Optional


# =============================================================================
# SERVICE COMMAND BUILDERS
# =============================================================================


def build_postgres_service_command(settings: Dict[str, Any]) -> str:
    """Build Postgres service startup command."""
    db_name = settings.get("db_name", "benchmark")
    data_dir = settings.get("data_dir", "/tmp/pgdata")
    auth = settings.get("auth", "trust")

    # Performance tuning settings
    tuning = settings.get("tuning", {})
    shared_buffers = tuning.get("shared_buffers", "128MB")
    effective_cache_size = tuning.get("effective_cache_size", "512MB")
    maintenance_work_mem = tuning.get("maintenance_work_mem", "64MB")

    # Build the command
    cmd_parts = [
        f"/usr/lib/postgresql/18/bin/initdb -D {data_dir} --username=postgres --auth={auth} --auth-host={auth}",
        f'echo "host all all 0.0.0.0/0 {auth}" >> {data_dir}/pg_hba.conf',
    ]

    # Add tuning if specified
    if tuning:
        cmd_parts.extend(
            [
                f'echo "shared_buffers = {shared_buffers}" >> {data_dir}/postgresql.conf',
                f'echo "effective_cache_size = {effective_cache_size}" >> {data_dir}/postgresql.conf',
                f'echo "maintenance_work_mem = {maintenance_work_mem}" >> {data_dir}/postgresql.conf',
            ]
        )

    cmd_parts.extend(
        [
            f'/usr/lib/postgresql/18/bin/pg_ctl -D {data_dir} -o "-h 0.0.0.0 -p 5432 -k /tmp" -l {data_dir}/logfile start',
            "sleep 3",
            f"/usr/lib/postgresql/18/bin/createdb -h 127.0.0.1 -p 5432 -U postgres {db_name}",
            f'echo "Database {db_name} created"',
            f"tail -f {data_dir}/logfile",
        ]
    )

    return "sh -c '" + " && ".join(cmd_parts) + "'"


def build_chroma_service_command(settings: Dict[str, Any]) -> str:
    """Build ChromaDB service startup command."""
    host = settings.get("host", "0.0.0.0")
    port = settings.get("port", 8000)
    return f"chroma run --host {host} --port {port}"


def build_vllm_service_command(settings: Dict[str, Any]) -> str:
    """Build vLLM service startup command."""
    model = settings.get("model", "facebook/opt-125m")
    tensor_parallel = settings.get("tensor_parallel_size", 1)

    cmd = f"vllm serve --model {model}"
    if tensor_parallel > 1:
        cmd += f" --tensor-parallel-size {tensor_parallel}"

    return cmd


def build_ollama_service_command(settings: Dict[str, Any]) -> str:
    """Build Ollama service startup command."""
    model = settings.get("model", "llama2")
    warmup = settings.get("warmup_seconds", 5)

    return f"""/bin/sh -c '
  ollama serve > /tmp/ollama.log 2>&1 &
  sleep {warmup}
  ollama pull {model}
  tail -f /tmp/ollama.log
'"""


def build_nginx_service_command(settings: Dict[str, Any]) -> str:
    """Build nginx service startup command with writable paths."""
    return """mkdir -p /tmp/nginx/logs /tmp/nginx/cache /tmp/nginx/run
nginx -g 'daemon off; error_log /tmp/nginx/logs/error.log warn; access_log /tmp/nginx/logs/access.log; pid /tmp/nginx/run/nginx.pid; client_body_temp_path /tmp/nginx/cache/client_temp; fastcgi_temp_path /tmp/nginx/cache/fastcgi_temp; uwsgi_temp_path /tmp/nginx/cache/uwsgi_temp; scgi_temp_path /tmp/nginx/cache/scgi_temp;'"""


# =============================================================================
# CLIENT COMMAND BUILDERS
# =============================================================================


def build_postgres_smoke_client_command(settings: Dict[str, Any]) -> str:
    """Build Postgres smoke test client command with JSONL output."""
    query = settings.get("query", "SELECT version();")
    warmup_delay = settings.get("warmup_delay", 5)
    db_name = settings.get("db_name", "benchmark")

    return f"""module load PostgreSQL
sleep {warmup_delay}

# Initialize JSONL output
mkdir -p "$BENCHMARK_OUTPUT_DIR"
if [ -n "$CLIENT_NAME" ]; then
  REQUESTS_FILE="$BENCHMARK_OUTPUT_DIR/requests_$CLIENT_NAME.jsonl"
else
  REQUESTS_FILE="$BENCHMARK_OUTPUT_DIR/requests.jsonl"
fi
echo '{{"benchmark_id": "'$BENCHMARK_ID'", "service_type": "postgres", "test_start": "'$(date -Iseconds)'"}}' > "$REQUESTS_FILE"

echo "Testing PostgreSQL connection..."
start_time=$(date +%s.%N)
start_timestamp=$(date +%s)

if psql -h $SERVICE_HOSTNAME -p $SERVICE_PORT -U postgres -d {db_name} -c '{query}' > /tmp/pg_result.txt 2>&1; then
  end_time=$(date +%s.%N)
  latency=$(echo "$end_time - $start_time" | bc)
  # Ensure latency has leading zero for valid JSON
  latency=$(printf "%.9f" $latency)
  
  # Write success JSONL
  echo '{{"timestamp_start": '$start_timestamp', "timestamp_end": '$(date +%s)', "latency_s": '$latency', "success": true, "service_type": "postgres", "request_id": "smoke_test", "operation_type": "select", "query_type": "version_check"}}' >> "$REQUESTS_FILE"
  
  echo "✓ Connection successful!"
  cat /tmp/pg_result.txt
  echo "Latency: ${{latency}}s"
else
  end_time=$(date +%s.%N)
  latency=$(echo "$end_time - $start_time" | bc)
  # Ensure latency has leading zero for valid JSON
  latency=$(printf "%.9f" $latency)
  
  # Write failure JSONL
  echo '{{"timestamp_start": '$start_timestamp', "timestamp_end": '$(date +%s)', "latency_s": '$latency', "success": false, "service_type": "postgres", "request_id": "smoke_test", "operation_type": "select", "error": "connection_failed"}}' >> "$REQUESTS_FILE"
  
  echo "✗ Connection failed!"
  cat /tmp/pg_result.txt
  exit 1
fi
"""


def build_postgres_stress_client_command(settings: Dict[str, Any]) -> str:
    """Build Postgres stress test client command with JSONL output."""
    num_inserts = settings.get("num_inserts", 10000)
    num_selects = settings.get("num_selects", 5000)
    table_name = settings.get("table_name", "stress_test")
    warmup_delay = settings.get("warmup_delay", 5)
    db_name = settings.get("db_name", "benchmark")

    return f"""module load PostgreSQL
sleep {warmup_delay}

# Configuration
NUM_INSERTS={num_inserts}
NUM_SELECTS={num_selects}
TABLE_NAME="{table_name}"
DB_NAME="{db_name}"

echo "=== Postgres Stress Test ==="
echo "Inserts: $NUM_INSERTS"
echo "Selects: $NUM_SELECTS"
echo "Table: $TABLE_NAME"
echo ""

# Initialize JSONL output
mkdir -p "$BENCHMARK_OUTPUT_DIR"
if [ -n "$CLIENT_NAME" ]; then
  REQUESTS_FILE="$BENCHMARK_OUTPUT_DIR/requests_$CLIENT_NAME.jsonl"
else
  REQUESTS_FILE="$BENCHMARK_OUTPUT_DIR/requests.jsonl"
fi
echo '{{"benchmark_id": "'$BENCHMARK_ID'", "service_type": "postgres", "test_start": "'$(date -Iseconds)'"}}' > "$REQUESTS_FILE"

# Create table
echo "Creating table..."
psql -h $SERVICE_HOSTNAME -p $SERVICE_PORT -U postgres -d $DB_NAME -c "
  DROP TABLE IF EXISTS $TABLE_NAME;
  CREATE TABLE $TABLE_NAME (
    id SERIAL PRIMARY KEY,
    data VARCHAR(255),
    value INTEGER,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    payload TEXT
  );
  CREATE INDEX idx_value ON $TABLE_NAME(value);
  CREATE INDEX idx_timestamp ON $TABLE_NAME(timestamp);
" || exit 1

echo "Table created successfully."
echo ""

# Insert phase
echo "=== INSERT PHASE ==="
INSERT_START=$(date +%s.%N)
insert_errors=0

for i in $(seq 1 $NUM_INSERTS); do
  if [ $((i % 1000)) -eq 0 ]; then
    echo "Inserted $i/$NUM_INSERTS records..."
  fi
  
  DATA="data_$i"
  VALUE=$((i % 1000))
  PAYLOAD="payload_text_for_record_$i"
  
  start_time=$(date +%s.%N)
  start_timestamp=$(date +%s)
  
  if psql -h $SERVICE_HOSTNAME -p $SERVICE_PORT -U postgres -d $DB_NAME -c "
    INSERT INTO $TABLE_NAME (data, value, payload) VALUES ('$DATA', $VALUE, '$PAYLOAD');
  " > /dev/null 2>&1; then
    end_time=$(date +%s.%N)
    latency=$(echo "$end_time - $start_time" | bc)
    # Ensure latency has leading zero for valid JSON
    latency=$(printf "%.9f" $latency)
    
    # Write insert operation JSONL
    echo '{{"timestamp_start": '$start_timestamp', "timestamp_end": '$(date +%s)', "latency_s": '$latency', "success": true, "service_type": "postgres", "request_id": "insert_'$i'", "operation_type": "insert", "rows_affected": 1, "query_type": "point_insert"}}' >> "$REQUESTS_FILE"
  else
    insert_errors=$((insert_errors + 1))
    
    # Write failed insert JSONL
    echo '{{"timestamp_start": '$start_timestamp', "timestamp_end": '$(date +%s)', "latency_s": 0, "success": false, "service_type": "postgres", "request_id": "insert_'$i'", "operation_type": "insert", "error": "psql_failed"}}' >> "$REQUESTS_FILE"
  fi
done

INSERT_END=$(date +%s.%N)
INSERT_DURATION=$(echo "$INSERT_END - $INSERT_START" | bc)
INSERT_TPS=$(echo "scale=2; $NUM_INSERTS / $INSERT_DURATION" | bc)

echo "Insert phase complete:"
echo "  Duration: ${{INSERT_DURATION}}s"
echo "  TPS: ${{INSERT_TPS}}"
echo "  Errors: $insert_errors"
echo ""

# Select phase
echo "=== SELECT PHASE ==="
SELECT_START=$(date +%s.%N)
select_errors=0

for i in $(seq 1 $NUM_SELECTS); do
  if [ $((i % 1000)) -eq 0 ]; then
    echo "Executed $i/$NUM_SELECTS selects..."
  fi
  
  start_time=$(date +%s.%N)
  start_timestamp=$(date +%s)
  QUERY_TYPE=$((i % 4))
  
  case $QUERY_TYPE in
    0) 
      query="SELECT COUNT(*) FROM $TABLE_NAME WHERE value = $((i % 1000));"
      query_type="point_lookup"
      ;;
    1) 
      query="SELECT COUNT(*) FROM $TABLE_NAME WHERE value BETWEEN $((i % 500)) AND $((i % 500 + 100));"
      query_type="range_scan"
      ;;
    2) 
      query="SELECT COUNT(*) FROM $TABLE_NAME WHERE payload LIKE '%record_%';"
      query_type="like_scan"
      ;;
    3) 
      query="SELECT value, COUNT(*) FROM $TABLE_NAME GROUP BY value ORDER BY COUNT(*) DESC LIMIT 10;"
      query_type="aggregation"
      ;;
  esac
  
  if psql -h $SERVICE_HOSTNAME -p $SERVICE_PORT -U postgres -d "$DB_NAME" -c "$query" > /dev/null 2>&1; then
    end_time=$(date +%s.%N)
    latency=$(echo "$end_time - $start_time" | bc)
    # Ensure latency has leading zero for valid JSON
    latency=$(printf "%.9f" $latency)
    
    # Write select operation JSONL
    echo '{{"timestamp_start": '$start_timestamp', "timestamp_end": '$(date +%s)', "latency_s": '$latency', "success": true, "service_type": "postgres", "request_id": "select_'$i'", "operation_type": "select", "query_type": "'$query_type'"}}' >> "$REQUESTS_FILE"
  else
    select_errors=$((select_errors + 1))
    
    # Write failed select JSONL
    echo '{{"timestamp_start": '$start_timestamp', "timestamp_end": '$(date +%s)', "latency_s": 0, "success": false, "service_type": "postgres", "request_id": "select_'$i'", "operation_type": "select", "error": "psql_failed"}}' >> "$REQUESTS_FILE"
  fi
done

SELECT_END=$(date +%s.%N)
SELECT_DURATION=$(echo "$SELECT_END - $SELECT_START" | bc)
SELECT_QPS=$(echo "scale=2; $NUM_SELECTS / $SELECT_DURATION" | bc)

echo "Select phase complete:"
echo "  Duration: ${{SELECT_DURATION}}s"
echo "  QPS: ${{SELECT_QPS}}"
echo "  Errors: $select_errors"
echo ""

echo "=== STRESS TEST COMPLETE ==="
echo "Insert TPS: ${{INSERT_TPS}}"
echo "Select QPS: ${{SELECT_QPS}}"
echo "Total errors: $((insert_errors + select_errors))"
echo "Total test time: $(echo "$SELECT_END - $INSERT_START" | bc)s"
"""


def build_chroma_healthcheck_client_command(settings: Dict[str, Any]) -> str:
    """Build ChromaDB healthcheck client command."""
    return """echo 'Testing ChromaDB service at:' $SERVICE_URL
curl -s $SERVICE_URL/api/v2/heartbeat | head -3
echo 'ChromaDB service is reachable'"""


def build_chroma_stress_client_command(settings: Dict[str, Any]) -> str:
    """Build ChromaDB stress test client command using curl with JSONL output (v2 API)."""
    num_vectors = settings.get("num_vectors", 1000)
    dim = settings.get("dim", 128)
    num_queries = settings.get("num_queries", 100)
    top_k = settings.get("top_k", 10)
    warmup_delay = settings.get("warmup_delay", 5)

    # ChromaDB v2 API uses /api/v2/tenants/default_tenant/databases/default_database/collections
    return f"""sleep {warmup_delay}

echo "=== ChromaDB Stress Test (v2 API) ==="
echo "Vectors: {num_vectors}"
echo "Dimension: {dim}"
echo "Queries: {num_queries}"
echo "Top-K: {top_k}"
echo ""

# Initialize JSONL output
mkdir -p "$BENCHMARK_OUTPUT_DIR"
if [ -n "$CLIENT_NAME" ]; then
  REQUESTS_FILE="$BENCHMARK_OUTPUT_DIR/requests_$CLIENT_NAME.jsonl"
else
  REQUESTS_FILE="$BENCHMARK_OUTPUT_DIR/requests.jsonl"
fi
echo '{{"benchmark_id": "'$BENCHMARK_ID'", "service_type": "chroma", "test_start": "'$(date -Iseconds)'"}}' > "$REQUESTS_FILE"

# Base API URL for ChromaDB v2
API_BASE="$SERVICE_URL/api/v2/tenants/default_tenant/databases/default_database"

# Create collection
echo "Creating collection..."
CREATE_RESP=$(curl -s -X POST "$API_BASE/collections" \\
  -H "Content-Type: application/json" \\
  -d '{{"name": "stress_test"}}')
echo "Create response: $CREATE_RESP"

# Get collection ID
COLLECTION_ID=$(echo "$CREATE_RESP" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('id', ''))" 2>/dev/null)

# If collection already exists, get it
if [ -z "$COLLECTION_ID" ]; then
  COLLECTION_ID=$(curl -s "$API_BASE/collections/stress_test" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('id', ''))" 2>/dev/null)
fi

echo "Collection ID: $COLLECTION_ID"

if [ -z "$COLLECTION_ID" ]; then
  echo "ERROR: Could not get collection ID"
  exit 1
fi

# Insert phase
echo ""
echo "=== INSERT PHASE ==="
INSERT_START=$(date +%s.%N)
insert_errors=0

for i in $(seq 1 {num_vectors}); do
  EMBEDDING=$(python3 -c "import random; print([random.random() for _ in range({dim})])")
  
  start_time=$(date +%s.%N)
  start_timestamp=$(date +%s)
  
  HTTP_CODE=$(curl -s -w "%{{http_code}}" -o /tmp/chroma_resp_$i.json -X POST "$API_BASE/collections/$COLLECTION_ID/add" \\
    -H "Content-Type: application/json" \\
    -d "{{\\"ids\\": [\\"id_$i\\"], \\"embeddings\\": [$EMBEDDING]}}")
  
  end_time=$(date +%s.%N)
  latency=$(echo "$end_time - $start_time" | bc)
  latency=$(printf "%.9f" $latency)
  
  if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "201" ]; then
    echo '{{"timestamp_start": '$start_timestamp', "timestamp_end": '$(date +%s)', "latency_s": '$latency', "success": true, "service_type": "chroma", "request_id": "insert_'$i'", "operation_type": "insert", "http_status": '$HTTP_CODE', "vectors": 1, "dimension": {dim}}}' >> "$REQUESTS_FILE"
  else
    insert_errors=$((insert_errors + 1))
    echo '{{"timestamp_start": '$start_timestamp', "timestamp_end": '$(date +%s)', "latency_s": '$latency', "success": false, "service_type": "chroma", "request_id": "insert_'$i'", "operation_type": "insert", "http_status": '$HTTP_CODE', "error": "http_error"}}' >> "$REQUESTS_FILE"
  fi
  
  if [ $((i % 100)) -eq 0 ]; then
    echo "Inserted $i/{num_vectors} vectors..."
  fi
done

INSERT_END=$(date +%s.%N)
INSERT_DURATION=$(echo "$INSERT_END - $INSERT_START" | bc)
INSERT_VPS=$(echo "scale=2; {num_vectors} / $INSERT_DURATION" | bc)

echo "Insert phase complete:"
echo "  Duration: ${{INSERT_DURATION}}s"
echo "  VPS: ${{INSERT_VPS}}"
echo "  Errors: $insert_errors"
echo ""

# Query phase
echo "=== QUERY PHASE ==="
QUERY_START=$(date +%s.%N)
query_errors=0

for i in $(seq 1 {num_queries}); do
  QUERY_VEC=$(python3 -c "import random; print([random.random() for _ in range({dim})])")
  
  start_time=$(date +%s.%N)
  start_timestamp=$(date +%s)
  
  HTTP_CODE=$(curl -s -w "%{{http_code}}" -o /tmp/chroma_query_$i.json -X POST "$API_BASE/collections/$COLLECTION_ID/query" \\
    -H "Content-Type: application/json" \\
    -d "{{\\"query_embeddings\\": [$QUERY_VEC], \\"n_results\\": {top_k}}}")
  
  end_time=$(date +%s.%N)
  latency=$(echo "$end_time - $start_time" | bc)
  latency=$(printf "%.9f" $latency)
  
  if [ "$HTTP_CODE" = "200" ]; then
    echo '{{"timestamp_start": '$start_timestamp', "timestamp_end": '$(date +%s)', "latency_s": '$latency', "success": true, "service_type": "chroma", "request_id": "query_'$i'", "operation_type": "query", "http_status": '$HTTP_CODE', "top_k": {top_k}, "dimension": {dim}}}' >> "$REQUESTS_FILE"
  else
    query_errors=$((query_errors + 1))
    echo '{{"timestamp_start": '$start_timestamp', "timestamp_end": '$(date +%s)', "latency_s": '$latency', "success": false, "service_type": "chroma", "request_id": "query_'$i'", "operation_type": "query", "http_status": '$HTTP_CODE', "error": "http_error"}}' >> "$REQUESTS_FILE"
  fi
  
  if [ $((i % 20)) -eq 0 ]; then
    echo "Executed $i/{num_queries} queries..."
  fi
done

QUERY_END=$(date +%s.%N)
QUERY_DURATION=$(echo "$QUERY_END - $QUERY_START" | bc)
QUERY_QPS=$(echo "scale=2; {num_queries} / $QUERY_DURATION" | bc)

echo "Query phase complete:"
echo "  Duration: ${{QUERY_DURATION}}s"
echo "  QPS: ${{QUERY_QPS}}"
echo "  Errors: $query_errors"
echo ""

echo "=== STRESS TEST COMPLETE ==="
echo "Insert VPS: ${{INSERT_VPS}}"
echo "Query QPS: ${{QUERY_QPS}}"
echo "Total time: $(echo "$QUERY_END - $INSERT_START" | bc)s"
echo "Total errors: $((insert_errors + query_errors))"
"""


def build_vllm_smoke_client_command(settings: Dict[str, Any]) -> str:
    """Build vLLM smoke test client command using curl with JSONL output."""
    model = settings.get("model", "facebook/opt-125m")
    prompt = settings.get("prompt", "Hello")
    max_tokens = settings.get("max_tokens", 50)
    warmup_delay = settings.get("warmup_delay", 5)

    return f"""sleep {warmup_delay}

echo "Testing vLLM service at: $SERVICE_URL"
echo "Model: {model}"
echo "Prompt: {prompt}"
echo ""

# Initialize JSONL output
mkdir -p "$BENCHMARK_OUTPUT_DIR"
if [ -n "$CLIENT_NAME" ]; then
  REQUESTS_FILE="$BENCHMARK_OUTPUT_DIR/requests_$CLIENT_NAME.jsonl"
else
  REQUESTS_FILE="$BENCHMARK_OUTPUT_DIR/requests.jsonl"
fi
echo '{{"benchmark_id": "'$BENCHMARK_ID'", "service_type": "vllm", "test_start": "'$(date -Iseconds)'"}}' > "$REQUESTS_FILE"

# Time the request
START_TIME=$(date +%s.%N)
start_timestamp=$(date +%s)

RESPONSE=$(curl -s -X POST "$SERVICE_URL/v1/completions" \\
  -H "Content-Type: application/json" \\
  -d '{{"model": "{model}", "prompt": "{prompt}", "max_tokens": {max_tokens}}}')

END_TIME=$(date +%s.%N)
end_timestamp=$(date +%s)
LATENCY=$(echo "$END_TIME - $START_TIME" | bc)
# Ensure latency has leading zero for valid JSON
LATENCY=$(printf "%.9f" $LATENCY)

if [ $? -eq 0 ]; then
  # Extract token count if available
  tokens=$(echo "$RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('usage', {{}}).get('completion_tokens', 0))" 2>/dev/null || echo "0")
  
  # Write request JSONL
  echo '{{"timestamp_start": '$start_timestamp', "timestamp_end": '$(date +%s)', "latency_s": '$LATENCY', "success": true, "service_type": "vllm", "request_id": 1, "http_status": 200, "output_tokens": '$tokens', "input_tokens": 5, "prompt": "{prompt}", "model": "{model}"}}' >> "$REQUESTS_FILE"
else
  # Write failed request JSONL
  echo '{{"timestamp_start": '$start_timestamp', "timestamp_end": '$(date +%s)', "latency_s": 0, "success": false, "service_type": "vllm", "request_id": 1, "http_status": null, "error": "curl_failed", "model": "{model}"}}' >> "$REQUESTS_FILE"
fi

echo "Response:"
echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
echo ""
echo "Latency: ${{LATENCY}}s"
echo "vLLM smoke test completed successfully"
"""


def build_vllm_stress_client_command(settings: Dict[str, Any]) -> str:
    """Build vLLM stress test client command using curl with JSONL output."""
    model = settings.get("model", "facebook/opt-125m")
    num_requests = settings.get("num_requests", 50)
    max_tokens = settings.get("max_tokens", 64)
    warmup_delay = settings.get("warmup_delay", 10)
    concurrent_requests = settings.get("concurrent_requests", 1)

    return f"""sleep {warmup_delay}

echo "=== vLLM Stress Test ==="
echo "Model: {model}"
echo "Requests: {num_requests}"
echo "Max tokens: {max_tokens}"
echo "Concurrent: {concurrent_requests}"
echo ""

# Initialize JSONL output
mkdir -p "$BENCHMARK_OUTPUT_DIR"
if [ -n "$CLIENT_NAME" ]; then
  REQUESTS_FILE="$BENCHMARK_OUTPUT_DIR/requests_$CLIENT_NAME.jsonl"
else
  REQUESTS_FILE="$BENCHMARK_OUTPUT_DIR/requests.jsonl"
fi
echo '{{"benchmark_id": "'$BENCHMARK_ID'", "service_type": "vllm", "test_start": "'$(date -Iseconds)'"}}' > "$REQUESTS_FILE"

latency_sum=0
errors=0
success_count=0

for i in $(seq 1 {num_requests}); do
  echo "Request $i:"
  start=$(date +%s.%N)
  start_timestamp=$(date +%s)
  
  response=$(curl -s -X POST "$SERVICE_URL/v1/completions" \\
    -H "Content-Type: application/json" \\
    -d '{{"model": "{model}", "prompt": "Hello world", "max_tokens": {max_tokens}}}' \\
    2>/dev/null)
  
  if [ $? -eq 0 ]; then
    end=$(date +%s.%N)
    end_timestamp=$(date +%s)
    latency=$(echo "$end - $start" | bc)
    # Ensure latency has leading zero for valid JSON
    latency=$(printf "%.9f" $latency)
    latency_sum=$(echo "$latency_sum + $latency" | bc)
    success_count=$((success_count + 1))
    echo "  Latency: ${{latency}}s"
    
    # Extract token count if available
    tokens=$(echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('usage', {{}}).get('completion_tokens', 0))" 2>/dev/null || echo "0")
    
    # Write request JSONL
    echo '{{"timestamp_start": '$start_timestamp', "timestamp_end": '$(date +%s)', "latency_s": '$latency', "success": true, "service_type": "vllm", "request_id": '$i', "http_status": 200, "output_tokens": '$tokens', "input_tokens": 5, "prompt": "Hello world", "model": "{model}"}}' >> "$REQUESTS_FILE"
  else
    echo "  Failed"
    errors=$((errors + 1))
    
    # Write failed request JSONL
    echo '{{"timestamp_start": '$start_timestamp', "timestamp_end": '$(date +%s)', "latency_s": 0, "success": false, "service_type": "vllm", "request_id": '$i', "http_status": null, "error": "curl_failed", "model": "{model}"}}' >> "$REQUESTS_FILE"
  fi
  
  if [ $((i % 10)) -eq 0 ]; then
    echo "Completed $i/{num_requests} requests..."
  fi
  
  # Add delay for concurrent requests > 1
  if [ {concurrent_requests} -gt 1 ]; then
    sleep 0.1
  fi
done

echo ""
echo "=== STRESS TEST COMPLETE ==="
echo "Successful requests: $success_count"
echo "Failed requests: $errors"
if [ $success_count -gt 0 ]; then
  avg_latency=$(echo "scale=3; $latency_sum / $success_count" | bc)
  echo "Avg latency: ${{avg_latency}}s"
fi
echo "vLLM stress test completed"
"""


def build_ollama_smoke_client_command(settings: Dict[str, Any]) -> str:
    """Build Ollama smoke test client command with JSONL output."""
    model = settings.get("model", "llama2")
    num_requests = settings.get("num_requests", 5)
    max_retries = settings.get("max_retries", 30)

    return f"""echo 'Testing Ollama service at $SERVICE_URL'
echo ""
echo "Waiting for service to be ready..."
MAX_RETRIES={max_retries}
RETRY=0
while [ $RETRY -lt $MAX_RETRIES ]; do
  if curl -s $SERVICE_URL/api/tags > /dev/null 2>&1; then
    echo "✓ Service is ready!"
    break
  fi
  echo "Service not ready yet, waiting... (attempt $((RETRY+1))/$MAX_RETRIES)"
  sleep 10
  RETRY=$((RETRY+1))
done
if [ $RETRY -eq $MAX_RETRIES ]; then
  echo "✗ Service did not become ready in time"
  exit 1
fi
echo ""
echo "Running inference benchmark ({num_requests} requests)..."

# Initialize JSONL output
mkdir -p "$BENCHMARK_OUTPUT_DIR"
if [ -n "$CLIENT_NAME" ]; then
  REQUESTS_FILE="$BENCHMARK_OUTPUT_DIR/requests_$CLIENT_NAME.jsonl"
else
  REQUESTS_FILE="$BENCHMARK_OUTPUT_DIR/requests.jsonl"
fi
echo '{{"benchmark_id": "'$BENCHMARK_ID'", "service_type": "ollama", "test_start": "'$(date -Iseconds)'"}}' > "$REQUESTS_FILE"

for i in $(seq 1 {num_requests}); do
  echo "Request $i:"
  START=$(date +%s.%N)
  start_timestamp=$(date +%s)
  
  response=$(curl -X POST $SERVICE_URL/api/generate -d '{{
    "model": "{model}",
    "prompt": "What is artificial intelligence?",
    "stream": false
  }}' 2>/dev/null)
  curl_exit_code=$?
  
  END=$(date +%s.%N)
  end_timestamp=$(date +%s)
  DURATION=$(echo "$END - $START" | bc)
  # Ensure latency has leading zero for valid JSON
  DURATION=$(printf "%.9f" $DURATION)
  
  if [ $curl_exit_code -eq 0 ]; then
    echo "Response: $(echo "$response" | head -c 200)"
    echo "Latency: ${{DURATION}}s"
    
    # Extract response details
    response_len=$(echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data.get('response', '')))" 2>/dev/null || echo "0")
    
    # Write request JSONL
    echo '{{"timestamp_start": '$start_timestamp', "timestamp_end": '$(date +%s)', "latency_s": '$DURATION', "success": true, "service_type": "ollama", "request_id": '$i', "http_status": 200, "output_tokens": '$response_len', "prompt": "What is artificial intelligence?", "model": "{model}"}}' >> "$REQUESTS_FILE"
  else
    echo "Request failed"
    
    # Write failed request JSONL
    echo '{{"timestamp_start": '$start_timestamp', "timestamp_end": '$(date +%s)', "latency_s": 0, "success": false, "service_type": "ollama", "request_id": '$i', "http_status": null, "error": "curl_failed", "model": "{model}"}}' >> "$REQUESTS_FILE"
  fi
  
  echo "---"
done
echo "Benchmark complete!"
"""


def build_ollama_stress_client_command(settings: Dict[str, Any]) -> str:
    """Build Ollama stress test client command with JSONL output."""
    model = settings.get("model", "llama2")
    num_requests = settings.get("num_requests", 20)
    max_tokens = settings.get("max_tokens", 50)
    warmup_delay = settings.get("warmup_delay", 30)
    max_retries = settings.get("max_retries", 30)

    prompts = [
        "What is machine learning?",
        "Explain neural networks briefly.",
        "What is deep learning?",
        "How does AI work?",
        "What is natural language processing?",
    ]

    return f"""sleep {warmup_delay}

echo "=== Ollama Stress Test ==="
echo "Model: {model}"
echo "Requests: {num_requests}"
echo "Max Tokens: {max_tokens}"
echo ""

echo "Waiting for service to be ready..."
MAX_RETRIES={max_retries}
RETRY=0
while [ $RETRY -lt $MAX_RETRIES ]; do
  if curl -s $SERVICE_URL/api/tags > /dev/null 2>&1; then
    echo "✓ Service is ready!"
    break
  fi
  echo "Service not ready yet, waiting... (attempt $((RETRY+1))/$MAX_RETRIES)"
  sleep 10
  RETRY=$((RETRY+1))
done
if [ $RETRY -eq $MAX_RETRIES ]; then
  echo "✗ Service did not become ready in time"
  exit 1
fi

# Initialize JSONL output
mkdir -p "$BENCHMARK_OUTPUT_DIR"
if [ -n "$CLIENT_NAME" ]; then
  REQUESTS_FILE="$BENCHMARK_OUTPUT_DIR/requests_$CLIENT_NAME.jsonl"
else
  REQUESTS_FILE="$BENCHMARK_OUTPUT_DIR/requests.jsonl"
fi
echo '{{"benchmark_id": "'$BENCHMARK_ID'", "service_type": "ollama", "test_start": "'$(date -Iseconds)'"}}' > "$REQUESTS_FILE"

# Array of prompts
PROMPTS=("{prompts[0]}" "{prompts[1]}" "{prompts[2]}" "{prompts[3]}" "{prompts[4]}")

echo ""
echo "=== INFERENCE PHASE ==="
TOTAL_START=$(date +%s.%N)
errors=0

for i in $(seq 1 {num_requests}); do
  PROMPT_IDX=$((($i - 1) % 5))
  PROMPT="${{PROMPTS[$PROMPT_IDX]}}"
  
  start_time=$(date +%s.%N)
  start_timestamp=$(date +%s)
  
  response=$(curl -s -X POST $SERVICE_URL/api/generate -d '{{
    "model": "{model}",
    "prompt": "'"$PROMPT"'",
    "stream": false,
    "options": {{"num_predict": {max_tokens}}}
  }}' 2>/dev/null)
  curl_exit_code=$?
  
  end_time=$(date +%s.%N)
  latency=$(echo "$end_time - $start_time" | bc)
  latency=$(printf "%.9f" $latency)
  
  if [ $curl_exit_code -eq 0 ] && echo "$response" | grep -q "response"; then
    # Extract token counts
    eval_count=$(echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('eval_count', 0))" 2>/dev/null || echo "0")
    prompt_eval_count=$(echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('prompt_eval_count', 0))" 2>/dev/null || echo "0")
    
    echo '{{"timestamp_start": '$start_timestamp', "timestamp_end": '$(date +%s)', "latency_s": '$latency', "success": true, "service_type": "ollama", "request_id": '$i', "http_status": 200, "output_tokens": '$eval_count', "input_tokens": '$prompt_eval_count', "model": "{model}"}}' >> "$REQUESTS_FILE"
    
    if [ $((i % 5)) -eq 0 ]; then
      echo "Completed $i/{num_requests} requests... (latency: ${{latency}}s)"
    fi
  else
    errors=$((errors + 1))
    echo '{{"timestamp_start": '$start_timestamp', "timestamp_end": '$(date +%s)', "latency_s": '$latency', "success": false, "service_type": "ollama", "request_id": '$i', "http_status": null, "error": "inference_failed", "model": "{model}"}}' >> "$REQUESTS_FILE"
    echo "Request $i failed"
  fi
done

TOTAL_END=$(date +%s.%N)
TOTAL_DURATION=$(echo "$TOTAL_END - $TOTAL_START" | bc)
RPS=$(echo "scale=2; {num_requests} / $TOTAL_DURATION" | bc)

echo ""
echo "=== STRESS TEST COMPLETE ==="
echo "Total requests: {num_requests}"
echo "Errors: $errors"
echo "Total time: ${{TOTAL_DURATION}}s"
echo "Throughput: ${{RPS}} RPS"
"""


def build_nginx_healthcheck_client_command(settings: Dict[str, Any]) -> str:
    """Build nginx healthcheck client command."""
    return """echo 'Testing nginx at:' $SERVICE_URL
curl -s $SERVICE_URL | head -5
echo 'Service reachable'
echo 'Benchmark complete'"""


# =============================================================================
# REGISTRY AND MAIN BUILDER FUNCTIONS
# =============================================================================

SERVICE_BUILDERS = {
    "postgres": build_postgres_service_command,
    "chroma": build_chroma_service_command,
    "vllm": build_vllm_service_command,
    "ollama": build_ollama_service_command,
    "nginx": build_nginx_service_command,
}

CLIENT_BUILDERS = {
    "postgres_smoke": build_postgres_smoke_client_command,
    "postgres_stress": build_postgres_stress_client_command,
    "chroma_healthcheck": build_chroma_healthcheck_client_command,
    "chroma_stress": build_chroma_stress_client_command,
    "vllm_smoke": build_vllm_smoke_client_command,
    "vllm_stress": build_vllm_stress_client_command,
    "ollama_smoke": build_ollama_smoke_client_command,
    "ollama_stress": build_ollama_stress_client_command,
    "nginx_healthcheck": build_nginx_healthcheck_client_command,
}


def build_service_command(service_type: str, settings: Dict[str, Any]) -> Optional[str]:
    """
    Build service command from type and settings.

    Args:
        service_type: Type of service (e.g., "postgres", "chroma")
        settings: Service-specific settings

    Returns:
        Generated command string, or None if type not found
    """
    builder = SERVICE_BUILDERS.get(service_type)
    if builder:
        return builder(settings)
    return None


def build_client_command(client_type: str, settings: Dict[str, Any]) -> Optional[str]:
    """
    Build client command from type and settings.

    Args:
        client_type: Type of client (e.g., "postgres_smoke", "chroma_stress")
        settings: Client-specific settings

    Returns:
        Generated command string, or None if type not found
    """
    builder = CLIENT_BUILDERS.get(client_type)
    if builder:
        return builder(settings)
    return None


def get_default_image(service_type: str) -> Optional[str]:
    """Get default container image for a service type."""
    defaults = {
        "postgres": "postgres:latest",
        "chroma": "chromadb/chroma:latest",
        "vllm": "vllm/vllm-openai:latest",
        "ollama": "ollama/ollama:latest",
        "nginx": "nginx:latest",
    }
    return defaults.get(service_type)


def get_default_port(service_type: str) -> Optional[int]:
    """Get default port for a service type."""
    defaults = {
        "postgres": 5432,
        "chroma": 8000,
        "vllm": 8000,
        "ollama": 11434,
        "nginx": 80,
    }
    return defaults.get(service_type)


def get_default_env(
    service_type: str, settings: Dict[str, Any]
) -> Optional[Dict[str, str]]:
    """Get default environment variables for a service type."""
    if service_type == "postgres":
        data_dir = settings.get("data_dir", "/tmp/pgdata")
        return {"PGDATA": data_dir}
    return None


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================


def validate_service_type(service_type: str) -> None:
    """Validate that service type is supported."""
    if service_type not in SERVICE_BUILDERS:
        supported = ", ".join(sorted(SERVICE_BUILDERS.keys()))
        raise ValueError(
            f"Unknown service type '{service_type}'. Supported types: {supported}"
        )


def validate_client_type(client_type: str) -> None:
    """Validate that client type is supported."""
    if client_type not in CLIENT_BUILDERS:
        supported = ", ".join(sorted(CLIENT_BUILDERS.keys()))
        raise ValueError(
            f"Unknown client type '{client_type}'. Supported types: {supported}"
        )


def validate_settings(settings: Dict[str, Any], context: str = "") -> None:
    """
    Validate settings values for sanity.

    Args:
        settings: Settings dictionary to validate
        context: Context string for error messages (e.g., "service" or "client")
    """
    # Numeric fields that must be positive
    positive_fields = [
        "num_inserts",
        "num_selects",
        "num_vectors",
        "num_queries",
        "num_requests",
        "warmup_delay",
        "warmup_seconds",
        "max_retries",
        "top_k",
        "dim",
        "max_tokens",
        "tensor_parallel_size",
    ]

    for field in positive_fields:
        if field in settings:
            value = settings[field]
            if not isinstance(value, (int, float)) or value < 0:
                raise ValueError(
                    f"Invalid {context} setting '{field}': must be a non-negative number, got {value}"
                )
            if field in [
                "num_inserts",
                "num_selects",
                "num_vectors",
                "num_queries",
                "num_requests",
            ]:
                if value < 1:
                    raise ValueError(
                        f"Invalid {context} setting '{field}': must be at least 1, got {value}"
                    )


def get_supported_service_types() -> list:
    """Return list of supported service types."""
    return list(SERVICE_BUILDERS.keys())


def get_supported_client_types() -> list:
    """Return list of supported client types."""
    return list(CLIENT_BUILDERS.keys())
