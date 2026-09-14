// 生成「跳转壳」用的 dist：只放一个 index.html，
// 它加载后会立刻跳到 http://127.0.0.1:8791（后端同源托管的前端）。
//
// 为什么这么做：Tauri v2 只要配了 build.frontendDist，构建时就会把
// windows[].url 覆盖回本地资源，导致指向后端的 url 永远不生效。
// 与其跟它抢，不如把本地资源本身做成一个跳转页。
import { mkdirSync, copyFileSync, rmSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const dist = join(root, "dist");

rmSync(dist, { recursive: true, force: true });
mkdirSync(dist, { recursive: true });
copyFileSync(join(root, "shell", "index.html"), join(dist, "index.html"));

console.log("[build:shell] dist/index.html ready -> http://127.0.0.1:8791");
