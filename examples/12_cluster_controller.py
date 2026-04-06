"""
csp_lib Example 12: etcd Leader Election 與 ClusterController

展示內容：
  - EtcdConfig / ClusterConfig: 叢集配置設定
  - LeaderElector: 基於 etcd lease 的 leader 選舉狀態機
  - ClusterStatePublisher / ClusterStateSubscriber: Leader/Follower 間的 Redis 狀態同步
  - ClusterSnapshot: 叢集狀態快照資料結構
  - VirtualContextBuilder: 從 Redis 快取資料建構 StrategyContext（Follower 模式）
  - ClusterController: 中央編排器，自動切換 Leader/Follower 角色

架構圖：
  Instance A (Leader)                 Instance B (Follower)
  +---------------------------+       +---------------------------+
  | ClusterController         |       | ClusterController         |
  |  +- LeaderElector -----+  |       |  +- LeaderElector -----+  |
  |  |  state: LEADER      |  |       |  |  state: FOLLOWER    |  |
  |  +---------------------+  |       |  +---------------------+  |
  |  +- SystemController --+  |       |  +- SystemController --+  |
  |  |  live context       |  |       |  |  virtual context    |  |
  |  |  real command       |  |       |  |  no-op command      |  |
  |  +---------------------+  |       |  +---------------------+  |
  |  +- UnifiedManager ----+  |       |                           |
  |  |  Modbus connected   |  |       |  (devices disconnected)   |
  |  |  MongoDB/Redis sync |  |       |                           |
  |  +---------------------+  |       |                           |
  |  +- StatePublisher ----+  |       |  +- StateSubscriber ---+  |
  |  |  Redis <-- push     |  |       |  |  Redis --> poll     |  |
  |  +---------------------+  |       |  +---------------------+  |
  +---------------------------+       +---------------------------+
           |                                     ^
           |          etcd (election key)        |
           +-----> /csp/cluster/election <-------+
           |          Redis (state sync)         |
           +-----> cluster:ns:* keys  <----------+

容錯切換流程：
  1. Instance A 持有 lease，成為 LEADER
  2. Instance A lease 到期（網路分區或程序異常）
  3. Instance B 偵測到 key 被刪除，重新參與競選
  4. Instance B 贏得選舉，升格為 LEADER
  5. Instance B 啟動 UnifiedDeviceManager，切換至 live context
  6. Instance A（若重新連線）偵測到新 leader，降級為 FOLLOWER

注意：
  本範例使用 mock 物件模擬 etcd 與 Redis，無需外部服務即可執行。
  正式環境請替換為真正的 etcd (etcetra) 與 Redis (csp_lib.redis) 客戶端。

Run: uv run python examples/12_cluster_controller.py
"""

import asyncio
import json
import time
from collections import defaultdict

from csp_lib.cluster import (
    ClusterConfig,
    ClusterSnapshot,
    ElectionState,
    EtcdConfig,
    VirtualContextBuilder,
)
from csp_lib.controller.core import StrategyContext, SystemBase
from csp_lib.integration.schema import AggregateFunc, ContextMapping

# ============================================================
# Step 1: 叢集配置
# ============================================================


