import Cocoa
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var serverProcess: Process?
    private lazy var serverPort: String = {
        Bundle.main.object(forInfoDictionaryKey: "NoteBridgeServerPort") as? String ?? "8765"
    }()
    private lazy var appURL: URL = URL(string: "http://127.0.0.1:\(serverPort)")!
    private lazy var statusURL: URL = URL(string: "http://127.0.0.1:\(serverPort)/api/status")!
    private lazy var appDisplayName: String = {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String ?? "Note Bridge"
    }()
    private lazy var personalMode: Bool = {
        Bundle.main.object(forInfoDictionaryKey: "NoteBridgePersonalMode") as? String == "1"
    }()
    private lazy var projectDir: String = {
        let bundled = Bundle.main.resourcePath ?? FileManager.default.currentDirectoryPath
        let bundledServer = URL(fileURLWithPath: bundled).appendingPathComponent("plauddb_web.py").path
        if FileManager.default.fileExists(atPath: bundledServer) {
            return bundled
        }
        return FileManager.default.currentDirectoryPath
    }()
    private lazy var dataDir: String = {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let url = base.appendingPathComponent("Note Bridge", isDirectory: true)
        try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url.path
    }()

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        appendDebug("applicationDidFinishLaunching")
        startServer()
        appendDebug("startServer returned")
        buildWindow()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) {
            self.webView.load(URLRequest(url: self.appURL))
        }
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    func applicationWillTerminate(_ notification: Notification) {
        serverProcess?.terminate()
    }

    private func buildWindow() {
        let frame = NSRect(x: 0, y: 0, width: 1180, height: 780)
        window = NSWindow(
            contentRect: frame,
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.center()
        window.title = appDisplayName
        window.minSize = NSSize(width: 980, height: 640)

        webView = WKWebView(frame: window.contentView?.bounds ?? frame)
        webView.autoresizingMask = [.width, .height]
        window.contentView?.addSubview(webView)
        window.makeKeyAndOrderFront(nil)
    }

    private func startServer() {
        appendDebug("startServer begin projectDir=\(projectDir) dataDir=\(dataDir)")
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.arguments = ["\(projectDir)/plauddb_web.py"]
        process.currentDirectoryURL = URL(fileURLWithPath: projectDir)

        var env = ProcessInfo.processInfo.environment
        env["PLAUDDB_NO_BROWSER"] = "1"
        env["PLAUDDB_PORT"] = serverPort
        env["NOTE_BRIDGE_HOME"] = dataDir
        env["NOTE_BRIDGE_PERSONAL_MODE"] = personalMode ? "1" : "0"
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        process.environment = env
        let logPath = URL(fileURLWithPath: dataDir).appendingPathComponent("server.log").path
        FileManager.default.createFile(atPath: logPath, contents: nil)
        if let logHandle = FileHandle(forWritingAtPath: logPath) {
            logHandle.seekToEndOfFile()
            process.standardOutput = logHandle
            process.standardError = logHandle
        }

        do {
            try process.run()
            serverProcess = process
            appendDebug("server process started pid=\(process.processIdentifier)")
        } catch {
            appendDebug("server process failed: \(error.localizedDescription)")
            showError("Note Bridge server could not start: \(error.localizedDescription)")
        }
    }

    private func appendDebug(_ message: String) {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let dir = base.appendingPathComponent("Note Bridge", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let url = dir.appendingPathComponent("app.log")
        let line = "[\(Date())] \(message)\n"
        if !FileManager.default.fileExists(atPath: url.path) {
            FileManager.default.createFile(atPath: url.path, contents: nil)
        }
        if let handle = FileHandle(forWritingAtPath: url.path) {
            handle.seekToEndOfFile()
            handle.write(line.data(using: .utf8) ?? Data())
            try? handle.close()
        }
    }

    private func migrateLegacyConfigIfNeeded() {
        let fileManager = FileManager.default
        let dataURL = URL(fileURLWithPath: dataDir, isDirectory: true)
        let legacyRoot = Bundle.main.bundleURL.deletingLastPathComponent()
        for name in [".env", "category_rules.json"] {
            let target = dataURL.appendingPathComponent(name)
            let source = legacyRoot.appendingPathComponent(name)
            if !fileManager.fileExists(atPath: target.path), fileManager.fileExists(atPath: source.path) {
                try? fileManager.copyItem(at: source, to: target)
            }
        }
    }

    private func serverIsRunning() -> Bool {
        let semaphore = DispatchSemaphore(value: 0)
        var ok = false
        var request = URLRequest(url: statusURL, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 0.3)
        request.setValue("no-cache", forHTTPHeaderField: "Cache-Control")
        let task = URLSession.shared.dataTask(with: request) { _, response, _ in
            if let http = response as? HTTPURLResponse, http.statusCode == 200 {
                ok = true
            }
            semaphore.signal()
        }
        task.resume()
        _ = semaphore.wait(timeout: .now() + 0.35)
        return ok
    }

    private func showError(_ message: String) {
        let alert = NSAlert()
        alert.messageText = "Note Bridge"
        alert.informativeText = message
        alert.alertStyle = .warning
        alert.runModal()
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
