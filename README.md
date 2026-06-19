# DataStack Compass 🧭

**DataStack Compass** là một nền tảng quản trị rủi ro phiên bản phần mềm (Software Version Risk Governance). Nền tảng tự động thu thập, xử lý, lưu trữ và hiển thị thông tin Release Notes, CVE (lỗ hổng bảo mật), Breaking Changes và thay đổi License từ các công cụ Data Stack cốt lõi (Kafka, Flink, Spark, v.v.).

Kiến trúc cốt lõi sử dụng mô hình **Data Lakehouse** hiện đại với sự kết hợp của **Apache Iceberg**, **MinIO**, và **StarRocks**.

---

## 🏗️ Kiến trúc Hệ thống
- **Orchestration**: Apache Airflow điều phối luồng dữ liệu (chạy local qua LocalExecutor/Standalone).
- **Processing**: PySpark chạy local mode `local[*]` + Great Expectations kiểm tra Data Quality.
- **Storage**: MinIO lưu trữ Object Storage (S3-compatible) đóng vai trò làm Data Lake với định dạng **Apache Iceberg** (không yêu cầu Hive Metastore).
- **OLAP Layer**: StarRocks truy vấn trực tiếp vào MinIO (thông qua External Catalog Iceberg) đem lại tốc độ siêu nhanh.
- **Backend API**: FastAPI cung cấp RESTful endpoints.
- **Frontend**: ReactJS (Vite + TailwindCSS + Recharts) hiển thị Dashboard.

---

## 🚀 Hướng dẫn Chạy Toàn Bộ Dự Án (Từ Đầu Đến Cuối)

Sau khi hạ tầng cơ sở và Iceberg Catalog đã được khởi tạo (như việc chạy `init_starrocks.py`), dưới đây là toàn bộ các bước để kích hoạt mọi tính năng của hệ thống.

### Bước 1: Khởi động Hạ tầng Docker (Infrastructure)
Bật toàn bộ các dịch vụ lõi bao gồm Data Lake (MinIO), OLAP (StarRocks), Database (Postgres), và hệ thống quản trị Pipeline (Apache Airflow):
```bash
cd infra/docker
docker-compose up -d --build
```
*(Cờ `--build` sẽ tự động tạo một Docker Image tuỳ chỉnh cho Airflow có chứa sẵn Java và PySpark để chạy `spark-submit`).*

### Bước 2: Kích hoạt Môi trường Ảo (Python Virtual Environment)
Kích hoạt `.venv` nếu bạn muốn chạy thủ công các test nội bộ (FastAPI, Great Expectations, v.v.):
```bash
source .venv/Scripts/activate
```

### Bước 3: Khởi chạy Data Pipeline (Apache Airflow qua Docker)
Apache Airflow sẽ tự động lấy dữ liệu thô (Raw) từ GitHub, NVD API, RSS Feeds, sau đó dùng PySpark để transform và lưu vào Iceberg (Silver & Gold).

1. Truy cập Airflow UI tại: **http://localhost:8080**
2. Đăng nhập với tài khoản mặc định: 
   - **Username**: admin
   - **Password**: admin
3. **Kích hoạt các DAGs sau theo thứ tự:**
   - Bật (Unpause) và trigger DAG **`ingest_software_releases`**: Lấy thông tin releases từ Github.
   - Bật và trigger DAG **`ingest_cves`**: Lấy danh sách lỗ hổng bảo mật.
   - Bật và trigger DAG **`ingest_tech_blogs`**: Thu thập RSS feeds.
   - Sau khi các DAG trên chạy xong, kích hoạt DAG **`master_data_pipeline`**. DAG này sẽ gọi PySpark (`build_gold_summary.py`) tổng hợp dữ liệu Gold Layer và cập nhật StarRocks statistics.

### Bước 4: Khởi chạy Backend API (FastAPI)
Mở một terminal mới, kích hoạt `.venv` và khởi động API server:
```powershell
cd api
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
- Truy cập API Swagger UI để test dữ liệu: **http://localhost:8000/docs**

### Bước 5: Khởi chạy Giao diện Frontend (React)
Mở một terminal mới (yêu cầu cài sẵn Node.js 18+):
```powershell
cd frontend
npm install
npm run dev
```
- Mở trình duyệt và trải nghiệm Dashboard quản trị rủi ro tại: **http://localhost:3000** (hoặc port được cung cấp bởi Vite như 5173).

---

## 🔍 Đánh giá Kỹ Thuật (System Evaluation)

Dựa trên việc scan toàn bộ kiến trúc codebase, dự án được triển khai cực kỳ chuẩn chỉnh theo chuẩn công nghiệp thực tế:

1. **Thiết kế Data Lakehouse Tối Ưu**: 
   - Việc loại bỏ Hive Metastore (HMS) ở môi trường local và dùng thẳng Iceberg Hadoop Catalog trỏ vào MinIO là một nước đi rất thông minh. Nó giảm hẳn gánh nặng RAM/CPU cho Docker Compose nhưng vẫn giữ nguyên trải nghiệm phân tích Data Lakehouse thực tế bằng StarRocks.
   - Tách biệt rõ 3 lớp Bronze (Raw), Silver (Cleaned/Iceberg), Gold (Aggregated/Iceberg).
   
2. **Khả năng Mở Rộng & Idempotent**:
   - Các logic PySpark và Airflow DAG sử dụng lệnh `MERGE INTO` thuần của Spark SQL. Nhờ vậy, pipelines đạt chuẩn *Idempotent* (chạy lại bao nhiêu lần cũng không sinh dữ liệu rác/trùng lặp). Codebase hoàn toàn agnostic, nếu sau này muốn đổi lại sang kiến trúc khác trên Production thì không cần đổi một dòng logic nào của DAG.

3. **Tự Động Hóa Quản Trị Dữ Liệu**:
   - Sử dụng Airflow External Task Sensor để master pipeline biết khi nào các DAG ingestion hoàn thành.
   - Cấu hình Great Expectations trực tiếp chặn lỗi data (Data Quality) từ sớm.
   - Có cơ chế dọn dẹp data tự động thông qua `expire_snapshots` để giải phóng dung lượng.

4. **Trải nghiệm Frontend / Backend**:
   - Cấu trúc REST API rất rõ ràng với FastAPI, tối ưu hóa qua Connection Pooling `DBUtils` giúp StarRocks không bị quá tải session. 
   - Frontend Vite + Tailwind giúp Hot-Reload nhanh, đồ thị Recharts kết nối API trơn tru qua cấu hình Proxy.

---
**💡 Tips cho Quá trình Phát triển (Development):**
- **Sửa Data Model**: Nếu bạn thay đổi Schema, hãy vào `storage/delta/schemas.py` (Mặc dù thư mục tên delta, logic hiện dùng chung cho cả Iceberg) để điều chỉnh PySpark schema.
- **Log của Spark**: Để xem log quá trình xử lý, hãy theo dõi trực tiếp output của Task trong giao diện Airflow (phần Logs).
- **Kiểm tra dữ liệu OLAP**: Có thể dùng DBeaver hoặc MySQL Client kết nối tới cổng `9030` của localhost bằng user `root` để query trực tiếp vào `minio_iceberg_catalog.silver.silver_releases` giúp debug dữ liệu siêu nhanh.
