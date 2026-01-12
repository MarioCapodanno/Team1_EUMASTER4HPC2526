# containers/ - Container Definitions

Apptainer/Singularity definition files for building containers on HPC.

## Files

| File | Description |
|------|-------------|
| `grafana.def` | Grafana monitoring dashboard container |
| `prometheus.def` | Prometheus metrics server container |
| `pushgateway.def` | Prometheus Pushgateway container |

## Building

```bash
# Build container on MeluXina
apptainer build grafana.sif grafana.def
```
