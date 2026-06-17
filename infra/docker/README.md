# DataStack Compass — Local Infrastructure

Hướng dẫn khởi chạy toàn bộ hạ tầng phát triển trên máy local bằng Docker Compose.

## Kiến trúc tổng quan

```
┌──────────────────────────────────────────────────────────────┐
│                      datastack-net                           │
│                                                              │
│  ┌──────────┐   ┌────────────┐   ┌──────────────────────┐   │
│  │  MinIO    │   │ StarRocks  │   │  Airflow             │   │
│  │  :9000 S3 │   │  :9030 SQL │   │  :8080 Webserver     │   │
│  │  :9001 UI │   │  :8030 FE  │   │  Scheduler (no port) │   │
│  └──────────┘   └────────────┘   └──────────┬───────────┘   │
│                                              │               │
│                                    ┌─────────▼─────────┐     │
│                                    │ PostgreSQL :5432   │     │
│                                    │ (Airflow metadata) │     │
│                                    └───────────────────┘     │
│                                                              │
│  ┌─────────────────────────┐     ┌──────────────────────┐    │
│  │  FastAPI Backend :8000  │     │  Frontend Web :3000  │    │
│  └─────────────────────────┘     └──────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

## Yêu cầu

| Tool            | Version tối thiểu |
| --------------- | ----------------- |
| Docker Engine   | 24.0+             |
| Docker Compose  | v2.20+            |
| GNU Make        | 4.0+              |
| MySQL client    | bất kỳ (cho health check) |

## Khởi động lần đầu

```bash
# 1. Di chuyển tới thư mục infra
cd infra/docker

# 2. Khởi động toàn bộ services
make up

# 3. Đợi khoảng 60–90 giây cho StarRocks khởi động xong

# 4. Kiểm tra trạng thái
make ps

# 5. Chạy health check
bash health_check.sh
```

> **Lưu ý:** Lần chạy đầu tiên Docker sẽ pull images (~3–5 GB), hãy đảm bảo
> kết nối Internet ổn định.

## URL truy cập các services

| Service           | URL                                     | Credentials               |
| ----------------- | --------------------------------------- | ------------------------- |
| MinIO Console     | [http://localhost:9001](http://localhost:9001) | `minioadmin` / `minioadmin` |
| MinIO S3 API      | `http://localhost:9000`                 | (dùng access key ở trên)  |
| StarRocks FE      | [http://localhost:8030](http://localhost:8030) | —                         |
| StarRocks MySQL   | `mysql -h 127.0.0.1 -P 9030 -u root`  | password: *(không có)*    |
| Airflow Web UI    | [http://localhost:8080](http://localhost:8080) | `admin` / `admin`         |
| PostgreSQL        | `psql -h localhost -p 5432 -U airflow`  | password: `airflow`       |
| FastAPI Backend   | [http://localhost:8000/docs](http://localhost:8000/docs)| —                         |
| Frontend Web UI   | [http://localhost:3000](http://localhost:3000) | —                         |

## Quản lý services

### Lệnh Make cơ bản

```bash
make up          # Khởi động tất cả services (detached)
make down        # Dừng containers (giữ nguyên data)
make ps          # Xem trạng thái containers
make logs        # Xem logs toàn bộ services (Ctrl+C để thoát)
make clean       # Dừng + xóa volumes + xóa thư mục data/
```

### Khởi động từng layer

```bash
make up-storage  # Chỉ MinIO + StarRocks
make up-airflow  # Chỉ PostgreSQL + Airflow
make up-app      # Chỉ FastAPI + Frontend
```

## Đọc logs từng service

```bash
# Logs của một service cụ thể
make log-service SVC=minio
make log-service SVC=starrocks
make log-service SVC=airflow-webserver
make log-service SVC=airflow-scheduler
make log-service SVC=postgres
make log-service SVC=fastapi
make log-service SVC=frontend

# Hoặc dùng docker compose trực tiếp
docker compose logs -f minio            # MinIO
docker compose logs -f starrocks         # StarRocks
docker compose logs -f airflow-webserver # Airflow Web
docker compose logs -f airflow-scheduler # Airflow Scheduler
docker compose logs -f postgres          # PostgreSQL
docker compose logs -f fastapi           # FastAPI
docker compose logs -f frontend          # Frontend

# Xem N dòng cuối cùng
docker compose logs --tail=100 starrocks
```

## Health Check

```bash
bash health_check.sh
```

Output mẫu:

```
╔══════════════════════════════════════════════════╗
║       DataStack Compass — Health Check          ║
╚══════════════════════════════════════════════════╝

▸ Storage Layer
  MinIO (S3 API)         PASS
  MinIO (Console)        PASS

▸ OLAP Layer
  StarRocks (MySQL)      PASS
  StarRocks (FE HTTP)    PASS

▸ Orchestration Layer
  Airflow Webserver      PASS
  Postgres (Airflow DB)  PASS

▸ Application Layer
  FastAPI Backend        PASS
  Frontend (React)       PASS

──────────────────────────────────────────────────
  Result: 8/8 services healthy ✓

▸ Docker Memory Usage

CONTAINER                  MEM USAGE / LIMIT     MEM %
datastack-starrocks        1.82GiB / 4GiB        45.50%
datastack-airflow-web...   412MiB / 1GiB         40.23%
datastack-airflow-sch...   380MiB / 1GiB         37.11%
datastack-fastapi          120MiB / 512MiB       23.43%
datastack-minio            128MiB / 512MiB       25.00%
datastack-postgres         42MiB / 256MiB        16.41%
datastack-frontend         20MiB / 128MiB        15.62%
```

## Giới hạn RAM

| Service            | Memory Limit |
| ------------------ | ------------ |
| MinIO              | 512 MB       |
| StarRocks          | 4 GB         |
| PostgreSQL         | 256 MB       |
| Airflow Webserver  | 1 GB         |
| Airflow Scheduler  | 1 GB         |
| FastAPI Backend    | 512 MB       |
| Frontend           | 128 MB       |
| **Tổng tối đa**   | **~7.4 GB**  |

## Cấu trúc dữ liệu local

```
infra/docker/
├── docker-compose.yml
├── Makefile
├── health_check.sh
├── README.md
└── data/                    ← được tạo tự động khi chạy
    ├── minio/               ← Object storage (bronze/silver/gold)
    ├── starrocks/           ← OLAP data
    └── postgres/            ← Airflow metadata DB
```

> Thư mục `data/` đã được thêm vào `.gitignore`. Chạy `make clean` sẽ xóa
> toàn bộ dữ liệu local.

## Troubleshooting

### StarRocks khởi động chậm
StarRocks cần 60–90 giây để FE và BE sẵn sàng. Health check sẽ báo FAIL nếu
chạy quá sớm — hãy đợi và thử lại.

### Port đã bị chiếm
```bash
# Kiểm tra port đang được dùng bởi process nào
lsof -i :9030    # Linux / macOS
netstat -ano | findstr :9030   # Windows
```

### Xóa sạch và bắt đầu lại
```bash
make clean
make up
```
