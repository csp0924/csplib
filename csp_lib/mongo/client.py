# =============== MongoDB - Client ===============
#
# MongoDB 連線配置與客戶端工廠
#
# 支援 Standalone / Replica Set 模式。

from __future__ import annotations

from dataclasses import dataclass

from motor.motor_asyncio import AsyncIOMotorClient

from csp_lib.core import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class MongoConfig:
    """
    MongoDB 連線配置

    支援兩種模式：
    1. Standalone: 單機模式，使用 host/port
    2. Replica Set: 副本集模式，使用 replica_hosts/replica_set

    當同時提供 replica_hosts 和 replica_set 時自動切換為 Replica Set 模式。

    Attributes:
        host: MongoDB 主機位址（Standalone 模式）
        port: MongoDB 連接埠（Standalone 模式）

        replica_hosts: 副本集主機列表 ["host1:27017", "host2:27017"]
        replica_set: 副本集名稱

        username: 使用者名稱
        password: 密碼
        auth_source: 驗證資料庫（預設 "admin"）
        auth_mechanism: 驗證機制（例如 "MONGODB-X509"）

        tls: 是否啟用 TLS
        tls_cert_key_file: 客戶端憑證檔案路徑（.pem）
        tls_ca_file: CA 憑證檔案路徑
        tls_allow_invalid_hostnames: 是否允許無效主機名

        direct_connection: 是否直連（Replica Set 設為 False）

        server_selection_timeout_ms: Server Selection 超時（毫秒）
        connect_timeout_ms: 連線超時（毫秒）
        socket_timeout_ms: Socket 讀寫超時（毫秒）

    Example:
        ```python
        # Standalone 模式
        config = MongoConfig(
            host="localhost",
            port=27017,
        )

        # Standalone + X.509 驗證
        config = MongoConfig(
            host="mongo.example.com",
            port=27017,
            tls=True,
            tls_cert_key_file="/path/to/client.pem",
            tls_ca_file="/path/to/ca.crt",
            auth_mechanism="MONGODB-X509",
        )

        # Replica Set 模式
        config = MongoConfig(
            replica_hosts=["rs1:27017", "rs2:27017", "rs3:27017"],
            replica_set="myReplicaSet",
            username="user",
            password="password",
        )
        ```
    """

    # Standalone
    host: str = "localhost"
    port: int = 27017

    # Replica Set 模式
    replica_hosts: tuple[str, ...] | None = None
    replica_set: str | None = None

    # Auth
    username: str | None = None
    password: str | None = None
    auth_source: str = "admin"
    auth_mechanism: str | None = None

    # TLS
    tls: bool = False
    tls_cert_key_file: str | None = None
    tls_ca_file: str | None = None
    tls_allow_invalid_hostnames: bool = False

    # Connection behavior
    direct_connection: bool = True

    # Timeout (毫秒)
    server_selection_timeout_ms: int | None = None
    connect_timeout_ms: int | None = None
    socket_timeout_ms: int | None = None

    def __post_init__(self) -> None:
        """驗證配置一致性"""
        # Replica Set 模式需同時提供 replica_hosts 和 replica_set
        if (self.replica_hosts is None) != (self.replica_set is None):
            raise ValueError("Replica Set 模式需同時提供 replica_hosts 和 replica_set")

    @property
    def is_replica_set_mode(self) -> bool:
        """是否為 Replica Set 模式"""
        return self.replica_hosts is not None and self.replica_set is not None


def create_mongo_client(config: MongoConfig) -> AsyncIOMotorClient:
    """
    根據配置建立 MongoDB 客戶端

    根據配置自動選擇 Standalone 或 Replica Set 模式。

    Args:
        config: MongoDB 連線配置

    Returns:
        配置好的 AsyncIOMotorClient 實例

    Example:
        ```python
        config = MongoConfig(
            host="localhost",
            port=27017,
            tls=True,
            tls_cert_key_file="/path/to/client.pem",
            tls_ca_file="/path/to/ca.crt",
            auth_mechanism="MONGODB-X509",
        )
        client = create_mongo_client(config)
        db = client["my_database"]
        ```
    """
    # 建立 URI
    if config.is_replica_set_mode:
        hosts = ",".join(config.replica_hosts)  # type: ignore
        uri = f"mongodb://{hosts}"
    else:
        uri = f"mongodb://{config.host}:{config.port}"

    # 連線參數
    kwargs: dict = {}

    # Replica Set
    if config.is_replica_set_mode:
        kwargs["replicaSet"] = config.replica_set
        kwargs["directConnection"] = False
    else:
        kwargs["directConnection"] = config.direct_connection

    # Auth (username/password in URI or authMechanism)
    if config.username and config.password:
        # URL encode credentials in URI
        from urllib.parse import quote_plus

        uri = f"mongodb://{quote_plus(config.username)}:{quote_plus(config.password)}@{uri.replace('mongodb://', '')}"
        kwargs["authSource"] = config.auth_source

    if config.auth_mechanism:
        kwargs["authMechanism"] = config.auth_mechanism

    # TLS
    if config.tls:
        kwargs["tls"] = True

        if config.tls_cert_key_file:
            kwargs["tlsCertificateKeyFile"] = config.tls_cert_key_file

        if config.tls_ca_file:
            kwargs["tlsCAFile"] = config.tls_ca_file

        if config.tls_allow_invalid_hostnames:
            kwargs["tlsAllowInvalidHostnames"] = True

    # Timeout
    if config.server_selection_timeout_ms is not None:
        kwargs["serverSelectionTimeoutMS"] = config.server_selection_timeout_ms

    if config.connect_timeout_ms is not None:
        kwargs["connectTimeoutMS"] = config.connect_timeout_ms

    if config.socket_timeout_ms is not None:
        kwargs["socketTimeoutMS"] = config.socket_timeout_ms

    client = AsyncIOMotorClient(uri, **kwargs)

    mode = "Replica Set" if config.is_replica_set_mode else "Standalone"
    logger.info(f"MongoDB 客戶端已建立 ({mode}): {uri.split('@')[-1] if '@' in uri else uri} (TLS: {config.tls})")

    return client


__all__ = [
    "MongoConfig",
    "create_mongo_client",
]
