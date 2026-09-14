/**
 * 设计态预览入口（M5-8）。
 *
 * `?state=NN` 用于在设计评审时固定到某个界面状态并截图；
 * **不传 `state` 参数即为实况模式**（live），此时前端走真实后端 API。
 *
 * 注意：这里只读 URL，不产生任何数据。放在 lib/ 而非 mock/，
 * 因为它不是假数据 —— 见 docs/PRODUCTION_READINESS.md §4。
 */
export function currentStateId(): string {
  const p = new URLSearchParams(window.location.search).get("state");
  return p ?? "01";
}

/** 是否处于实况模式（无 ?state= 且后端在线）。 */
export function isLiveMode(backendOnline: boolean): boolean {
  return backendOnline && !new URLSearchParams(window.location.search).get("state");
}