def demo_configuration():
    """展示 etcd 與叢集配置的設定方式。"""
    print("=" * 60)
    print("Demo 1: Cluster Configuration")
    print("=" * 60)

    # -- etcd 連線配置 --
    etcd_config = EtcdConfig(
        endpoints=["etcd-node1:2379", "etcd-node2:2379", "etcd-node3:2379"],
        username="csp_user",
        password="secret",
        ca_cert="/etc/ssl/etcd/ca.pem",
    )
    print(f"\n  etcd endpoints: {etcd_config.endpoints}")
    print(f"  etcd auth: user={etcd_config.username}")
    print(f"  etcd TLS: ca_cert={etcd_config.ca_cert}")

    # -- 叢集配置（Instance A）--
    config_a = ClusterConfig(
        instance_id="instance_a",
        etcd=etcd_config,
        namespace="site_bms",
        election_key="/csp/cluster/site_bms/election",
        lease_ttl=10,  # lease 存活時間（秒）
        state_publish_interval=1.0,  # 狀態發佈間隔（秒）
        state_ttl=30,  # Redis 狀態 key TTL（秒）
        failover_grace_period=2.0,  # 升格後等待設備產生資料的緩衝期（秒）
        device_ids=["pcs_01", "pcs_02", "bms_01"],  # 需同步的設備清單
        max_keepalive_failures=3,  # keepalive 連續失敗上限（超過則自我隔離）
        campaign_retry_delay=2.0,  # 競選失敗後重試延遲（秒）
    )

    print("\n  Instance A config:")
    print(f"    instance_id: {config_a.instance_id}")
    print(f"    namespace: {config_a.namespace}")
    print(f"    election_key: {config_a.election_key}")
    print(f"    lease_ttl: {config_a.lease_ttl}s")
    print(f"    failover_grace_period: {config_a.failover_grace_period}s")
    print(f"    device_ids: {config_a.device_ids}")

    # -- Redis key 產生（帶命名空間隔離）--
    print("\n  Redis keys (namespaced):")
    print(f"    leader:     {config_a.redis_key('leader')}")
    print(f"    mode_state: {config_a.redis_key('mode_state')}")
    print(f"    protection: {config_a.redis_key('protection_state')}")
    print(f"    command:    {config_a.redis_key('last_command')}")
    print(f"    channel:    {config_a.redis_channel('leader_change')}")


# ============================================================
# Step 2: 選舉狀態機
# ============================================================


def demo_election_state_machine():
    """展示 LeaderElector 的狀態轉移圖。"""
    print("\n" + "=" * 60)
    print("Demo 2: Election State Machine")
    print("=" * 60)

    print("\n  ElectionState values:")
    for state in ElectionState:
        print(f"    {state.name}: '{state.value}'")

    # 狀態轉移說明
    print("\n  State transitions:")
    print("    STOPPED -> CANDIDATE  (start, begin campaign)")
    print("    CANDIDATE -> LEADER   (won: key=instance_id)")
    print("    CANDIDATE -> FOLLOWER (lost: key=other_id)")
    print("    LEADER -> FOLLOWER    (lease expired / keepalive failed)")
    print("    FOLLOWER -> CANDIDATE (leader key deleted, re-campaign)")
    print("    * -> STOPPED          (stop)")

    # 基於 Lease 的選舉演算法
    print("\n  Lease-based algorithm:")
    print("    1. Grant lease (TTL=10s)")
    print("    2. Txn: IF key NOT EXISTS -> PUT(key, instance_id, lease)")
    print("    3. Success: LEADER + keepalive loop (interval=TTL/3)")
    print("    4. Failure: FOLLOWER + watch/poll for key deletion")
    print("    5. On demotion: callback -> switch to virtual context")


# ============================================================
# Step 3: 叢集狀態快照
# ============================================================


def demo_cluster_snapshot():
    """展示 ClusterSnapshot 資料結構。"""
    print("\n" + "=" * 60)
    print("Demo 3: ClusterSnapshot (State Sync Data)")
    print("=" * 60)

    # 建構一個模擬的快照（通常由 ClusterStateSubscriber 從 Redis 反序列化產生）
    snapshot = ClusterSnapshot(
        leader_id="instance_a",
        elected_at=time.time() - 120.0,
        base_modes=["pq"],
        override_names=["emergency_stop"],
        effective_mode="emergency_stop",
        triggered_rules=["over_voltage"],
        protection_was_modified=True,
        p_target=0.0,
        q_target=0.0,
        command_timestamp=time.time() - 1.0,
        auto_stop_active=True,
    )

    print(f"\n  Leader: {snapshot.leader_id}")
    print(f"  Elected at: {time.strftime('%H:%M:%S', time.localtime(snapshot.elected_at))}")
    print(f"  Base modes: {snapshot.base_modes}")
    print(f"  Override: {snapshot.override_names}")
    print(f"  Effective mode: {snapshot.effective_mode}")
    print(f"  Triggered rules: {snapshot.triggered_rules}")
    print(f"  Protection modified: {snapshot.protection_was_modified}")
    print(f"  Last command: P={snapshot.p_target}kW, Q={snapshot.q_target}kVar")
    print(f"  Auto-stop: {snapshot.auto_stop_active}")

    # -- 展示 Redis key 佈局 --
    print("\n  Redis key layout (published by leader):")
    ns = "site_bms"
    print(f"    cluster:{ns}:leader            -> JSON(instance_id, elected_at, hostname)")
    print(f"    cluster:{ns}:mode_state        -> HASH(base_modes, overrides, effective_mode)")
    print(f"    cluster:{ns}:protection_state  -> HASH(triggered_rules, was_modified)")
    print(f"    cluster:{ns}:last_command      -> HASH(p_target, q_target, timestamp)")
    print(f"    cluster:{ns}:auto_stop_active  -> '0' or '1'")
    print("    device:pcs_01:state            -> HASH(p_actual, q_actual, soc, ...)")


