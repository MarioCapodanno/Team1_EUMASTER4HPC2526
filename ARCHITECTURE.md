# Architecture Documentation

## Overview

The AI Factory Benchmarking Framework is a modular Python-based system designed to deploy and benchmark containerized services on HPC clusters using Slurm orchestration. The framework follows a clean separation of concerns with distinct modules for communication, state management, service orchestration, and user interaction.

## System Architecture

```
┌─────────────┐
│  Frontend   │  CLI interface and recipe parsing
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Manager   │  Service and client orchestration
└──────┬──────┘
       │
       ├────────────┬─────────────┬──────────────┐
       ▼            ▼             ▼              ▼
┌─────────────┐ ┌──────┐   ┌──────────┐   ┌─────────┐
│Communicator │ │Client│   │ Service  │   │ Storage │
└─────────────┘ └──────┘   └──────────┘   └─────────┘
       │           Data        Data         Persistence
       ▼          Models      Models            Layer
┌─────────────┐
│   Cluster   │  MeluXina HPC (Slurm + Apptainer)
└─────────────┘
```

## Core Modules

### Frontend Module (`frontend.py`)

**Purpose**: Entry point for user interaction, handles CLI arguments and recipe configuration parsing.

**Responsibilities**:
- Parse YAML recipe files into structured Python objects
- Generate unique benchmark identifiers
- Coordinate deployment workflow through Manager
- Display benchmark status and results

**Key Components**:
- `Recipe`: Main configuration container
- `Configuration`: Cluster target settings
- `ServiceConfig`: Service deployment parameters
- `ClientConfig`: Client deployment parameters
- `BenchmarkConfig`: Benchmark execution settings
- `parse_recipe()`: YAML parsing function
- `main()`: CLI entry point

**Input**: YAML recipe files or benchmark IDs
**Output**: Deployment status and benchmark information

### Manager Module (`manager.py`)

**Purpose**: Orchestrates service and client deployment on the cluster, managing the complete lifecycle from submission to monitoring.

**Responsibilities**:
- Connect to cluster via Communicator
- Generate sbatch scripts for services and clients
- Submit jobs to Slurm scheduler
- Monitor job status transitions
- Create and persist Service and Client objects
- Verify service health before client deployment

**Key Methods**:
- `connect()` / `disconnect()`: Cluster connection management
- `deploy_service()`: Deploy containerized service
- `deploy_client()`: Deploy benchmark client with service verification
- `deploy_multiple_clients()`: Deploy multiple clients in parallel
- `_create_sbatch_script()`: Generate service job scripts
- `_create_client_sbatch_script()`: Generate client job scripts
- `_wait_for_job_to_start()`: Poll job status until running
- `load_service()` / `load_client()`: Retrieve persisted state

**Dependencies**: Communicator, Service, Client, Storage

### Communicator Module (`communicator.py`)

**Purpose**: Abstract interface for cluster communication with concrete SSH implementation.

**Responsibilities**:
- Execute remote commands on cluster
- Transfer files to/from cluster
- Submit and manage Slurm jobs
- Query job status and metadata

**Architecture**:
- `Communicator`: Abstract base class defining interface
- `SSHCommunicator`: Concrete implementation using Fabric/Paramiko
- `CommandResult`: Encapsulates command execution results

**Key Methods**:
- `connect()` / `disconnect()`: Session management
- `execute_command()`: Run shell commands remotely
- `upload_file()` / `download_file()`: File transfer operations
- `submit_job()`: Submit sbatch scripts to Slurm
- `get_job_status()`: Query job state via squeue/sacct
- `cancel_job()`: Terminate running jobs

**Implementation Details**:
- Uses SSH config files for connection settings
- Supports command timeouts and working directory context
- Parses Slurm output for job IDs and status

### Service Module (`service.py`)

**Purpose**: Data model representing a deployed service on the cluster.

**Responsibilities**:
- Store service metadata and connection information
- Provide serialization for persistence
- Track service lifecycle timestamps

**Key Attributes**:
- `name`: Service identifier
- `container_image`: Container image specification
- `job_id`: Slurm job identifier
- `hostname` / `port`: Network connection details
- `submit_time` / `start_time` / `end_time`: Lifecycle timestamps
- `working_dir` / `log_file`: Cluster filesystem paths
- `metadata`: Extensible metadata dictionary

**Key Methods**:
- `get_url()`: Construct service URL
- `to_dict()` / `from_dict()`: Serialization
- `save()` / `load()` / `load_all()`: Persistence operations

### Client Module (`client.py`)

**Purpose**: Data model representing a benchmark client running on the cluster.

**Responsibilities**:
- Store client metadata and execution information
- Track relationship to target service
- Provide serialization for persistence

**Key Attributes**:
- `name`: Client identifier
- `service_name`: Target service reference
- `benchmark_command`: Benchmark execution command
- `job_id`: Slurm job identifier
- `hostname`: Execution node
- `submit_time` / `start_time` / `end_time`: Lifecycle timestamps
- `log_file` / `metrics_file`: Output file paths
- `metadata`: Extensible metadata dictionary

