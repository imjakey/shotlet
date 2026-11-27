# Linux 基础截图预览版

面向银河麒麟、统信 UOS 的 x86_64 和 ARM64 桌面。第一阶段支持 **X11 截图、区域选择、标注和 PNG 保存**，复用已有画布与标注工具；中文字体通过 Fontconfig 查找。

## 使用范围

- 包架构：`amd64` 对应 x86_64，`arm64` 对应 aarch64。两个包不能混用。
- 当前要求 X11 会话。`echo "$XDG_SESSION_TYPE"` 应为 `x11`；Wayland 会明确报错，不会返回虚构显示器或黑色截图。
- 优先使用 SDL_GPU 的 Vulkan 后端；设备初始化失败时自动回退 CPU 软件渲染，覆盖基础截图、标注和 PNG 导出。可用 `SHOTLET_RENDERER=software` 强制软件模式。国产显卡及真机桌面仍需验证。
- 软件模式的工具栏图标使用 4× 采样位图缓存，保持原矢量形状、交互范围和状态颜色，修复细线与圆弧断裂。缓存随所属工具栏释放，不依赖额外图标字体。
- 首期不开放 Wayland、OCR、贴图、滚动长截图、录屏和全局热键。OCR、贴图按钮禁用；托盘常驻模式及系统剪贴板尚不作为本阶段交付范围。
- 首期“完成”、保存按钮和 `Ctrl+S` 均打开系统保存对话框，导出包含标注的 PNG。宿主／SDK 模式的完成操作仍返回图片像素。

实际兼容范围还需要按具体系统版本／SP、桌面环境和显卡驱动做验收。Xvfb／Mesa 的自动化检查不能替代银河麒麟 UKUI、统信 DDE 真机验证。

## 安装和运行

DEB 包可安装到基于 Debian 软件包体系的麒麟／UOS 桌面：

```sh
sudo apt install ./shotlet-0.1.1-linux-amd64.deb
# ARM64 机器改为 shotlet-0.1.1-linux-arm64.deb；版本以实际构建为准
shotlet --language zh-CN --theme auto
```

也可以从应用菜单打开 Shotlet。运行后拖动选择区域，在工具栏添加矩形、箭头、文字等标注，再保存。系统文件选择器负责取消与覆盖确认；写入在目标目录内完成，完整编码成功后才替换目标文件。

TGZ 包保持相同的安装目录结构，可直接运行其中的 `usr/bin/shotlet`；依赖需要自行安装。运行时依赖包括 X11、XRandR、Xinerama、Fontconfig、Zenity，以及 `fonts-noto-cjk` 或 `fonts-wqy-zenhei`。Vulkan 运行库与可用驱动用于加速，软件模式不需要它们。应用优先使用可用的 FileChooser Portal，缺失时使用 Zenity。Zenity 3／4 使用系统默认按钮文案，避免版本差异。

`scripts/test-linux-tarball.sh` 可以验证并解压 TGZ、检查实际 ELF 架构和依赖、启动截图测试，然后检查 PNG 签名、尺寸、分块和 IEND；安装了 `pngcheck` 时还会校验 CRC 与图像数据。截图内容、中文和标注效果仍需目视确认。无需 root，不修改 HOME；日志、设置和截图写入独立结果目录。

```sh
bash scripts/test-linux-tarball.sh /path/to/shotlet-0.1.1-linux-amd64.tar.gz
# 只做预检，不打开截图界面：
bash scripts/test-linux-tarball.sh /path/to/shotlet-0.1.1-linux-amd64.tar.gz --check-only
# 仅校验、解压和打印程序路径，不执行程序：
bash scripts/test-linux-tarball.sh /path/to/shotlet-0.1.1-linux-amd64.tar.gz --prepare-only
# 强制 CPU 软件渲染：
bash scripts/test-linux-tarball.sh /path/to/shotlet-0.1.1-linux-amd64.tar.gz --software
```

测试脚本只需要 Bash 和常见系统命令，不调用 Python。构建机上可以用下列命令生成测试包，加入一个架构的 TGZ，或同时加入同版本的两个架构：

```sh
python3 scripts/package-linux-testkit.py \
  --packages dist/linux/shotlet-0.1.1-linux-amd64.tar.gz dist/linux/shotlet-0.1.1-linux-arm64.tar.gz \
  --output dist/linux/shotlet-linux-testkit.tar.gz
```

测试包包含 `test-shotlet.sh`、所选 TGZ、说明和 SHA256SUMS。使用新的独立目录解压，进入 `shotlet-linux-testkit` 执行 `bash test-shotlet.sh`，脚本会自动选择本机架构。CI 每个架构的产物包含对应架构测试包。脚本强制使用 Zenity，以复现已经验证的保存流程。结果目录默认放在 `/tmp/shotlet-test.*`，也可用 `--output-dir` 指定一个新的或空目录；所有结果保留供复查。