# ============================================================
# Step 4: 虛擬 Context 建構器（Follower 模式）
# ============================================================


def demo_virtual_context_builder():
    """展示 Follower 如何從 Redis 快取資料建構 StrategyContext。"""
    print("\n" + "=" * 60)
    print("Demo 4: VirtualContextBuilder (Follower Mode)")
    print("=" * 60)

    # -- 模擬從 Redis 快取讀取的設備狀態 --
    class MockSubscriber:
        @property
        def device_states(self):
            return {
                "pcs_01": {"soc": 65.0, "p_actual": -30.0, "q_actual": 5.0, "voltage": 378.5},
                "pcs_02": {"soc": 72.0, "p_actual": -28.0, "q_actual": 3.0, "voltage": 379.2},
                "bms_01": {"soc": 68.0, "voltage": 756.0, "temperature": 28.5},
            }

    subscriber = MockSubscriber()

    # -- 定義 context 映射（與 Leader 的 ContextBuilder 使用相同映射）--
    mappings = [
        # trait 模式: 聚合多台 PCS 的 SOC（取平均）
        ContextMapping(point_name="soc", context_field="soc", trait="pcs", aggregate=AggregateFunc.AVERAGE),
        # trait 模式: 聚合多台 PCS 的有功功率（加總）
        ContextMapping(point_name="p_actual", context_field="extra.total_p", trait="pcs", aggregate=AggregateFunc.SUM),
        # device_id 模式: 讀取特定 BMS 的電壓
        ContextMapping(point_name="voltage", context_field="extra.voltage", device_id="bms_01"),
        # device_id 模式: 讀取特定 BMS 的溫度
        ContextMapping(point_name="temperature", context_field="extra.temperature", device_id="bms_01"),
    ]

    # trait -> device_id 映射（告訴 builder "pcs" trait 下有哪些設備）
    trait_device_map = {
        "pcs": ["pcs_01", "pcs_02"],
    }

    builder = VirtualContextBuilder(
        subscriber=subscriber,
        mappings=mappings,
        system_base=SystemBase(p_base=500.0, q_base=200.0),
        trait_device_map=trait_device_map,
    )

    # -- 建構 context（介面與 ContextBuilder.build() 完全相同）--
    ctx: StrategyContext = builder.build()

    print("\n  VirtualContextBuilder.build() result:")
    print(f"    soc: {ctx.soc}  (avg of pcs_01=65, pcs_02=72)")
    print(f"    system_base: P={ctx.system_base.p_base}kW, Q={ctx.system_base.q_base}kVar")
    print(f"    extra.total_p: {ctx.extra.get('total_p')}  (sum of pcs_01=-30, pcs_02=-28)")
    print(f"    extra.voltage: {ctx.extra.get('voltage')}  (bms_01 direct read)")
    print(f"    extra.temperature: {ctx.extra.get('temperature')}  (bms_01 direct read)")

    # 關鍵概念：Leader 與 Follower 產生相同介面的 StrategyContext
    print("\n  Key insight:")
    print("    Leader:   ContextBuilder.build()         -> reads from live Modbus devices")
    print("    Follower: VirtualContextBuilder.build()  -> reads from Redis cache")
    print("    Both produce StrategyContext with the same interface")
    print("    -> StrategyExecutor.set_context_provider() swaps seamlessly")


