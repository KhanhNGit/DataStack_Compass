"""
Connector to download cvelistV5 from Github and upload to MinIO Bronze.
"""
import os
import io
import json
import zipfile
import urllib.request
import logging
from datetime import datetime

import boto3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cvelist_connector")

CVELIST_ZIP_URL = "https://github.com/CVEProject/cvelistV5/archive/refs/heads/main.zip"
TMP_JSONL_PATH = "/tmp/cvelistV5.jsonl"

def upload_to_minio(file_path: str, bucket_name: str, object_name: str):
    logger.info(f"Uploading {file_path} to s3://{bucket_name}/{object_name}")
    s3_client = boto3.client(
        's3',
        endpoint_url=os.environ.get("MINIO_ENDPOINT", "http://minio:9000"),
        aws_access_key_id=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
        region_name="us-east-1"
    )
    
    try:
        s3_client.head_bucket(Bucket=bucket_name)
    except:
        s3_client.create_bucket(Bucket=bucket_name)

    s3_client.upload_file(file_path, bucket_name, object_name)
    logger.info("Upload complete.")

def main():
    logger.info(f"Downloading cvelistV5 from {CVELIST_ZIP_URL}")
    request = urllib.request.Request(CVELIST_ZIP_URL, headers={'User-Agent': 'Mozilla/5.0'})
    
    try:
        with urllib.request.urlopen(request) as response:
            with open("/tmp/cvelistV5_main.zip", "wb") as out_file:
                while True:
                    chunk = response.read(8192 * 1024)
                    if not chunk:
                        break
                    out_file.write(chunk)
        logger.info("Downloaded successfully.")
    except Exception as e:
        logger.error(f"Download failed: {e}")
        raise
    
    logger.info("Extracting JSON files to JSONL format...")
    count = 0
    with zipfile.ZipFile("/tmp/cvelistV5_main.zip", "r") as z:
        with open(TMP_JSONL_PATH, "w", encoding="utf-8") as out_jsonl:
            for file_info in z.infolist():
                if file_info.filename.endswith(".json") and "/cves/" in file_info.filename:
                    if "delta" in file_info.filename or "deltaCves" in file_info.filename:
                        continue
                    try:
                        with z.open(file_info) as f:
                            data = json.load(f)
                            # Add a crawled_at timestamp
                            data["_crawled_at"] = datetime.utcnow().isoformat()
                            out_jsonl.write(json.dumps(data) + "\n")
                            count += 1
                            if count % 10000 == 0:
                                logger.info(f"Processed {count} CVEs...")
                    except Exception as e:
                        logger.warning(f"Error parsing {file_info.filename}: {e}")
                        
    logger.info(f"Finished extracting {count} CVEs to {TMP_JSONL_PATH}")
    
    bucket = os.environ.get("MINIO_BUCKET_BRONZE", "compass-lake")
    # For delta table or spark read, we can place it in bronze/cvelist/
    object_name = "bronze/bronze_cves/cvelistV5.jsonl"
    
    upload_to_minio(TMP_JSONL_PATH, bucket, object_name)
    
    # Cleanup
    if os.path.exists(TMP_JSONL_PATH):
        os.remove(TMP_JSONL_PATH)
    if os.path.exists("/tmp/cvelistV5_main.zip"):
        os.remove("/tmp/cvelistV5_main.zip")
        
    logger.info("Cleanup completed. Connector done.")

if __name__ == "__main__":
    main()
