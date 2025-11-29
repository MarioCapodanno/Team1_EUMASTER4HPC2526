# Student Challenge 2025-2026 (Benchmarking AI Factories on MeluXina supercomputer)

The objective of this challenge is to prepare students for the upcoming AI Factories in the European Union. These AI Factories will harness the power of next-generation HPC and AI systems to revolutionise data processing, analytics, and model deployment. Through this challenge, students will gain practical skills in AI benchmarking, system monitoring, and real-world deployment scenarios—equipping them to design and operate future AI Factory workflows at scale.

# Global plan of the challenge

The challenge will span 4 months, with students organised into teams. It follows these steps:

## Phase 1 :

### Onboarding

- Introduction to MeluXina and best practices for research and commercial HPC use.
- Familiarisation with Slurm, storage systems, and monitoring tools.
- Exploration & Adoption: In-depth exploration of the assigned topic.
- Define objectives, identify tools and methodologies, and clarify performance metrics.

### What to do:

- Create your own project github (public) and configure it with milestones
- Comment on the issue 1 (https://github.com/LuxProvide/EUMASTER4HPC2526/issues/1 ) to mention your github URL
- Do the onboaring and the examples on meluxina
- Load the example's result/log files on your github
- Schedule meetings (within the group and brainstorm the project)
- Define clear design, identify the tech stacks, create issues on your gitLab

### What I need to look to at the end of the phase:

- Your github
- The logs of the example (per user)
- The design (README file)
- The issues & tasks


## Phase 2 :

-Prototyping: Development of applications, monitoring dashboards, or benchmarking scripts.
-Iterative testing and validation.

## Phase 3:

- Evaluation & Testing: Deployment on MeluXina at realistic scales.
- Performance measurements, resource usage profiling, and scalability testing.
- Report Building: Documentation of methodologies, results, and recommended best practices.
- Creation of comprehensive final reports.

## Phase 4:

-Defense: Each team will present their results and defend their findings in a final session.
Q&A and feedback for improvement.

# Challenge topics: Developing a global benchmarking framework for AI Factory workloads

## Objectives

Design and implement a unified benchmarking framework to evaluate end-to-end performance for critical AI Factory components.
Include benchmarks for:

- File storage, relational databases (e.g., PostgreSQL), and object storage (e.g., S3)
- Inference servers (vLLM, Triton, etc.)
- Vector databases (Chroma, Faiss, Milvus, Weaviate)
- Enable reproducible, modular benchmarking scenarios using Slurm orchestration.
- Provide comparative insights, performance guidelines, and scalability assessments.

## Timeline

- Month 1: Analyse MeluXina’s architecture; survey APIs and services for storage, inference, and retrieval; design benchmark framework architecture.
- Month 2: Develop modular benchmark components:
    - Generic services deployment : Storage, Inference, Vector DB
    - Load generators based on Dask/Spark/Slurm for inference and retrieval tasks
    - Common data schema and metrics collection interface
- Month 3: Execute benchmarks using Slurm; collect throughput, latency, resource usage, and scaling metrics across all components.
- Month 4: Integrate results; generate dashboards and comparisons; finalise documentation and present findings.

## Tools & stacks :

- Modular framework using Python, and Slurm
- Python DB drivers (e.g., psycopg2), S3 SDK for storage benchmarks
- GPU-accelerated inference servers in containerised environments
- Dockerised vector DB deployments for scalable search testing
- Prometheus & Grafana for unified monitoring
- Slurm for orchestrated, synchronised benchmark execution
- Supervision & Mentoring

## Supervision by Dr. Farouk Mansouri:

- Dr. Mansouri Farouk will oversee the challenge, providing strategic and technical supervision with a load of 4 hours per month.
Responsibilities:
- Overall coordination and alignment with AI Factory vision.
Weekly progress reviews.
- Technical deep-dives on HPC practices and system optimisation.


## Mentoring:

- Dedicated mentoring sessions will take place one per week for:
- Technical support and best practices.
-Guidance on tool selection, deployment, and optimisation.
-Assistance with debugging, benchmarking analysis, and report writing.
Preparation for the final defense.

## Current Implementation Status

### Phase 2 Progress: Modular Benchmark Framework

The framework now includes:

1. **Service Module** (`src/service.py`): Manages service deployment and lifecycle
2. **Client Module** (`src/client.py`): Generic client for running benchmarks against services
3. **Manager Module** (`src/manager.py`): Orchestrates service and client deployment via Slurm
4. **Frontend Module** (`src/frontend.py`): CLI interface for deploying and monitoring benchmarks
5. **Communicator Module** (`src/communicator.py`): SSH-based cluster communication
6. **Storage Module** (`src/storage.py`): State persistence for benchmarks

### Key Features

- ✅ **Generic Service Deployment**: Deploy any containerized service (inference servers, databases, etc.)
- ✅ **Generic Client Deployment**: Run customizable benchmark clients with automatic service discovery
- ✅ **Service Health Verification**: Clients only deploy after verifying services are running
- ✅ **Separate Sbatch Jobs**: Services and clients run as independent Slurm jobs for scalability
- ✅ **State Persistence**: All benchmark state saved to storage for monitoring and analysis
- ✅ **Recipe-based Configuration**: YAML-based configuration for reproducible benchmarks

### Usage

Deploy a benchmark:
```bash
python src/frontend.py examples/recipe_test.yaml
```

Check benchmark status:
```bash
python src/frontend.py --id <benchmark_id>
```

### Example Recipes

- `examples/recipe_test.yaml`: Simple nginx service with echo clients
- `examples/recipe_vllm.yaml`: vLLM inference server benchmark
- `examples/recipe_postgres.yaml`: PostgreSQL database benchmark
- `examples/recipe_chroma.yaml`: Chroma vector database benchmark

See `docs/CLIENT_IMPLEMENTATION.md` for detailed documentation.

### Testing

Run the test suite:
```bash
python test_client_module.py
```