**Key Methods**:
- `to_dict()` / `from_dict()`: Serialization
- `save()` / `load()` / `load_all()`: Persistence operations

### Storage Module (`storage.py`)

**Purpose**: Persistence layer for benchmark state with pluggable backend support (data are saved locally).

**Responsibilities**:
- Store and retrieve Service and Client objects
- Organize data by benchmark ID
- Support multiple storage backends

**Architecture**:
- `StorageBackend`: Abstract interface
- `CSVStorageBackend`: File-based CSV implementation
- `StorageManager`: High-level storage operations

**Key Methods**:
- `save_entity()`: Persist entity to storage
- `load_entity()`: Retrieve entity by ID
- `load_all_entities()`: Retrieve all entities of type
- `delete_entity()`: Remove entity from storage
- `list_benchmarks()`: List all benchmark IDs

**Current Implementation**: CSV files in `~/.benchmark_storage/`

### Monitor Module (`monitor.py`)

**Purpose**: Reserved for future monitoring and metrics collection functionality.

**Status**: Placeholder for Phase 3 implementation.

## Communication Flow

### Deployment Workflow

1. **User initiates deployment**: `python frontend.py recipe.yaml`
2. **Frontend parses recipe**: Validates YAML and creates Recipe object
3. **Frontend creates Manager**: Passes target and generated benchmark ID
4. **Manager connects to cluster**: Establishes SSH session via Communicator
5. **Manager deploys service**:
   - Generates sbatch script with container and command
   - Uploads script to cluster via Communicator
   - Submits job via Communicator
   - Waits for job to reach RUNNING state
   - Creates Service object with cluster metadata
   - Persists Service via Storage
6. **Manager verifies service**: Checks Slurm job status is RUNNING
7. **Manager deploys clients** (for each client):
   - Generates sbatch script with benchmark command
   - Injects service connection environment variables
   - Uploads script to cluster
   - Submits job via Communicator
   - Creates Client object
   - Persists Client via Storage
8. **Frontend displays summary**: Shows benchmark ID and deployment status

### Status Query Workflow

1. **User queries status**: `frontend.py --id <benchmark_id>`
2. **Frontend loads entities**: Retrieves Services and Clients via Storage
3. **Frontend displays information**: Lists all services and clients with metadata

### Service-Client Communication

Clients receive service connection information via environment variables injected by the Manager into their sbatch scripts:

- `SERVICE_NAME`: Service identifier
- `SERVICE_HOSTNAME`: Hostname where service is running
- `SERVICE_PORT`: Service port number
- `SERVICE_URL`: Complete HTTP URL to service

Clients use these variables in their benchmark commands to connect to services.

## Data Flow

```
Recipe YAML
    │
    ▼
[Frontend: Parse]
    │
    ▼
Recipe Object
    │
    ▼
[Manager: Deploy Service]
    │
    ├──[Communicator: Submit Job]──► Cluster (Slurm)
    │                                    │
    │                                    ▼
    │                              Service Running
    │                                    │
    ├──[Storage: Save Service]◄──────────┘
    │
    ▼
[Manager: Verify Service Running]
    │
    ▼
[Manager: Deploy Clients]
    │
    ├──[Communicator: Submit Jobs]──► Cluster (Slurm)
    │                                     │
    │                                     ▼
    │                               Clients Running
    │                                     │
    └──[Storage: Save Clients]◄───────────┘
```

## Extension Points

### Adding New Storage Backends

Implement `StorageBackend` interface:
```python
class DatabaseStorageBackend(StorageBackend):
    def save(self, benchmark_id, entity_type, entity_id, data): ...
    def load(self, benchmark_id, entity_type, entity_id): ...
    def load_all(self, benchmark_id, entity_type): ...
```

### Adding New Communicator Types

Implement `Communicator` interface:
```python
class APIcommunicator(Communicator):
    def connect(self): ...
    def execute_command(self, command): ...
    def submit_job(self, script_path): ...
```

### Adding Custom Metrics

Extend `Client` metadata field:
```python
client.metadata['custom_metrics'] = {
    'throughput': 1000,
    'p99_latency': 0.5
}
```

## Design Principles

1. **Separation of Concerns**: Each module has a single, well-defined responsibility
2. **Abstraction**: Communication and storage use abstract interfaces for flexibility
3. **Data Models**: Service and Client are pure data containers, logic lives in Manager
4. **State Persistence**: All benchmark state is persisted for later analysis
5. **Recipe-Driven**: Configuration via YAML enables reproducible benchmarks
6. **Modularity**: Components can be extended or replaced independently

## Technology Stack

- **Language**: Python 3.10+
- **Cluster Communication**: Fabric (SSH), Paramiko
- **Job Scheduling**: Slurm
- **Containerization**: Apptainer/Singularity
- **Configuration**: YAML
- **Storage**: CSV (current), extensible to databases
- **HPC Platform**: MeluXina supercomputer

## Security Considerations

- SSH authentication uses cluster SSH configuration
- No credentials stored in code or recipes
- Job submission restricted by Slurm account permissions
- File operations confined to user-owned directories
