/**
 * 视图模式判定（M5-8 设计态 / 实况二选一）。
 *
 * **默认是实况模式（live）**：不带任何参数打开就是真数据、真 Agent。
 * 只有**显式**带 `?state=NN` 才进入设计态预览（用固定的界面状态截图评审）。
 *
 * 注意：这里只读 URL，不产生任何数据。放在 lib/ 而非 mock/，
 * 因为它不是假数据 —— 见 docs/PRODUCTION_READINESS.md §4。
 */

const STATE_PARAM = "state";

/** 显式请求的设计态编号；未传或非法一律返回 null（即实况模式）。 */
export function currentStateId(): string | null {
  const p = new URLSearchParams(window.location.search).get(STATE_PARAM);
  if (!p) return null;
  return /^[0-9]{2}$/.test(p) ? p : null;
}

/** 是否处于设计态预览（仅当显式传了合法的 `?state=NN`）。 */
export function isDesignPreview(): boolean {
  return currentStateId() !== null;
}

/**
 * 是否处于实况模式（真数据 + 真 API）。
 *
 * 只要不是设计态预览就是实况 —— **后端离线也仍然是实况**，此时前端必须显示
 * 明确的连接错误，而不是悄悄换成演示数据。静默回退会让用户以为看到的是真实
 * 指标，这在运维场景里是最危险的一类错误。
 */
export function isLiveMode(_backendOnline = false): boolean {
  return !isDesignPreview();
}
