# =============== Tests - MongoDB Config ===============
#
# 測試 MongoConfig 與 create_mongo_client()

import pytest

from csp_lib.mongo import MongoConfig, create_mongo_client


class TestMongoConfig:
    """MongoConfig 單元測試"""

    def test_standalone_mode_default(self) -> None:
        """測試 Standalone 模式預設值"""
        config = MongoConfig()

        assert config.host == "localhost"
        assert config.port == 27017
        assert config.replica_hosts is None
        assert config.replica_set is None
        assert config.is_replica_set_mode is False

    def test_standalone_mode_custom(self) -> None:
        """測試 Standalone 模式自訂值"""
        config = MongoConfig(
            host="mongo.example.com",
            port=27018,
            username="admin",
            password="secret",
            auth_source="admin",
        )

        assert config.host == "mongo.example.com"
        assert config.port == 27018
        assert config.username == "admin"
        assert config.password == "secret"
        assert config.auth_source == "admin"
        assert config.is_replica_set_mode is False

    def test_replica_set_mode(self) -> None:
        """測試 Replica Set 模式"""
        config = MongoConfig(
            replica_hosts=("rs1:27017", "rs2:27017", "rs3:27017"),
            replica_set="myReplicaSet",
            username="user",
            password="password",
        )

        assert config.is_replica_set_mode is True
        assert config.replica_hosts == ("rs1:27017", "rs2:27017", "rs3:27017")
        assert config.replica_set == "myReplicaSet"

    def test_replica_set_requires_both_params(self) -> None:
        """測試 Replica Set 模式必須同時提供 replica_hosts 和 replica_set"""
        with pytest.raises(ValueError, match="同時提供"):
            MongoConfig(
                replica_hosts=("rs1:27017",),
                replica_set=None,
            )

        with pytest.raises(ValueError, match="同時提供"):
            MongoConfig(
                replica_hosts=None,
                replica_set="myReplicaSet",
            )

    def test_tls_config(self) -> None:
        """測試 TLS 配置"""
        config = MongoConfig(
            host="localhost",
            port=27017,
            tls=True,
            tls_cert_key_file="/path/to/client.pem",
            tls_ca_file="/path/to/ca.crt",
            tls_allow_invalid_hostnames=True,
        )

        assert config.tls is True
        assert config.tls_cert_key_file == "/path/to/client.pem"
        assert config.tls_ca_file == "/path/to/ca.crt"
        assert config.tls_allow_invalid_hostnames is True

    def test_x509_auth(self) -> None:
        """測試 X.509 驗證配置"""
        config = MongoConfig(
            host="localhost",
            tls=True,
            tls_cert_key_file="/path/to/client.pem",
            tls_ca_file="/path/to/ca.crt",
            auth_mechanism="MONGODB-X509",
        )

        assert config.auth_mechanism == "MONGODB-X509"

    def test_timeout_settings(self) -> None:
        """測試 Timeout 設定"""
        config = MongoConfig(
            host="localhost",
            server_selection_timeout_ms=5000,
            connect_timeout_ms=3000,
            socket_timeout_ms=10000,
        )

        assert config.server_selection_timeout_ms == 5000
        assert config.connect_timeout_ms == 3000
        assert config.socket_timeout_ms == 10000

    def test_direct_connection(self) -> None:
        """測試直連設定"""
        # Standalone 預設直連
        config_standalone = MongoConfig(host="localhost")
        assert config_standalone.direct_connection is True

        # Replica Set 應設為 False
        config_replica = MongoConfig(
            replica_hosts=("rs1:27017",),
            replica_set="myReplicaSet",
            direct_connection=False,
        )
        assert config_replica.direct_connection is False


class TestCreateMongoClient:
    """create_mongo_client() 測試"""

    def test_create_standalone_client(self) -> None:
        """測試建立 Standalone 客戶端"""
        config = MongoConfig(
            host="localhost",
            port=27017,
            server_selection_timeout_ms=1000,
        )

        client = create_mongo_client(config)

        # Motor client 應該被建立
        assert client is not None
        # 關閉客戶端
        client.close()

    def test_create_client_with_timeout(self) -> None:
        """測試 Timeout 設定傳遞"""
        config = MongoConfig(
            host="localhost",
            port=27017,
            server_selection_timeout_ms=500,
            connect_timeout_ms=500,
            socket_timeout_ms=1000,
        )

        client = create_mongo_client(config)
        assert client is not None
        client.close()

    def test_create_replica_set_client(self) -> None:
        """測試建立 Replica Set 客戶端（不連線）"""
        config = MongoConfig(
            replica_hosts=("rs1:27017", "rs2:27017"),
            replica_set="testRS",
            server_selection_timeout_ms=100,
        )

        client = create_mongo_client(config)
        assert client is not None
        client.close()
