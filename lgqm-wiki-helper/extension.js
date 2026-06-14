const vscode = require("vscode");
const http = require("http");
const { spawn } = require("child_process");
const path = require("path");

const SERVER_PORT = 8080;
const SERVER_URL = `http://127.0.0.1:${SERVER_PORT}`;
let serverProcess = null;
let statusBarItem = null;
let dashboardPanel = null; // 面板单例，复用

function activate(context) {
  // ---- 状态栏：监控面板 ----
  statusBarItem = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Right,
    100
  );
  statusBarItem.text = "$(dashboard) 监控面板";
  statusBarItem.tooltip = "在 VS Code 内打开临高启明同人监控看板";
  statusBarItem.command = "lgqm-wiki.openDashboard";
  statusBarItem.show();
  context.subscriptions.push(statusBarItem);

  // ---- 命令：打开面板 ----
  context.subscriptions.push(
    vscode.commands.registerCommand("lgqm-wiki.openDashboard", async () => {
      await ensureServerRunning();
      showDashboardPanel();
    })
  );

  // ---- 命令：预览 .mw ----
  context.subscriptions.push(
    vscode.commands.registerCommand("lgqm-wiki.previewMw", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) {
        vscode.window.showWarningMessage("没有打开的编辑器");
        return;
      }
      const text = editor.document.getText();
      const fileName = path.basename(editor.document.fileName);

      // 确保服务器运行
      await ensureServerRunning();

      // 显示加载提示
      await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: `正在渲染 ${fileName}...`,
          cancellable: false,
        },
        async () => {
          try {
            const html = await postPreview(text);
            if (html) {
              showPreviewPanel(html, fileName);
            }
          } catch (e) {
            vscode.window.showErrorMessage(`预览失败: ${e.message}`);
          }
        }
      );
    })
  );

  // ---- 欢迎信息 ----
  vscode.window.showInformationMessage(
    "📊 临高启明 Wiki 助手已就绪 — 点击底部状态栏打开监控面板"
  );
}

// ---- 确保服务器运行 ----
async function ensureServerRunning() {
  // 先检查是否已运行
  if (await isServerUp()) return;

  // 已有启动中的进程
  if (serverProcess) return;

  vscode.window.showInformationMessage(
    "正在启动 WebUI 服务器..."
  );

  // 在工作区目录启动服务器
  const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri?.fsPath || ".";
  serverProcess = spawn("python3", ["-m", "monitor.cli", "webui", "--port", String(SERVER_PORT)], {
    cwd: workspaceRoot,
    detached: false,
    shell: true,
  });

  // 后台输出不阻塞
  serverProcess.stdout?.on("data", () => {});
  serverProcess.stderr?.on("data", () => {});
  serverProcess.on("exit", () => {
    serverProcess = null;
  });

  // 轮询等待就绪
  for (let i = 0; i < 20; i++) {
    await sleep(500);
    if (await isServerUp()) {
      vscode.window.showInformationMessage("✅ WebUI 服务器已就绪");
      return;
    }
  }
  throw new Error("服务器启动超时");
}

function isServerUp() {
  return new Promise((resolve) => {
    const req = http.get(`${SERVER_URL}/api/report`, (res) => {
      resolve(res.statusCode === 200);
    });
    req.on("error", () => resolve(false));
    req.setTimeout(2000, () => {
      req.destroy();
      resolve(false);
    });
  });
}

// ---- POST wikitext 到 /api/preview ----
function postPreview(text) {
  return new Promise((resolve, reject) => {
    const data = Buffer.from(text, "utf-8");
    const options = {
      hostname: "127.0.0.1",
      port: SERVER_PORT,
      path: "/api/preview",
      method: "POST",
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Content-Length": data.length,
      },
      timeout: 120000, // 预览可能需要 2 分钟
    };

    const req = http.request(options, (res) => {
      let body = "";
      res.on("data", (chunk) => (body += chunk));
      res.on("end", () => {
        try {
          const result = JSON.parse(body);
          if (result.full) {
            resolve(result.full);
          } else {
            reject(new Error(result.error || "预览 API 返回空"));
          }
        } catch (e) {
          reject(new Error("JSON 解析失败"));
        }
      });
    });
    req.on("error", (e) => reject(e));
    req.on("timeout", () => {
      req.destroy();
      reject(new Error("预览请求超时"));
    });
    req.write(data);
    req.end();
  });
}

// ---- WebView 监控面板（VS Code 内嵌标签页） ----
function showDashboardPanel() {
  if (dashboardPanel) {
    // 已存在则直接显示
    dashboardPanel.reveal(vscode.ViewColumn.One);
    return;
  }

  dashboardPanel = vscode.window.createWebviewPanel(
    "lgqmDashboard",
    "📊 临高启明同人监控",
    vscode.ViewColumn.One,
    { enableScripts: true, retainContextWhenHidden: true }
  );

  dashboardPanel.webview.html = `<!DOCTYPE html>
    <html lang="zh-CN">
    <head><meta charset="UTF-8">
    <style>
      * { margin: 0; padding: 0; box-sizing: border-box; }
      html, body { height: 100vh; overflow: hidden; background: #1a1a2e; }
      iframe { position: absolute; top: 0; left: 0; width: 100%; height: 100%; border: none; }
    </style></head>
    <body>
      <iframe src="${SERVER_URL}/?vscode=1"></iframe>
      <script>
        const vscodeApi=acquireVsCodeApi();
        window.addEventListener('message',function(e){
          if(e.data&&e.data.command==='openExternal') vscodeApi.postMessage(e.data);
        });
      </script>
    </body></html>`;

  dashboardPanel.webview.onDidReceiveMessage(m=>{
    if(m.command==='openExternal'&&m.url) vscode.env.openExternal(vscode.Uri.parse(m.url));
  });

  dashboardPanel.onDidDispose(() => {
    dashboardPanel = null;
  });
}

// ---- WebView 预览面板 ----
function showPreviewPanel(html, fileName) {
  const panel = vscode.window.createWebviewPanel(
    "lgqmPreview",
    `预览: ${fileName}`,
    vscode.ViewColumn.Beside,
    { enableScripts: true, retainContextWhenHidden: true }
  );

  // 使用 iframe srcdoc 渲染完整 HTML（含 head + base + 内联 CSS）
  panel.webview.html = `<!DOCTYPE html>
    <html lang="zh-CN">
    <head><meta charset="UTF-8">
    <style>
      * { margin: 0; padding: 0; box-sizing: border-box; }
      html, body { height: 100vh; overflow: auto; background: #fff; }
      iframe { position: absolute; top: 0; left: 0; width: 100%; height: 100%; border: none; background: #fff; }
    </style></head>
    <body>
      <iframe srcdoc="${escapeHtml(html)}"></iframe>
    </body></html>`;
}

function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function deactivate() {
  // 扩展停用时不做额外清理，服务器可继续运行
}

module.exports = { activate, deactivate };
