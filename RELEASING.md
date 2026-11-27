# 发布 Shotlet

工作流 [Release](.github/workflows/release.yml) 使用 GitHub 托管构建机生成桌面主应用，不需要本机上传二进制，也不需要配置额外的访问令牌。构建阶段只有读取权限，发布阶段通过 `GITHUB_TOKEN` 获取 `contents: write` 权限。仓库或组织的 Actions 策略需要允许工作流运行及创建 Release。

## 先检查构建产物

将工作流及相关脚本合入默认分支后，在 GitHub 的 **Actions → Release → Run workflow** 中选择分支并运行。手动运行只生成供下载检查的 Artifacts，不创建 Release。

Windows 和 macOS 发布构建使用 Release 配置，关闭测试、Node addon 和截图 SDK。Linux 发布复用 Linux build and test 工作流，在 x86_64 和 ARM64 原生构建机上完成核心、X11 桌面、GUI 和软件回退测试，并使用 Zig 构建 glibc 2.28 兼容包、检查 ABI。正式打标签前应确认目标提交的 Build and test 与 Linux build and test 均已通过。

| 平台 | 构建机 | 分发内容 |
| --- | --- | --- |
| Windows x64 | `windows-2022` | `shotlet.exe`、可选运行时资源、许可证 |
| macOS Apple Silicon | `macos-15` | arm64 `shotlet.app`、许可证 |
| macOS Intel | `macos-15-intel` | x86_64 `shotlet.app`、许可证 |
| Linux x86_64 | `ubuntu-24.04` | amd64 DEB／TGZ、桌面入口、图标、许可证 |
| Linux ARM64 | `ubuntu-24.04-arm` | arm64 DEB／TGZ、桌面入口、图标、许可证 |

各平台产物均带项目许可证、第三方依赖说明和 SDL、Dear ImGui、nlohmann/json 的完整许可证。Linux 兼容包还包含 Zig／LLVM 运行库许可证。分发桌面主应用，Node addon 和 C SDK 按 README 单独构建。

## 发布版本

1. 更新根目录 `CMakeLists.txt` 的 `project(shotlet VERSION ...)`，提交并推送修改。
2. 确认目标提交的 Build and test 与 Linux build and test 工作流通过，并完成必要的实际桌面功能检查。
3. 对该提交创建并推送同名版本标签。例如当前版本 `0.1.1`：

```bash
git tag v0.1.1
git push origin v0.1.1
```

只接受与 CMake 版本完全一致的 `v主版本.次版本.修订号` 标签，例如 `v0.1.1`。不支持带预发布后缀的标签；不匹配时在构建前报错，确保分发包文件名和应用内部版本一致。

全部平台打包成功后，工作流合并并验证 SHA-256 校验文件，创建 Release 草稿、上传三个 ZIP、两种架构各自的 DEB／TGZ 及 `SHA256SUMS`，最后公开 Release，并自动生成更新说明。任一构建失败都不会进入发布阶段。

如果上传或公开失败，检查 Releases 中是否留下同名草稿；确认后删除未完成的草稿，再重新运行失败任务。已公开的同名 Release 不会被自动覆盖。

## 下载与校验

发布附件名为：

```text
shotlet-0.1.1-windows-x64.zip
shotlet-0.1.1-macos-arm64.zip
shotlet-0.1.1-macos-x64.zip
shotlet-0.1.1-linux-amd64.deb
shotlet-0.1.1-linux-amd64.tar.gz
shotlet-0.1.1-linux-arm64.deb
shotlet-0.1.1-linux-arm64.tar.gz
SHA256SUMS
```

下载对应平台的分发包和 `SHA256SUMS`，比对文件的 SHA-256。

```bash
# macOS
shasum -a 256 shotlet-0.1.1-macos-arm64.zip
```

```powershell
# Windows PowerShell
Get-FileHash .\shotlet-0.1.1-windows-x64.zip -Algorithm SHA256
```

macOS 截图最低需要 13.3，录屏需要 15 或更新版本。应用包在构建后剥离符号并采用临时签名（ad-hoc），未使用 Developer ID 签名和 Apple 公证；Windows EXE 未做代码签名，系统可能提示来源未验证。当前 ZIP 是便携分发包，不包含安装器或自动更新功能。

## 本地打包

先按 README 构建 Release 主应用，再从仓库根目录运行：

```bash
python3 scripts/package-release.py --build-dir build --platform macos-arm64
```

Intel Mac 使用 `--platform macos-x64`；Windows 使用 `python` 和 `--platform windows-x64`。打包脚本从 CMake 读取版本，默认输出到 `dist/`，并生成对应的 `.zip.sha256` 文件。macOS 使用系统 `ditto` 保留应用包权限、符号链接和元数据，并检查二进制架构与签名。

Linux 本地构建、CPack 打包和目标桌面验证见 [Linux 适配说明](docs/linux.md)。
