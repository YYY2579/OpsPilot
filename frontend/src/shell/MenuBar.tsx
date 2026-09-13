import { useShell } from "../state/shell";

interface MenuItem { label: string; shortcut?: string; sep?: boolean; disabled?: boolean }
interface Menu { label: string; items: MenuItem[] }

const MENUS: Menu[] = [
  { label: "文件", items: [
    { label: "新建窗口", shortcut: "Ctrl+Shift+N" }, { label: "新聊天", shortcut: "Ctrl+N" },
    { label: "打开文件夹…", shortcut: "Ctrl+O" }, { label: "", sep: true },
    { label: "保存会话记录", shortcut: "Ctrl+S" }, { label: "导出当前报告…", shortcut: "Ctrl+Shift+E" },
    { label: "", sep: true }, { label: "关闭窗口", shortcut: "Ctrl+W" }, { label: "退出 OpsPilot", shortcut: "Ctrl+Q" },
  ]},
  { label: "编辑", items: [
    { label: "撤销", shortcut: "Ctrl+Z" }, { label: "重做", shortcut: "Ctrl+Shift+Z" },
    { label: "", sep: true }, { label: "剪切", shortcut: "Ctrl+X" }, { label: "复制", shortcut: "Ctrl+C" },
    { label: "粘贴", shortcut: "Ctrl+V" }, { label: "删除", shortcut: "Del" },
    { label: "", sep: true }, { label: "全选", shortcut: "Ctrl+A" }, { label: "查找…", shortcut: "Ctrl+F" },
  ]},
  { label: "视图", items: [
    { label: "切换左侧栏", shortcut: "Ctrl+B" }, { label: "切换右侧面板", shortcut: "Ctrl+Alt+B" },
    { label: "切换底部面板", shortcut: "Ctrl+J", disabled: true }, { label: "打开终端", shortcut: "Ctrl+`", disabled: true },
    { label: "", sep: true }, { label: "放大", shortcut: "Ctrl+=" }, { label: "缩小", shortcut: "Ctrl+-" },
    { label: "重置缩放", shortcut: "Ctrl+0" }, { label: "全屏", shortcut: "F11" },
    { label: "", sep: true }, { label: "浅色 / 深色主题", shortcut: "Ctrl+Shift+L" },
  ]},
  { label: "设置", items: [
    { label: "偏好设置…", shortcut: "Ctrl+," }, { label: "", sep: true },
    { label: "模型与密钥" }, { label: "连接与凭据" }, { label: "主题" }, { label: "语言" },
    { label: "", sep: true }, { label: "导入 / 导出配置" },
  ]},
  { label: "帮助", items: [
    { label: "文档", shortcut: "F1" }, { label: "键盘快捷键", shortcut: "Ctrl+K Ctrl+S" },
    { label: "系统状态" }, { label: "检查更新…" }, { label: "", sep: true }, { label: "关于 OpsPilot" },
  ]},
];

export default function MenuBar() {
  const { menuOpen, setMenu } = useShell();

  return (
    <div className="menubar relative select-none">
      <div className="flex items-center gap-2 px-3 h-full">
        <span className="w-[18px] h-[18px] rounded-[5px] bg-accent text-white text-[10px] font-semibold grid place-items-center">OP</span>
        <span className="font-medium text-ink">OpsPilot</span>
        <span className="w-px h-[16px] bg-line mx-1" />
      </div>

      {MENUS.map((menu) => (
        <div key={menu.label} className="relative h-full">
          <button
            onClick={() => setMenu(menuOpen === menu.label ? null : menu.label)}
            onMouseEnter={() => menuOpen && setMenu(menu.label)}
            className="h-full px-[7px] text-ink2 hover:text-ink transition-colors"
            style={menuOpen === menu.label ? { background: "var(--accent)", color: "#fff" } : undefined}
          >{menu.label}</button>

          {menuOpen === menu.label && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setMenu(null)} />
              <div className="absolute left-0 top-[26px] z-50 w-[252px] py-1 rounded-[9px] border border-line2 bg-surface"
                   style={{ boxShadow: "0 12px 34px rgba(0,0,0,.5)" }}>
                {menu.items.map((item, i) =>
                  item.sep ? (
                    <div key={i} className="h-px bg-line my-[5px]" />
                  ) : (
                    <button key={i}
                      disabled={item.disabled}
                      className={`w-full flex items-center justify-between px-[10px] h-[26px] text-left
                        ${item.disabled ? "text-ink3 cursor-not-allowed" : "text-ink hover:bg-surface2"}`}>
                      <span>{item.label}</span>
                      {item.shortcut && <span className="text-ink3 text-[11px]">{item.shortcut}</span>}
                    </button>
                  ),
                )}
              </div>
            </>
          )}
        </div>
      ))}

      <div className="ml-auto flex items-center gap-[14px] px-3 text-ink3">
        <span className="text-[11px] hover:text-ink">─</span>
        <span className="text-[11px] hover:text-ink">□</span>
        <span className="text-[11px] hover:text-ink">✕</span>
      </div>
    </div>
  );
}