程序默认解压到脚本旁的 `shotlet-runtime-架构-包摘要` 固定目录，也可用 `--runtime-dir` 指定。重跑时校验并复用同一个可执行文件，不覆盖已有程序。麒麟若提示 `Permission denied by kysec`，脚本以退出码 3 报告执行被阻止，不会误报 glibc 过低。可先使用 `--prepare-only` 获得程序路径，再按单位策略由管理员在“安全中心 → 应用防护 → 应用程序执行控制 → 高级配置”中授权这个程序文件，之后使用同一目录重跑。操作路径见[麒麟官方常见问题](https://kylinos.cn/upload/product/20240611/0005f934ce6aaa70024879cadde077b7.pdf)。脚本不会修改安全策略。

```sh
shotlet --version
shotlet --help
shotlet --log-level debug --log-dir /path/to/writable/logs
```

## 常规源码构建

需要 CMake 3.20+、支持 `<format>` 的 C++20 工具链（例如 GCC 13+）。仅使用 `-std=c++20` 不会为旧 GCC 补上 `<format>`。依赖 SDL、ImGui 的固定版本与根目录 README 一致。

以下是 Debian／Ubuntu 风格开发环境的依赖示例；麒麟／UOS 的软件源与包名应按对应版本检查：

```sh
sudo apt install build-essential cmake ninja-build git pkg-config \
  libx11-dev libxrandr-dev libxinerama-dev libxcursor-dev libxi-dev \
  libxfixes-dev libxext-dev libxss-dev libxtst-dev libxkbcommon-dev \
  libdbus-1-dev libfontconfig1-dev zenity fonts-wqy-zenhei libvulkan1

git clone --branch release-3.4.18 --depth 1 https://github.com/libsdl-org/SDL.git sdl3
git clone https://github.com/ocornut/imgui.git imgui
git -C imgui checkout e05bd9deb9a73b67acb5c04b8a581e06a2d42657

cmake -S . -B build/linux -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DSDL3_DIR="$PWD/sdl3" -DIMGUI_DIR="$PWD/imgui" \
  -DSHOTLET_BUILD_TESTS=OFF -DSHOTLET_BUILD_NODE_ADDON=OFF
cmake --build build/linux --parallel 4
./build/linux/shotlet
```

X11 的窗口坐标和截图均以 framebuffer 像素为基准，不能把 Xft 字体 DPI 直接当作截图像素／窗口坐标缩放比。选区会裁剪到实际显示器与根窗口边界。显示器布局、镜像输出和缩放仍需在目标桌面逐项测试。

## 兼容旧系统库的构建

提供 `cmake/toolchains/linux-zig.cmake`，使用 **Zig 0.15.2** 附带的 libc++ 静态运行库，并将应用的 glibc 基线设为 **2.28**。这避免要求用户升级系统全局 libc／libstdc++。构建工具本身可在较新系统运行。

在目标 CPU 的原生构建机上安装上述开发依赖，然后设置 Zig 可执行文件路径：

```sh
cmake -S . -B build/linux-portable -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$PWD/cmake/toolchains/linux-zig.cmake" \
  -DSHOTLET_ZIG=/absolute/path/to/zig \
  -DSHOTLET_LINUX_ARCH=x86_64 \
  -DCMAKE_BUILD_TYPE=MinSizeRel \
  -DSDL3_DIR="$PWD/sdl3" -DIMGUI_DIR="$PWD/imgui" \
  -DSHOTLET_BUILD_TESTS=OFF -DSHOTLET_BUILD_NODE_ADDON=OFF
cmake --build build/linux-portable --parallel 4
python3 scripts/check-linux-abi.py --arch x86_64 --max-glibc 2.28 \
  --static-cxx build/linux-portable/shotlet
cpack --config build/linux-portable/CPackConfig.cmake -G 'DEB;TGZ' -B dist/linux
```

ARM64 原生构建机将 `SHOTLET_LINUX_ARCH` 与 ABI 检查的 `--arch` 改成 `aarch64`。交叉构建还需通过 `SHOTLET_LINUX_SYSROOT` 提供对应架构的 X11／Fontconfig 等 C 依赖；只提供目标依赖头文件和库，不要用较新系统的 libc 头文件覆盖 Zig 的 libc 基线。

普通 GCC 构建的 DEB 通过 `dpkg-shlibdeps` 计算实际运行库依赖；兼容构建的产物应在打包前执行 ABI 检查，确认没有超出 glibc 基线或动态依赖 libstdc++。TGZ 也不携带系统 glibc、GPU 驱动和 X11 库。兼容包附带 Zig／LLVM 标准库的许可证。

## 自动化验证

安装额外的测试依赖：

```sh
sudo apt install libgtest-dev xvfb xauth xdotool python3-pil mesa-vulkan-drivers
cmake -S . -B build/linux-tests -G Ninja \
  -DCMAKE_BUILD_TYPE=Debug \
  -DSDL3_DIR="$PWD/sdl3" -DIMGUI_DIR="$PWD/imgui" \
  -DSHOTLET_BUILD_NODE_ADDON=OFF \
  -DSHOTLET_BUILD_TESTS=ON -DSHOTLET_BUILD_LINUX_GUI_TESTS=ON
cmake --build build/linux-tests --parallel 4
ctest --test-dir build/linux-tests --output-on-failure --timeout 120
```

测试应以普通用户运行，文件权限失败场景不适合在 root 身份下验证。测试数据使用临时目录和独立的 XDG 数据目录，不改 HOME。

Linux 专项测试在 24 位及 RGB565 的 Xvfb 显示上检查真实 X11 采集、区域裁剪、颜色通道、PNG 读回、中文文件名及失败时保留原文件。GUI 测试启动真实应用，在 X11 窗口上选择区域、画矩形、输入中文，再通过原生保存对话框导出并检查像素；还会验证保存取消和 Esc 退出。图形测试分别覆盖 Vulkan、强制软件渲染和 Vulkan 不可用时自动回退；后两项禁用 Vulkan ICD。Vulkan 项可使用 Mesa lavapipe。

`.github/workflows/linux.yml` 为 x86_64 与 ARM64 提供独立的原生构建／测试任务，以及旧 glibc 基线构建和 DEB／TGZ 产物。它不代表已经完成厂商桌面验收。