# ============================================================
# Step 5: 模擬 etcd Leader 選舉
# ============================================================


class MockEtcdStore:
    """模擬 etcd key-value 儲存（僅供範例示範）。"""

    def __init__(self):
        self._store: dict[str, str] = {}
        self._leases: dict[int, float] = {}
        self._lease_counter = 0

    def lease_grant(self, ttl: int) -> int:
        """申請 lease，回傳 lease_id"""
        self._lease_counter += 1
        self._leases[self._lease_counter] = time.time() + ttl
        return self._lease_counter

    def txn_put_if_not_exists(self, key: str, value: str, lease_id: int) -> bool:
        """交易操作: 若 key 不存在則寫入（原子操作）"""
        if key not in self._store:
            self._store[key] = value
            return True
        return False

    def get(self, key: str) -> str | None:
        """讀取 key"""
        return self._store.get(key)

    def delete(self, key: str) -> None:
        """刪除 key（模擬 lease 到期）"""
        self._store.pop(key, None)


class MockRedisStore:
    """模擬 Redis 儲存（僅供範例示範）。"""

    def __init__(self):
        self._store: dict[str, str] = {}
        self._hashes: dict[str, dict[str, str]] = defaultdict(dict)
        self._channels: dict[str, list] = defaultdict(list)

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def hset(self, key: str, mapping: dict) -> None:
        self._hashes[key].update({k: str(v) for k, v in mapping.items()})

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self._hashes.get(key, {}))

    async def expire(self, key: str, ttl: int) -> None:
        pass  # TTL 未模擬

    async def publish(self, channel: str, message: str) -> None:
        self._channels[channel].append(message)


async def demo_leader_election_simulation():
    """模擬兩個實例透過 etcd 競選 leader 的過程。"""
    print("\n" + "=" * 60)
    print("Demo 5: Leader Election Simulation (2 Instances)")
    print("=" * 60)

    etcd = MockEtcdStore()
    election_key = "/csp/cluster/site_bms/election"

    # -- Instance A 先發起競選 --
    print("\n  [T=0] Instance A campaigns...")
    lease_a = etcd.lease_grant(ttl=10)
    result_a = etcd.txn_put_if_not_exists(election_key, "instance_a@host_a", lease_a)
    # key 不存在，寫入成功
    print(f"    Txn result: {'SUCCESS (key not exist, write ok)' if result_a else 'FAILED'}")
    print("    Instance A state: LEADER")
    print(f"    Election key value: {etcd.get(election_key)}")

    # -- Instance B 稍後競選（應失敗，因為 key 已存在）--
    print("\n  [T=1] Instance B campaigns...")
    lease_b = etcd.lease_grant(ttl=10)
    result_b = etcd.txn_put_if_not_exists(election_key, "instance_b@host_b", lease_b)
    # key 已存在，競選失敗
    print(f"    Txn result: {'SUCCESS' if result_b else 'FAILED (key exists, campaign lost)'}")
    current_leader = etcd.get(election_key)
    leader_id = current_leader.split("@")[0] if current_leader and "@" in current_leader else current_leader
    print(f"    Instance B state: FOLLOWER (following: {leader_id})")

    # -- 模擬 Instance A 故障（lease 到期 / 網路分區）--
    print("\n  [T=12] Instance A lease expires (network partition)...")
    etcd.delete(election_key)
    # etcd 自動刪除到期的 lease 所綁定的 key
    print(f"    Election key: {etcd.get(election_key)} (deleted by etcd)")

    # -- Instance B 偵測到 leader 消失，重新競選 --
    print("\n  [T=14] Instance B detects leader loss, re-campaigns...")
    lease_b2 = etcd.lease_grant(ttl=10)
    result_b2 = etcd.txn_put_if_not_exists(election_key, "instance_b@host_b", lease_b2)
    print(f"    Txn result: {'SUCCESS (new leader)' if result_b2 else 'FAILED'}")
    print("    Instance B state: LEADER")
    print(f"    Election key value: {etcd.get(election_key)}")

    # -- 新 leader 將狀態發佈至 Redis --
    print("\n  [T=14] New leader publishes state to Redis...")
    redis = MockRedisStore()
    config_b = ClusterConfig(
        instance_id="instance_b",
        etcd=EtcdConfig(),
        namespace="site_bms",
    )

    # Leader 定期透過 ClusterStatePublisher 發佈以下 key
    await redis.set(
        config_b.redis_key("leader"),
        json.dumps({"instance_id": "instance_b", "elected_at": time.time(), "hostname": "host_b"}),
    )
    await redis.hset(
        config_b.redis_key("mode_state"),
        {"base_modes": json.dumps(["pq"]), "overrides": json.dumps([]), "effective_mode": "pq"},
    )
    await redis.hset(
        config_b.redis_key("last_command"),
        {"p_target": "500.0", "q_target": "100.0", "timestamp": str(time.time())},
    )

    # -- Follower 端透過 ClusterStateSubscriber 輪詢讀取 --
    leader_raw = await redis.get(config_b.redis_key("leader"))
    leader_data = json.loads(leader_raw) if leader_raw else {}
    mode_data = await redis.hgetall(config_b.redis_key("mode_state"))
    cmd_data = await redis.hgetall(config_b.redis_key("last_command"))

    print(f"    Leader identity: {leader_data.get('instance_id')} @ {leader_data.get('hostname')}")
    print(f"    Mode state: effective={mode_data.get('effective_mode')}")
    print(f"    Last command: P={cmd_data.get('p_target')}kW, Q={cmd_data.get('q_target')}kVar")


