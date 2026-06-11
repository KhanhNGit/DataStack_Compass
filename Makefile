.PHONY: test-unit test-integration test-all

# Chạy unit tests (thường không cần database, network, hay docker dependencies)
test-unit:
	pytest tests/unit/ -v

# Chạy integration tests (cần khởi động Docker Compose stack trước)
test-integration:
	pytest tests/integration/ -v -m integration

# Chạy toàn bộ bộ test
test-all:
	pytest tests/ -v
