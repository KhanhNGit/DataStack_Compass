# DataStack Compass

Software Version Risk Governance Platform.
Automatically collects, processes, stores, and displays Release Notes, CVEs, Breaking Changes, and License changes across the modern data stack (Kafka, Flink, Spark, etc.).

## Architecture Overview

```text
┌──────────────┐     ┌─────────────┐     ┌───────────────┐     ┌───────────────────────┐
│              │     │             │     │               │     │                       │
│ GitHub API & ├───► │   Apache    ├───► │ Apache Spark  ├───► │ Delta Lake (MinIO)    │
│ NVD Database │     │   Airflow   │     │  (PySpark)    │     │ s3a://bucket/table    │
│              │     │             │     │               │     │                       │
└──────────────┘     └─────────────┘     └──────┬────────┘     └───────────┬───────────┘
                                                │                          │
                                                │ (DQ checks)              │ (External Catalog)
                                                ▼                          ▼
                                         ┌───────────────┐     ┌───────────────────────┐
                                         │               │     │                       │
                                         │ Great Expect. │     │      StarRocks        │
                                         │               │     │    (OLAP Database)    │
                                         └───────────────┘     └───────────┬───────────┘
                                                                           │
                                                                           │ (pymysql)
                                                                           ▼
┌──────────────┐                       ┌───────────────┐     ┌───────────────────────┐
│              │     (REST API)        │               │     │                       │
│   ReactJS    │ ◄───────────────────► │    FastAPI    │ ◄───┤ Alerting Engine (SMTP)│
│ (Frontend)   │                       │   (Backend)   │     │                       │
└──────────────┘                       └───────────────┘     └───────────────────────┘
```

## Local Development Setup

Step-by-step từ zero:

1. Clone repo
   ```bash
   git clone <repo-url>
   cd datastack-compass
   ```

2. Copy `.env.example` → `.env`, fill in `GITHUB_TOKEN`
   ```bash
   cp .env.example .env
   # Mở file .env và điền giá trị GITHUB_TOKEN thật của bạn
   ```

3. Khởi động hạ tầng thông qua Docker
   ```bash
   cd infra/docker && make up
   ```

4. Chờ health check pass
   ```bash
   ./health_check.sh
   ```

5. Khởi tạo Delta tables
   ```bash
   python processing/spark_jobs/init_tables.py
   ```

6. Setup StarRocks external catalog
   Thực thi câu lệnh SQL sau trong trình quản lý hoặc client connect tới StarRocks (port 9030):
   ```sql
   CREATE EXTERNAL CATALOG minio_catalog
   PROPERTIES (
       "type" = "deltalake",
       "hive.metastore.type" = "dlf",
       "aws.s3.endpoint" = "http://minio:9000",
       "aws.s3.access_key" = "minioadmin",
       "aws.s3.secret_key" = "minioadmin",
       "aws.s3.enable_path_style_access" = "true"
   );
   ```

7. Start API
   ```bash
   cd api
   uvicorn main:app --reload
   ```

8. Start Frontend
   ```bash
   cd frontend
   npm install
   npm run dev
   # Lưu ý: Vite mặc định dùng npm run dev thay vì npm start
   ```

## RAM Usage Reference

Bảng tổng hợp từ cấu hình local:

| Service | RAM Limit | RAM Typical |
|---|---|---|
| MinIO | 512MB | ~200MB |
| StarRocks | 4GB | ~2.5GB |
| Airflow (webserver+scheduler) | 2.5GB | ~1.5GB |
| Spark (khi chạy job) | 2GB (on-demand) | 0 khi idle |
| FastAPI + ReactJS | 500MB | ~300MB |
| **Total** | **~9.5GB** | **~4.5-6.5GB** |

## Production Differences (chỉ config, không sửa code)

Dự án tuân thủ nghiêm ngặt rule Code Portability, vì vậy các môi trường chỉ khác nhau ở file cấu hình / biến môi trường:

| Configuration | `ENV=dev` (Local) | `ENV=prod` (Production) |
|---|---|---|
| **Orchestration** | Airflow LocalExecutor (Docker Compose) | Airflow KubernetesExecutor (K8s) |
| **Spark Mode** | local[*] (PySpark) | cluster mode (YARN / K8s) |
| **Storage (S3A)** | MinIO (s3a://... qua http://minio:9000) | AWS S3 / GCS buckets thực tế |
| **StarRocks** | All-in-One container | FE/BE tách biệt Nodes (High Availability) |
| **Mocking** | API trả về fixtures (ví dụ Governance blogs) | Query StarRocks Database thực |

## API Documentation

FastAPI tự động generate OpenAPI specification. Khi backend đã start, bạn có thể truy cập document tương tác tại:
- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)