# ============================================================
# Step 6: ClusterController 角色切換
# ============================================================


async def demo_cluster_controller_concept():
    """展示 ClusterController 的角色切換機制（概念說明）。"""
    print("\n" + "=" * 60)
    print("Demo 6: ClusterController Role Switching")
    print("=" * 60)

    # ClusterController 生命週期說明
    print("\n  ClusterController lifecycle:")
    print("    1. _on_start() [init as FOLLOWER]:")
    print("       - Create ClusterStateSubscriber (Redis poller)")
    print("       - Create VirtualContextBuilder (follower context)")
    print("       - Enter FOLLOWER mode:")
    print("         executor.set_context_provider(virtual_builder.build)")
    print("         executor.set_on_command(noop_handler)")
    print("       - Start SystemController (dry-run, strategy runs but no device write)")
    print("       - Start LeaderElector (begin etcd campaign)")
    print()
    # 升格為 LEADER
    print("    2. _handle_elected() [promoted to LEADER]:")
    print("       - Start UnifiedDeviceManager (Modbus, MongoDB, Redis)")
    print("       - Wait failover_grace_period (let devices produce data)")
    print("       - Switch to LEADER mode:")
    print("         executor.set_context_provider(live_context_builder.build)")
    print("         executor.set_on_command(real_command_router)")
    print("       - Start ClusterStatePublisher (push state to Redis)")
    print("       - Sync follower-cached mode state to live ModeManager")
    print("       - Call on_promoted() hook")
    print()
    # 降級為 FOLLOWER
    print("    3. _handle_demoted() [demoted to FOLLOWER]:")
    print("       - Stop ClusterStatePublisher")
    print("       - Switch to FOLLOWER mode (virtual context, no-op command)")
    print("       - Stop UnifiedDeviceManager (disconnect devices)")
    print("       - Call on_demoted() hook")
    print()
    # 完全停止
    print("    4. _on_stop() [shutdown]:")
    print("       - Stop LeaderElector (resign if leader)")
    print("       - Stop Publisher / SystemController / UnifiedManager")
    print("       - Stop Subscriber")

    # -- 核心機制：context provider 熱切換 --
    print("\n  Key mechanism: StrategyExecutor context provider hot-swap")
    print("  " + "-" * 50)

    # 模擬切換過程
    print("    [FOLLOWER] context_provider = VirtualContextBuilder.build")
    print("    [FOLLOWER] on_command       = noop_command_handler")
    print("        |")
    print("        v  _handle_elected()  -- promoted")
    print("    [LEADER]  context_provider = ContextBuilder.build")
    print("    [LEADER]  on_command       = CommandRouter.route")
    print("        |")
    print("        v  _handle_demoted()  -- demoted")
    print("    [FOLLOWER] context_provider = VirtualContextBuilder.build")
    print("    [FOLLOWER] on_command       = noop_command_handler")


