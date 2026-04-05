# =============== gRPC Module ===============
#
# gRPC 傳輸層定義
#
# 階層控制的 gRPC 服務定義與 TransportAdapter 參考：
#   - control.proto: ControlDispatchService + StatusReportService
#   - 對應 integration.hierarchical 的 Protocol 介面
#
# 此模組為 Layer 8 (Additional)，提供 .proto 定義。
# 需 `csp_lib[grpc]` optional dependency。

raise ImportError('csp_lib.grpc requires additional dependencies. Install with: pip install "csp0924_lib[grpc]"')
