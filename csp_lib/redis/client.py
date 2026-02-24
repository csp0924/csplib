# =============== Redis - Client ===============
#
# 異步 Redis 客戶端封裝
#
# 基於 redis.asyncio 提供連線管理與基本操作。
# 支援 Standalone / Sentinel 模式。

from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from redis.asyncio import Redis
from redis.asyncio.sentinel import Sentinel

from csp_lib.core import get_logger

if TYPE_CHECKING:
    from csp_lib.redis.config import RedisConfig

logger = get_logger(__name__)


# ================ TLS 配置 ================


@dataclass(frozen=True, slots=True)
class TLSConfig:
    """
    TLS 連線配置

    用於配置 Redis 的 TLS/SSL 連線參數。

    Attributes:
        ca_certs: CA 憑證檔案路徑（必填）
        certfile: 客戶端憑證檔案路徑（雙向 TLS 用，選填）
        keyfile: 客戶端私鑰檔案路徑（雙向 TLS 用，選填）
        cert_reqs: 憑證驗證模式（預設 "required"）
            - "required": 必須驗證伺服器憑證
            - "optional": 可選驗證
            - "none": 不驗證

    Example:
        ```python
        # 單向 TLS（僅驗證伺服器）
        tls = TLSConfig(ca_certs="/path/to/ca.crt")

        # 雙向 TLS（mTLS）
        tls = TLSConfig(
            ca_certs="/path/to/ca.crt",
            certfile="/path/to/client.crt",
            keyfile="/path/to/client.key",
        )
        ```
    """

    ca_certs: str
    certfile: str | None = None
    keyfile: str | None = None
    cert_reqs: Literal["required", "optional", "none"] = "required"

    def __post_init__(self) -> None:
        """驗證配置一致性"""
        # certfile 和 keyfile 必須同時提供或同時不提供
        if (self.certfile is None) != (self.keyfile is None):
            raise ValueError("certfile 和 keyfile 必須同時提供（雙向 TLS）或同時不提供（單向 TLS）")

    def to_ssl_context(self) -> ssl.SSLContext:
        """
        建立 SSLContext

        Returns:
            配置好的 ssl.SSLContext 實例
        """
        # 映射 cert_reqs 到 ssl 常數
        cert_reqs_map = {
            "required": ssl.CERT_REQUIRED,
            "optional": ssl.CERT_OPTIONAL,
            "none": ssl.CERT_NONE,
        }

        context = ssl.create_default_context(cafile=self.ca_certs)
        context.check_hostname = self.cert_reqs == "required"
        context.verify_mode = cert_reqs_map[self.cert_reqs]

        # 載入客戶端憑證（雙向 TLS）
        if self.certfile and self.keyfile:
            context.load_cert_chain(certfile=self.certfile, keyfile=self.keyfile)

        return context


# ================ Redis Client ================