# ============================================================
# Step 7: 健康檢查
# ============================================================


def demo_health_check():
    """展示 ClusterController 的健康檢查報告格式。"""
    print("\n" + "=" * 60)
    print("Demo 7: Health Check Report")
    print("=" * 60)

    # 模擬健康報告（ClusterController.health() 的回傳值）
    health_leader = {
        "role": "leader",
        "instance_id": "instance_a",
        "is_leader": True,
        "leader_id": "instance_a",
        "unified_manager_running": True,
        "system_controller_running": True,
    }

    health_follower = {
        "role": "follower",
        "instance_id": "instance_b",
        "is_leader": False,
        "leader_id": "instance_a",
        "unified_manager_running": False,
        "system_controller_running": True,
    }

    print("\n  Instance A (Leader) health:")
    for k, v in health_leader.items():
        print(f"    {k}: {v}")

    print("\n  Instance B (Follower) health:")
    for k, v in health_follower.items():
        print(f"    {k}: {v}")

    # Leader 與 Follower 的關鍵差異
    print("\n  Key difference:")
    print("    Leader:   unified_manager_running=True  (devices connected, real I/O)")
    print("    Follower: unified_manager_running=False (no device I/O)")


# ============================================================
# Step 8: 正式環境部署指引
# ============================================================


def demo_production_setup():
    """展示正式環境部署模式。"""
    print("\n" + "=" * 60)
    print("Demo 8: Production Setup Guide")
    print("=" * 60)

    # 前置需求與最小程式碼範例
    print("""
  Prerequisites:
    - etcd cluster (3+ nodes for HA)
    - Redis (Sentinel or Cluster for HA)
    - 2+ application instances

  Minimal production code:

    from csp_lib.cluster import ClusterConfig, ClusterController, EtcdConfig
    from csp_lib.integration import SystemController, SystemControllerConfig
    from csp_lib.manager import UnifiedDeviceManager, UnifiedConfig
    from csp_lib.redis import RedisClient

    # 1. Create configs
    cluster_config = ClusterConfig(
        instance_id="site_bms_01",
        etcd=EtcdConfig(endpoints=["etcd1:2379", "etcd2:2379"]),
        namespace="site_bms",
        device_ids=["pcs_01", "pcs_02"],
    )

    # 2. Create system components (same as single-instance)
    sys_ctrl = SystemController(ctrl_config, registry)
    unified = UnifiedDeviceManager(unified_config)
    redis = RedisClient(redis_config)

    # 3. Wrap with ClusterController
    cluster = ClusterController(
        config=cluster_config,
        system_controller=sys_ctrl,
        unified_manager=unified,
        redis_client=redis,
        on_promoted=my_on_promoted_callback,   # promoted hook
        on_demoted=my_on_demoted_callback,     # demoted hook
    )

    # 4. Run (blocks until stopped)
    async with cluster:
        await asyncio.Event().wait()

  ClusterController automatically handles:
    - Leader election via etcd
    - Device connect/disconnect on role change
    - Context provider hot-swap (live <-> virtual)
    - State publish/subscribe via Redis
    - Graceful failover with configurable grace period""")


# ============================================================
# 主程式
# ============================================================


async def async_main():
    demo_configuration()
    demo_election_state_machine()
    demo_cluster_snapshot()
    demo_virtual_context_builder()
    await demo_leader_election_simulation()
    await demo_cluster_controller_concept()
    demo_health_check()
    demo_production_setup()


def main():
    print("etcd Leader Election & ClusterController Deep Dive\n")

    asyncio.run(async_main())

    print("\n" + "=" * 60)
    print("All demos completed successfully.")
    print("=" * 60)


if __name__ == "__main__":
    main()
