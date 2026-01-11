# LocalStack Architecture Artifacts

This repository stores discovered Terraform architectures, generated test applications, and validation results for the [LocalStack Quality Monitor](https://github.com/lazarkanelov/localstack-quality-monitor) project.

**[View Latest Report](https://lazarkanelov.github.io/localstack-quality-monitor/latest/)** | **[All Reports](https://lazarkanelov.github.io/localstack-quality-monitor/)**

## Purpose

This artifact repository serves as persistent storage for:

- **Discovered Architectures** - Terraform configurations from various sources
- **Generated Test Apps** - Python pytest applications created by Claude AI
- **Validation Results** - Test results from running against LocalStack
- **Run History** - Historical data for trend analysis

## Repository Structure

```
ls-arch-artifacts/
├── architectures/
│   ├── index.json              # Master index of all architectures
│   ├── {hash}/                 # Individual architecture folders
│   │   ├── metadata.json       # Architecture metadata
│   │   ├── main.tf             # Terraform configuration
│   │   ├── variables.tf        # Variable definitions
│   │   └── outputs.tf          # Output definitions
│   └── ...
├── apps/
│   ├── {hash}/                 # Generated test applications
│   │   ├── test_app.py         # pytest test file
│   │   ├── requirements.txt    # Python dependencies
│   │   └── conftest.py         # pytest configuration
│   └── ...
└── runs/
    ├── {run-id}/               # Validation run results
    │   ├── summary.json        # Run summary and statistics
    │   └── results/
    │       ├── {hash}.json     # Per-architecture results
    │       └── ...
    └── ...
```

## Data Formats

### Architecture Index (`architectures/index.json`)

```json
{
  "version": 1,
  "architectures": {
    "abc123def456": {
      "hash": "abc123def456",
      "name": "aws-samples/serverless-patterns/s3-lambda-terraform",
      "source_url": "https://github.com/aws-samples/serverless-patterns",
      "source_type": "github_repos",
      "services": ["s3", "lambda", "iam"],
      "resource_count": 5,
      "discovered_at": "2024-01-15T10:30:00Z"
    }
  },
  "latest_run": "run-2024-01-15-abc123"
}
```

### Architecture Metadata (`architectures/{hash}/metadata.json`)

```json
{
  "hash": "abc123def456",
  "name": "s3-lambda-terraform",
  "source_url": "https://github.com/aws-samples/serverless-patterns/tree/main/s3-lambda-terraform",
  "source_type": "github_repos",
  "services": ["s3", "lambda", "iam"],
  "resource_count": 5,
  "discovered_at": "2024-01-15T10:30:00Z",
  "description": "S3 bucket triggering Lambda function"
}
```

### Run Summary (`runs/{run-id}/summary.json`)

```json
{
  "run_id": "run-2024-01-15-abc123",
  "started_at": "2024-01-15T10:00:00Z",
  "completed_at": "2024-01-15T10:45:00Z",
  "localstack_version": "3.0.0",
  "total": 50,
  "passed": 35,
  "failed": 10,
  "timeout": 3,
  "error": 2,
  "pass_rate": 70.0
}
```

### Validation Result (`runs/{run-id}/results/{hash}.json`)

```json
{
  "arch_hash": "abc123def456",
  "run_id": "run-2024-01-15-abc123",
  "status": "PASSED",
  "started_at": "2024-01-15T10:05:00Z",
  "completed_at": "2024-01-15T10:06:30Z",
  "duration_seconds": 90,
  "terraform_apply": {
    "success": true,
    "resources_created": 5,
    "logs": "..."
  },
  "pytest_results": {
    "passed": 3,
    "failed": 0,
    "output": "..."
  },
  "container_logs": "LocalStack logs...",
  "error_message": null
}
```

## How It's Used

### By LSQM Pipeline

1. **Sync Stage** - Clones this repo to load existing architectures
2. **Mine Stage** - Adds new architectures to `architectures/`
3. **Generate Stage** - Creates test apps in `apps/`
4. **Validate Stage** - Stores results in `runs/`
5. **Push Stage** - Commits and pushes all changes

### Deduplication

Architectures are deduplicated by:
- **Source URL** - Prevents re-mining the same repository location
- **Content Hash** - Prevents duplicate Terraform content from different sources

The hash is computed from normalized Terraform content (comments and whitespace removed).

## Architecture Sources

Architectures in this repository come from:

| Source | Description |
|--------|-------------|
| `github_repos` | Direct repository scanning (e.g., aws-samples/serverless-patterns) |
| `github_orgs` | Organization-wide search (aws-samples, terraform-aws-modules) |
| `terraform_registry` | Popular Terraform modules from registry.terraform.io |
| `custom` | Manually added architectures |

## Standalone Requirements

Only self-contained architectures are stored. An architecture must:

- Have at least one `resource "aws_*"` block
- Have all variables with default values (no required inputs)
- Not depend on remote modules
- Not use `terraform_remote_state`
- Use only LocalStack Community Edition services

## Statistics

Current repository statistics are available in the [latest report](https://lazarkanelov.github.io/localstack-quality-monitor/latest/).

## Related Projects

- [LocalStack Quality Monitor](https://github.com/lazarkanelov/localstack-quality-monitor) - The main LSQM tool
- [LocalStack](https://github.com/localstack/localstack) - Local AWS cloud emulator
- [terraform-local](https://github.com/localstack/terraform-local) - Terraform wrapper for LocalStack

## Automated Updates

This repository is automatically updated by the [Weekly Quality Monitor](https://github.com/lazarkanelov/localstack-quality-monitor/actions/workflows/weekly-run.yml) GitHub Actions workflow every Sunday.