class RedisClient:
    """
    異步 Redis 客戶端封裝

    提供連線管理與常用操作的封裝，簡化 Redis 互動。
    支援 Standalone 與 Sentinel 兩種模式。

    Attributes:
        _config: Redis 連線配置（使用 from_config 時）
        _host: Redis 主機（直接建構時）
        _port: Redis 連接埠
        _password: 密碼
        _tls_config: TLS 配置
        _socket_timeout: Socket 讀寫超時（秒）
        _socket_connect_timeout: Socket 連線超時（秒）
        _client: redis.asyncio.Redis 實例
        _sentinel: Sentinel 實例（Sentinel 模式時）

    Example:
        ```python
        # 方式一：直接建構（Standalone）
        client = RedisClient(host="localhost", port=6379)
        await client.connect()

        # 方式二：使用 Config（推薦）
        from csp_lib.redis import RedisClient, RedisConfig, TLSConfig

        config = RedisConfig(
            host="localhost",
            port=6379,
            password="secret",
            tls_config=TLSConfig(ca_certs="/path/to/ca.crt"),
        )
        client = RedisClient.from_config(config)
        await client.connect()

        # 方式三：Sentinel 模式
        config = RedisConfig(
            sentinels=(("sentinel1", 26379), ("sentinel2", 26379)),
            sentinel_master="mymaster",
            password="redis_password",
        )
        client = RedisClient.from_config(config)
        await client.connect()
        ```
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        password: str | None = None,
        tls_config: TLSConfig | None = None,
        socket_timeout: float | None = None,
        socket_connect_timeout: float | None = None,
    ) -> None:
        """
        初始化 Redis 客戶端（Standalone 模式）

        若需使用 Sentinel 模式，請改用 RedisClient.from_config()。

        Args:
            host: Redis 主機位址
            port: Redis 連接埠
            password: 密碼（選填）
            tls_config: TLS 配置（選填，啟用 TLS 時必須提供）
            socket_timeout: Socket 讀寫超時秒數（選填）
            socket_connect_timeout: Socket 連線超時秒數（選填）
        """
        self._config: RedisConfig | None = None
        self._host = host
        self._port = port
        self._password = password
        self._tls_config = tls_config
        self._socket_timeout = socket_timeout
        self._socket_connect_timeout = socket_connect_timeout
        self._retry_on_timeout = False
        self._client: Redis | None = None
        self._sentinel: Sentinel | None = None

    @classmethod
    def from_config(cls, config: "RedisConfig") -> "RedisClient":
        """
        從 RedisConfig 建立客戶端

        根據配置自動選擇 Standalone 或 Sentinel 模式。

        Args:
            config: Redis 連線配置

        Returns:
            配置好的 RedisClient 實例

        Example:
            ```python
            config = RedisConfig(
                sentinels=(("sentinel1", 26379),),
                sentinel_master="mymaster",
                password="secret",
            )
            client = RedisClient.from_config(config)
            await client.connect()
            ```
        """
        instance = cls.__new__(cls)
        instance._config = config
        instance._host = config.host
        instance._port = config.port
        instance._password = config.password
        instance._tls_config = config.tls_config
        instance._socket_timeout = config.socket_timeout
        instance._socket_connect_timeout = config.socket_connect_timeout
        instance._retry_on_timeout = config.retry_on_timeout
        instance._client = None
        instance._sentinel = None
        return instance

    @property
    def is_connected(self) -> bool:
        """是否已連線"""
        return self._client is not None

    @property
    def is_sentinel_mode(self) -> bool:
        """是否為 Sentinel 模式"""
        return self._config is not None and self._config.is_sentinel_mode

    async def connect(self) -> None:
        """
        建立 Redis 連線

        根據配置自動選擇 Standalone 或 Sentinel 模式連線。

        Raises:
            ConnectionError: 連線失敗
        """
        if self._client is not None:
            return

        if self.is_sentinel_mode:
            await self._connect_sentinel()
        else:
            await self._connect_standalone()

    async def _connect_standalone(self) -> None:
        """Standalone 模式連線"""
        kwargs: dict[str, Any] = {
            "host": self._host,
            "port": self._port,
            "decode_responses": True,
        }

        if self._password:
            kwargs["password"] = self._password

        if self._socket_timeout is not None:
            kwargs["socket_timeout"] = self._socket_timeout

        if self._socket_connect_timeout is not None:
            kwargs["socket_connect_timeout"] = self._socket_connect_timeout

        if self._retry_on_timeout:
            kwargs["retry_on_timeout"] = True

        # TLS 配置
        if self._tls_config:
            kwargs["ssl"] = self._tls_config.to_ssl_context()

        self._client = Redis(**kwargs)
        await self._client.ping()
        logger.info(f"Redis 已連線 (Standalone): {self._host}:{self._port} (TLS: {self._tls_config is not None})")

    async def _connect_sentinel(self) -> None:
        """Sentinel 模式連線"""
        if self._config is None:
            raise RuntimeError("Sentinel 模式需使用 from_config() 建立")

        # Sentinel 連線參數
        sentinel_kwargs: dict[str, Any] = {
            "decode_responses": True,
        }

        if self._config.sentinel_password:
            sentinel_kwargs["password"] = self._config.sentinel_password

        if self._socket_timeout is not None:
            sentinel_kwargs["socket_timeout"] = self._socket_timeout

        if self._socket_connect_timeout is not None:
            sentinel_kwargs["socket_connect_timeout"] = self._socket_connect_timeout

        # TLS for Sentinel
        if self._tls_config:
            sentinel_kwargs["ssl"] = self._tls_config.to_ssl_context()

        # 建立 Sentinel 連線
        self._sentinel = Sentinel(
            list(self._config.sentinels),  # type: ignore
            sentinel_kwargs=sentinel_kwargs,
        )

        # 取得 Master 連線參數
        master_kwargs: dict[str, Any] = {
            "decode_responses": True,
        }

        if self._password:
            master_kwargs["password"] = self._password

        if self._socket_timeout is not None:
            master_kwargs["socket_timeout"] = self._socket_timeout

        if self._socket_connect_timeout is not None:
            master_kwargs["socket_connect_timeout"] = self._socket_connect_timeout

        if self._retry_on_timeout:
            master_kwargs["retry_on_timeout"] = True

        if self._tls_config:
            master_kwargs["ssl"] = self._tls_config.to_ssl_context()

        # 取得 Master
        self._client = self._sentinel.master_for(
            self._config.sentinel_master,  # type: ignore
            **master_kwargs,
        )

        await self._client.ping()
        logger.info(
            f"Redis 已連線 (Sentinel): master={self._config.sentinel_master} (TLS: {self._tls_config is not None})"
        )

    async def disconnect(self) -> None:
        """關閉 Redis 連線"""
        if self._client is None:
            return

        await self._client.aclose()
        self._client = None
        logger.info("Redis 已斷線")

    # ================ Hash 操作 ================

    async def hset(self, name: str, mapping: dict[str, Any]) -> int:
        """
        設定 Hash 欄位

        Args:
            name: Hash key 名稱
            mapping: 欄位與值的字典

        Returns:
            新增的欄位數量
        """
        if not self._client:
            raise ConnectionError("Redis 尚未連線")

        # 將所有值轉為字串（Redis Hash 值必須是字串）
        str_mapping = {k: json.dumps(v) if not isinstance(v, str) else v for k, v in mapping.items()}
        return await self._client.hset(name, mapping=str_mapping)

    async def hgetall(self, name: str) -> dict[str, Any]:
        """
        取得 Hash 所有欄位

        Args:
            name: Hash key 名稱

        Returns:
            欄位與值的字典
        """
        if not self._client:
            raise ConnectionError("Redis 尚未連線")

        result = await self._client.hgetall(name)
        # 嘗試解析 JSON
        parsed = {}
        for k, v in result.items():
            try:
                parsed[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                parsed[k] = v
        return parsed

    async def hdel(self, name: str, *keys: str) -> int:
        """
        刪除 Hash 欄位

        Args:
            name: Hash key 名稱
            keys: 要刪除的欄位名稱

        Returns:
            刪除的欄位數量
        """
        if not self._client:
            raise ConnectionError("Redis 尚未連線")
        return await self._client.hdel(name, *keys)

    # ================ String 操作 ================

    async def set(self, name: str, value: str, ex: int | None = None) -> bool:
        """
        設定字串值

        Args:
            name: Key 名稱
            value: 值
            ex: 過期時間（秒）

        Returns:
            是否成功
        """
        if not self._client:
            raise ConnectionError("Redis 尚未連線")
        result = await self._client.set(name, value, ex=ex)
        return result is True

    async def get(self, name: str) -> str | None:
        """
        取得字串值

        Args:
            name: Key 名稱

        Returns:
            值，不存在時返回 None
        """
        if not self._client:
            raise ConnectionError("Redis 尚未連線")
        return await self._client.get(name)

    # ================ Set 操作 ================

    async def sadd(self, name: str, *values: str) -> int:
        """
        新增 Set 成員

        Args:
            name: Set key 名稱
            values: 要新增的值

        Returns:
            新增的成員數量
        """
        if not self._client:
            raise ConnectionError("Redis 尚未連線")
        return await self._client.sadd(name, *values)

    async def srem(self, name: str, *values: str) -> int:
        """
        移除 Set 成員

        Args:
            name: Set key 名稱
            values: 要移除的值

        Returns:
            移除的成員數量
        """
        if not self._client:
            raise ConnectionError("Redis 尚未連線")
        return await self._client.srem(name, *values)

    async def smembers(self, name: str) -> set[str]:
        """
        取得 Set 所有成員

        Args:
            name: Set key 名稱

        Returns:
            成員集合
        """
        if not self._client:
            raise ConnectionError("Redis 尚未連線")
        return await self._client.smembers(name)

    # ================ Pub/Sub ================

    async def publish(self, channel: str, message: str) -> int:
        """
        發布訊息到 channel

        Args:
            channel: Channel 名稱
            message: 訊息內容（字串）

        Returns:
            接收到訊息的訂閱者數量
        """
        if not self._client:
            raise ConnectionError("Redis 尚未連線")
        return await self._client.publish(channel, message)

    # ================ Key 操作 ================

    async def delete(self, *names: str) -> int:
        """
        刪除 Key

        Args:
            names: 要刪除的 Key 名稱

        Returns:
            刪除的 Key 數量
        """
        if not self._client:
            raise ConnectionError("Redis 尚未連線")
        return await self._client.delete(*names)

    async def exists(self, *names: str) -> int:
        """
        檢查 Key 是否存在

        Args:
            names: 要檢查的 Key 名稱

        Returns:
            存在的 Key 數量
        """
        if not self._client:
            raise ConnectionError("Redis 尚未連線")
        return await self._client.exists(*names)

    async def expire(self, name: str, seconds: int) -> bool:
        """
        設定 Key 過期時間

        Args:
            name: Key 名稱
            seconds: 過期時間（秒）

        Returns:
            是否成功設定（Key 存在時返回 True）
        """
        if not self._client:
            raise ConnectionError("Redis 尚未連線")
        return await self._client.expire(name, seconds)

    # ================ Key Pattern 操作 ================

    async def keys(self, pattern: str) -> list[str]:
        """
        取得匹配 pattern 的 Key 列表

        Args:
            pattern: 匹配模式（e.g., "monitor:default:nodes:*"）

        Returns:
            匹配的 Key 列表
        """
        if not self._client:
            raise ConnectionError("Redis 尚未連線")
        return await self._client.keys(pattern)

    # ================ Context Manager ================

    async def __aenter__(self) -> "RedisClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.disconnect()


__all__ = [
    "RedisClient",
    "TLSConfig",
]
