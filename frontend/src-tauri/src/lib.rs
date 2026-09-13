/// OpsPilot 桌面壳。
///
/// Tauri 的职责只有两个：① 加载前端 ② 管理窗口。
/// 全部业务逻辑在 Python 侧（FastAPI + OpenHands SDK）。
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("OpsPilot 启动失败");
}
