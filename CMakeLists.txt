cmake_minimum_required(VERSION 3.20)

# 固定 macOS 最低版本，避免发布产物跟随构建机系统版本导致旧系统 dlopen 失败。
# 注意：libc++ 的 std::format 无条件依赖浮点 std::to_chars，而后者从 macOS 13.3 起
# 才由系统 libc++.dylib 提供，因此当前代码的真实下限是 13.3（不是 ScreenCaptureKit 的 12.3）。
if(APPLE AND NOT CMAKE_OSX_DEPLOYMENT_TARGET)
    # 显式 FORCE：旧构建缓存里存在空值，普通 set(CACHE) 不会覆盖。
    set(CMAKE_OSX_DEPLOYMENT_TARGET "13.3" CACHE STRING "Minimum macOS deployment target" FORCE)
endif()

project(shotlet VERSION 0.1.1 LANGUAGES CXX C)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

if(APPLE)
    enable_language(OBJCXX)
endif()

# Options
option(SHOTLET_BUILD_CAPTURE_SDK "Build capture SDK and standalone host helper" OFF)
option(SHOTLET_BUILD_TESTS "Build tests" ON)
option(SHOTLET_BUILD_LINUX_GUI_TESTS "Test real Linux screenshot, annotations and native save dialogs" OFF)
option(SHOTLET_BUILD_NODE_ADDON "Build Node-API addon" ON)
find_package(Threads REQUIRED)

# SDL3 源码目录
set(SDL3_DIR "${CMAKE_CURRENT_SOURCE_DIR}/sdl3" CACHE PATH "Path to SDL3 source directory")
# 只构建静态库，不构建共享库、测试和示例
set(SDL_SHARED OFF CACHE BOOL "" FORCE)
set(SDL_STATIC ON CACHE BOOL "" FORCE)
set(SDL_TEST_LIBRARY OFF CACHE BOOL "" FORCE)
set(SDL_TESTS OFF CACHE BOOL "" FORCE)
set(SDL_EXAMPLES OFF CACHE BOOL "" FORCE)
# 默认使用 SDL_GPU；Linux 另启用软件渲染，关闭其他未使用子系统。
foreach(subsystem AUDIO CAMERA JOYSTICK HAPTIC HIDAPI POWER SENSOR DIALOG RENDER)
    set(SDL_${subsystem} OFF CACHE BOOL "Shotlet 不使用此 SDL 子系统" FORCE)
endforeach()
if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    # The first Linux desktop backend is X11; file dialogs use Portal or Zenity.
    set(SDL_DIALOG ON CACHE BOOL "Linux native save dialogs" FORCE)
    set(SDL_RENDER ON CACHE BOOL "Linux software rendering fallback" FORCE)
    set(SDL_RENDER_GPU OFF CACHE BOOL "Software fallback does not use SDL_GPU" FORCE)
    set(SDL_RENDER_VULKAN OFF CACHE BOOL "Software fallback does not use Vulkan" FORCE)
    set(SDL_OPENGL OFF CACHE BOOL "Software fallback does not use OpenGL" FORCE)
    set(SDL_OPENGLES OFF CACHE BOOL "Software fallback does not use GLES" FORCE)
    set(SDL_WAYLAND OFF CACHE BOOL "Linux capture currently requires X11" FORCE)
    set(SDL_KMSDRM OFF CACHE BOOL "Linux capture currently requires an X11 desktop" FORCE)
    set(CMAKE_POSITION_INDEPENDENT_CODE ON)
endif()
# 后台模式使用系统托盘，覆盖旧缓存中关闭的设置。
set(SDL_TRAY ON CACHE BOOL "Shotlet 后台模式使用系统托盘" FORCE)
if(APPLE)
    # macOS 仅使用 Metal。
    set(SDL_OPENGL OFF CACHE BOOL "Shotlet 在 macOS 使用 Metal" FORCE)
    set(SDL_OPENGLES OFF CACHE BOOL "Shotlet 在 macOS 使用 Metal" FORCE)
    set(SDL_VULKAN OFF CACHE BOOL "Shotlet 在 macOS 使用 Metal" FORCE)
elseif(WIN32)
    # Windows 仅使用 SDL_GPU 的 Direct3D 12 后端，不依赖 SDL_Render。
    set(SDL_OPENGL OFF CACHE BOOL "Shotlet 在 Windows 使用 Direct3D 12" FORCE)
    set(SDL_OPENGLES OFF CACHE BOOL "Shotlet 在 Windows 使用 Direct3D 12" FORCE)
    set(SDL_VULKAN OFF CACHE BOOL "Shotlet 在 Windows 使用 Direct3D 12" FORCE)
endif()
# 全局设置静态 CRT，确保 SDL3 和 shotlet 一致，避免链接冲突
if(MSVC)
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded" CACHE STRING "MSVC runtime library")
endif()

add_subdirectory(${SDL3_DIR} ${CMAKE_CURRENT_BINARY_DIR}/SDL3 EXCLUDE_FROM_ALL)
# SDL 3.4.18 已包含 Metal 窗口 ARC 引用释放修复。
get_directory_property(SDL3_SOURCE_VERSION DIRECTORY "${SDL3_DIR}" DEFINITION PROJECT_VERSION)
if(SDL3_SOURCE_VERSION VERSION_LESS "3.4.18")
    message(FATAL_ERROR "需要 SDL 3.4.18 或更新版本，请按 README.md 更新 SDL3_DIR 中的源码")
endif()
include(cmake/ApplyPatch.cmake)
set(SHOTLET_SDL_DYNAMIC_API_PATCH "${CMAKE_CURRENT_SOURCE_DIR}/cmake/patches/disable-sdl-dynamic-api.patch")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${SHOTLET_SDL_DYNAMIC_API_PATCH}")
# 关闭跳转表后，静态链接可以移除未使用的 SDL 实现；补丁不匹配时停止配置。
shotlet_apply_patch("${SDL3_DIR}" "${SHOTLET_SDL_DYNAMIC_API_PATCH}")
if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    # SDL 3.4.18 uses the color stride to read UVs in its software quad path.
    # ImGui supplies separate float colors and packed position/UV vertices.
    set(SHOTLET_SDL_SOFTWARE_UV_PATCH "${CMAKE_CURRENT_SOURCE_DIR}/cmake/patches/software-uv-stride.patch")
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${SHOTLET_SDL_SOFTWARE_UV_PATCH}")
    shotlet_apply_patch("${SDL3_DIR}" "${SHOTLET_SDL_SOFTWARE_UV_PATCH}")
endif()
if(APPLE)
    set(SHOTLET_MAC_TRANSPARENT_BACKING_PATCH "${CMAKE_CURRENT_SOURCE_DIR}/cmake/patches/macos-transparent-backing.patch")
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${SHOTLET_MAC_TRANSPARENT_BACKING_PATCH}")
    # SDL_GPU 不接受透明标志，Cocoa 重绘需尊重原生窗口配置，避免退出截图时出现黑底。
    shotlet_apply_patch("${SDL3_DIR}" "${SHOTLET_MAC_TRANSPARENT_BACKING_PATCH}")
endif()
set(SDL3_TARGET SDL3::SDL3-static)

# ImGui renderer backends (Linux also supports CPU rendering without Vulkan).
set(IMGUI_DIR "${CMAKE_CURRENT_SOURCE_DIR}/imgui" CACHE PATH "Path to ImGui directory")
set(IMGUI_CORE
    ${IMGUI_DIR}/imgui.cpp
    ${IMGUI_DIR}/imgui_draw.cpp
    ${IMGUI_DIR}/imgui_tables.cpp
    ${IMGUI_DIR}/imgui_widgets.cpp
)
set(IMGUI_SDLGPU3_SOURCE ${IMGUI_DIR}/backends/imgui_impl_sdlgpu3.cpp)
if(APPLE)
    set(IMGUI_SDLGPU3_SOURCE src/third_party/gpu_msl_backend.cpp)
endif()
set(IMGUI_SOURCES ${IMGUI_CORE}
    ${IMGUI_DIR}/backends/imgui_impl_sdl3.cpp
    ${IMGUI_SDLGPU3_SOURCE}
)
if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    list(APPEND IMGUI_SOURCES ${IMGUI_DIR}/backends/imgui_impl_sdlrenderer3.cpp)
endif()

# Shared application sources
set(SHOTLET_CORE_SOURCES
    src/i18n/Localization.cpp
    src/i18n/SystemLanguage.cpp
    src/app/Application.cpp
    src/app/ApplicationInitialization.cpp
    src/app/ApplicationCapture.cpp
    src/app/ApplicationRecording.cpp
    src/app/ApplicationOutput.cpp
    src/app/ApplicationOcr.cpp
    src/app/ApplicationClipboard.cpp
    src/app/ApplicationHistory.cpp
    src/app/ApplicationRecentCaptures.cpp
    src/app/ApplicationSettings.cpp
    src/app/Preferences.cpp
    src/ui/ScreenOverlay.cpp
    src/ui/ScreenOverlayContext.cpp
    src/ui/ScreenOverlayGpuTexture.cpp
    src/ui/ScreenOverlayEvents.cpp
    src/ui/ScreenOverlayRender.cpp
    src/ui/GpuTextureUpload.cpp
    src/ui/ImageEditor.cpp
    src/ui/SettingsWindow.cpp
    src/ui/HistoryWindow.cpp
    src/ui/HistoryWindowView.cpp
    src/ui/PopupSurface.cpp
    src/ui/RecordingWindow.cpp
    src/ui/RecentCapturesWindow.cpp
    src/ui/RecentCapturesView.cpp
    src/ui/OverlayManager.cpp
    src/ui/Toolbar.cpp
    src/ui/ToolbarIcons.cpp
    src/ui/WindowChrome.cpp
    src/ui/SubToolbar.cpp
    src/core/CanvasState.cpp
    src/core/CanvasTextInput.cpp
    src/core/CanvasInteraction.cpp
    src/core/CanvasRender.cpp
    src/core/CanvasImage.cpp
    src/core/CaptureDocument.cpp
    src/core/CanvasDocument.cpp
    src/history/DocumentCodec.cpp
    src/history/HistoryStore.cpp
    src/history/HistoryStorageMigration.cpp
    src/history/HistoryLibrary.cpp
    src/history/HistoryService.cpp
    src/platform/HistoryDirectoryLock.cpp
    src/platform/HistoryChangeSignal.cpp
    src/core/CursorManager.cpp
    src/core/LayerManager.cpp
    src/core/layers/ArrowLayer.cpp
    src/core/layers/BrushLayer.cpp
    src/core/layers/EllipseLayer.cpp
    src/core/layers/LayerRasterUtils.cpp
    src/core/layers/MosaicLayer.cpp
    src/core/layers/RectangleLayer.cpp
    src/core/layers/TextLayer.cpp
    src/core/layers/NumberLayer.cpp
    src/core/layers/HighlightLayer.cpp
    src/utils/MaskGeometry.cpp
    src/core/SmartRegionDetector.cpp
    src/scrollcapture/LongImageStore.cpp
    src/scrollcapture/ScrollCaptureStitcher.cpp
    src/scrollcapture/ScrollCaptureController.cpp
    src/scrollcapture/ScrollPlanner.cpp
    src/scrollcapture/FrameStability.cpp
    src/ui/ScreenOverlayScroll.cpp
    src/capture/ScreenCapture.cpp
    src/recording/ScreenRecorder.cpp
    src/recording/GifWriter.cpp
    src/recording/RecordingVisuals.cpp
    src/platform/FileService.cpp
    src/utils/AtomicFile.cpp
    src/output/FBORenderer.cpp
    src/utils/Logger.cpp
    src/utils/DashedLine.cpp
    src/platform/PlatformMainContext.cpp
    src/platform/DaemonProcess.cpp
    src/platform/OcrWindowLayout.cpp
    src/platform/SystemTray.cpp
    src/platform/HotkeyBinding.cpp
    src/ui/Theme.cpp
)

# Platform-specific source files
if(APPLE)
    list(REMOVE_ITEM SHOTLET_CORE_SOURCES src/platform/PlatformMainContext.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/recording/ScreenRecorder_mac.mm)
    list(APPEND SHOTLET_CORE_SOURCES src/recording/GifRecorder_mac.mm src/recording/RecordingVisuals_mac.mm)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/ApplicationPlatform_mac.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/Appearance_mac.mm)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/PlatformMainContext_mac.mm)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/TransparentWindow_mac.mm)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/MagnifierOverlay_mac.mm)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/ClipboardService_mac.mm)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/FontProvider_mac.mm)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/FileService_mac.mm)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/RecordingPlaybackWindow_mac.mm)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/MacImageOutput.mm)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/ImageEditorWindow_mac.mm)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/PinWindow_mac.mm)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/OcrService_mac.mm)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/OcrWindow_mac.mm)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/HotkeyService_mac.mm)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/NativeSystemTray_mac.mm)
    list(APPEND SHOTLET_CORE_SOURCES src/ui/ScreenOverlay_mac.mm)
    list(APPEND SHOTLET_CORE_SOURCES src/core/SmartRegionDetector_mac.mm)
    list(APPEND SHOTLET_CORE_SOURCES src/scrollcapture/MacFrameSource.mm)
    list(APPEND SHOTLET_CORE_SOURCES src/scrollcapture/MacScrollDriver.mm)
    list(APPEND SHOTLET_CORE_SOURCES src/scrollcapture/MacScrollCaptureUI.mm)
elseif(WIN32)
    list(APPEND SHOTLET_CORE_SOURCES src/recording/ScreenRecorder_win.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/recording/RecordingVisuals_win.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/ApplicationPlatform_win.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/WindowsCaptureGuard.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/Appearance_win.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/TransparentWindow_win.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/WindowsDpiAwareness.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/MagnifierOverlay_win.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/ClipboardService_win.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/FontProvider_win.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/FileService_win.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/RecordingPlaybackWindow_win.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/PinWindow_win.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/OcrService_win.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/OcrWindow_win.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/HotkeyService_win.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/NativeSystemTray_win.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/ui/ScreenOverlay_win.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/core/SmartRegionDetector_win.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/scrollcapture/WinFrameSource.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/scrollcapture/WinScrollDriver.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/scrollcapture/WinScrollCaptureUI.cpp)
else()
    list(APPEND SHOTLET_CORE_SOURCES src/recording/ScreenRecorder_stub.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/recording/RecordingVisuals_stub.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/ApplicationPlatform_stub.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/Appearance_stub.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/TransparentWindow_stub.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/MagnifierOverlay_stub.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/ClipboardService_stub.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/FontProvider_stub.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/FileService_stub.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/RecordingPlaybackWindow_stub.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/PinWindow_stub.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/OcrService_stub.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/OcrWindow_stub.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/HotkeyService_stub.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/platform/NativeSystemTray_stub.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/ui/ScreenOverlay_stub.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/core/SmartRegionDetector_stub.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/scrollcapture/MacFrameSource_stub.cpp)
    list(APPEND SHOTLET_CORE_SOURCES src/scrollcapture/MacScrollDriver_stub.cpp)
    if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
        list(REMOVE_ITEM SHOTLET_CORE_SOURCES
            src/platform/FontProvider_stub.cpp src/platform/FileService_stub.cpp)
        list(APPEND SHOTLET_CORE_SOURCES
            src/platform/FontProvider_linux.cpp src/platform/FileService_linux.cpp
            src/platform/ImageOutput_linux.cpp)
        list(APPEND SHOTLET_CORE_SOURCES src/ui/SoftwareIconCache.cpp)
    endif()
endif()

add_library(shotlet_core STATIC ${SHOTLET_CORE_SOURCES} ${IMGUI_SOURCES})

# 仅对已测量的模块优化体积，截图、画布和滚动拼接保留各构建类型的默认选项。
set(SHOTLET_SIZE_OPTIMIZED_SOURCES
    src/history/DocumentCodec.cpp
    src/app/Preferences.cpp
    src/ui/SettingsWindow.cpp
    src/ui/HistoryWindow.cpp
    src/ui/HistoryWindowView.cpp
    ${IMGUI_SOURCES}
)
if(MSVC)
    set(SHOTLET_SIZE_OPTIMIZATION "$<$<CONFIG:Release,MinSizeRel>:/O1>")
elseif(CMAKE_CXX_COMPILER_ID MATCHES "^(AppleClang|Clang|GNU)$")
    set(SHOTLET_SIZE_OPTIMIZATION "$<$<CONFIG:Release,MinSizeRel>:-Os>")
endif()
if(DEFINED SHOTLET_SIZE_OPTIMIZATION)
    set_property(SOURCE ${SHOTLET_SIZE_OPTIMIZED_SOURCES} APPEND PROPERTY
        COMPILE_OPTIONS "${SHOTLET_SIZE_OPTIMIZATION}")
    target_compile_options(SDL3-static PRIVATE "${SHOTLET_SIZE_OPTIMIZATION}")
endif()

target_include_directories(shotlet_core PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${IMGUI_DIR}
    ${IMGUI_DIR}/backends
)

target_link_libraries(shotlet_core PUBLIC ${SDL3_TARGET} Threads::Threads)
if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    find_package(X11 REQUIRED COMPONENTS Xrandr Xinerama)
    find_package(Fontconfig REQUIRED)
    target_link_libraries(shotlet_core PUBLIC
        X11::X11 X11::Xrandr X11::Xinerama Fontconfig::Fontconfig)
endif()
if(NOT WIN32)
    target_link_libraries(shotlet_core PUBLIC ${CMAKE_DL_LIBS})
endif()

target_compile_definitions(shotlet_core PUBLIC
    SHOTLET_VERSION="${PROJECT_VERSION}"
    $<$<PLATFORM_ID:Windows>:SHOTLET_PLATFORM_WINDOWS>
    $<$<PLATFORM_ID:Darwin>:SHOTLET_PLATFORM_MACOS>
    $<$<PLATFORM_ID:Linux>:SHOTLET_PLATFORM_LINUX>
    $<$<PLATFORM_ID:Windows>:_CRT_SECURE_NO_WARNINGS>
)

target_sources(shotlet_core PRIVATE
    $<$<PLATFORM_ID:Darwin>:src/capture/backends/CaptureMacOS_SC.mm>
    $<$<PLATFORM_ID:Windows>:src/capture/backends/CaptureWindows.cpp>
    $<$<PLATFORM_ID:Linux>:src/capture/backends/CaptureLinux.cpp>
)

add_executable(shotlet WIN32 src/main.cpp)
target_link_libraries(shotlet PRIVATE shotlet_core)

if(APPLE)
    target_link_options(shotlet PRIVATE "$<$<CONFIG:Release,MinSizeRel>:-Wl,-dead_strip>")
    foreach(language IN ITEMS en zh-Hans)
        set(localized_info "${CMAKE_CURRENT_SOURCE_DIR}/cmake/macos/${language}.lproj/InfoPlist.strings")
        target_sources(shotlet PRIVATE "${localized_info}")
        set_source_files_properties("${localized_info}" PROPERTIES
            MACOSX_PACKAGE_LOCATION "Resources/${language}.lproj")
    endforeach()
    set_target_properties(shotlet PROPERTIES
        MACOSX_BUNDLE TRUE
        MACOSX_BUNDLE_INFO_PLIST "${CMAKE_CURRENT_SOURCE_DIR}/cmake/macos/Info.plist.in"
        MACOSX_BUNDLE_BUNDLE_NAME "Shotlet"
        MACOSX_BUNDLE_GUI_IDENTIFIER "com.shotlet.app"
        MACOSX_BUNDLE_BUNDLE_VERSION "${PROJECT_VERSION}"
        MACOSX_BUNDLE_SHORT_VERSION_STRING "${PROJECT_VERSION}"
    )

    # Keep a command-line entry point for existing Electron execFile callers
    # while still giving macOS a bundle Info.plist with LSUIElement=true.
    file(GENERATE
        OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/shotlet"
        CONTENT "#!/bin/sh\nexec \"$(dirname \"$0\")/shotlet.app/Contents/MacOS/shotlet\" \"$@\"\n"
        FILE_PERMISSIONS
            OWNER_READ OWNER_WRITE OWNER_EXECUTE
            GROUP_READ GROUP_EXECUTE
            WORLD_READ WORLD_EXECUTE
    )

endif()

# macOS frameworks
if(APPLE)
    find_library(COCOA_FRAMEWORK Cocoa)
    find_library(IOKIT_FRAMEWORK IOKit)
    find_library(COREFOUNDATION_FRAMEWORK CoreFoundation)
    find_library(COREGRAPHICS_FRAMEWORK CoreGraphics)
    find_library(CORETEXT_FRAMEWORK CoreText)
    find_library(FOUNDATION_FRAMEWORK Foundation)
    find_library(SCREENCAPTUREKIT_FRAMEWORK ScreenCaptureKit)
    find_library(COREVIDEO_FRAMEWORK CoreVideo)
    find_library(COREMEDIA_FRAMEWORK CoreMedia)
    find_library(AVFOUNDATION_FRAMEWORK AVFoundation REQUIRED)
    find_library(AVKIT_FRAMEWORK AVKit REQUIRED)
    find_library(COREIMAGE_FRAMEWORK CoreImage)
    find_library(CARBON_FRAMEWORK Carbon)
    find_library(VISION_FRAMEWORK Vision)
    find_library(ACCELERATE_FRAMEWORK Accelerate)
    target_link_libraries(shotlet_core PUBLIC
        ${COCOA_FRAMEWORK}
        ${IOKIT_FRAMEWORK}
        ${COREFOUNDATION_FRAMEWORK}
        ${COREGRAPHICS_FRAMEWORK}
        ${CORETEXT_FRAMEWORK}
        ${FOUNDATION_FRAMEWORK}
        ${SCREENCAPTUREKIT_FRAMEWORK}
        ${COREVIDEO_FRAMEWORK}
        ${COREMEDIA_FRAMEWORK}
        ${AVFOUNDATION_FRAMEWORK}
        ${AVKIT_FRAMEWORK}
        ${COREIMAGE_FRAMEWORK}
        ${CARBON_FRAMEWORK}
        ${VISION_FRAMEWORK}
        ${ACCELERATE_FRAMEWORK}
    )

    # 滚动截图 M2 闭环验证 demo（设计 17.2 M2："命令行或最小 demo 验证注入—稳定—匹配"）
    add_executable(scroll_demo src/scrollcapture/ScrollDemoMain.mm)
    set_source_files_properties(src/scrollcapture/ScrollDemoMain.mm
        PROPERTIES COMPILE_FLAGS "-fobjc-arc"
    )
    target_link_libraries(scroll_demo PRIVATE shotlet_core)
endif()

# Windows platform libraries
if(WIN32)
    target_compile_definitions(shotlet_core PUBLIC SDL_MAIN_HANDLED)
    # C++/WinRT 支持：查找 Windows SDK cppwinrt 头文件目录
    set(CPPWINRT_SEARCH_PATHS
        "C:/Program Files (x86)/Windows Kits/10/Include/${CMAKE_VS_WINDOWS_TARGET_PLATFORM_VERSION}/cppwinrt"
        "$ENV{WindowsSdkDir}Include/$ENV{WindowsSdkVersion}cppwinrt"
    )
    set(CPPWINRT_INCLUDE_DIR "")
    foreach(dir ${CPPWINRT_SEARCH_PATHS})
        if(EXISTS "${dir}/winrt/base.h")
            set(CPPWINRT_INCLUDE_DIR "${dir}")
            break()
        endif()
    endforeach()
    if(CPPWINRT_INCLUDE_DIR)
            target_include_directories(shotlet_core PUBLIC "${CPPWINRT_INCLUDE_DIR}")
    else()
        message(WARNING "C++/WinRT headers not found, OCR will not be available")
    endif()
    target_link_libraries(shotlet_core PUBLIC
        dwmapi shcore gdi32 gdiplus user32 ole32 oleaut32 windowscodecs
        comdlg32 shell32 imm32 setupapi advapi32 winmm version comctl32
        windowsapp
        mf mfplat mfreadwrite mfuuid
    )
    if(MSVC)
        target_compile_options(shotlet_core PUBLIC /W3 /MP /Zc:__cplusplus /utf-8)
        target_link_options(shotlet PRIVATE /ENTRY:mainCRTStartup)
        target_link_options(shotlet PRIVATE "$<$<CONFIG:Release>:/INCREMENTAL:NO>")
    endif()
endif()

# macOS Objective-C++ files need ARC
if(APPLE)
    set_source_files_properties(
        src/capture/backends/CaptureMacOS_SC.mm
        src/recording/ScreenRecorder_mac.mm
        src/recording/GifRecorder_mac.mm
        src/recording/RecordingVisuals_mac.mm
        src/platform/TransparentWindow_mac.mm
        src/platform/MagnifierOverlay_mac.mm
        src/platform/ClipboardService_mac.mm
        src/platform/FontProvider_mac.mm
        src/platform/FileService_mac.mm
        src/platform/RecordingPlaybackWindow_mac.mm
        src/platform/MacImageOutput.mm
        src/platform/ImageEditorWindow_mac.mm
        src/platform/Appearance_mac.mm
        src/platform/PinWindow_mac.mm
        src/platform/OcrService_mac.mm
        src/platform/OcrWindow_mac.mm
        src/platform/HotkeyService_mac.mm
        src/platform/NativeSystemTray_mac.mm
        src/ui/ScreenOverlay_mac.mm
        src/scrollcapture/MacFrameSource.mm
        src/scrollcapture/MacScrollDriver.mm
        src/scrollcapture/MacScrollCaptureUI.mm
        PROPERTIES COMPILE_FLAGS "-fobjc-arc"
    )
endif()

if(SHOTLET_BUILD_NODE_ADDON)
    find_path(NODE_INCLUDE_DIR node_api.h
        PATHS
            "$ENV{HOME}/.nvm/versions/node/v22.19.0/include/node"
            "$ENV{HOME}/.nvm/current/include/node"
            "/usr/local/include/node"
            "/opt/homebrew/include/node"
    )

    if(NODE_INCLUDE_DIR)
        set(SHOTLET_NODE_SOURCES src/node/shotlet_node.cpp)
        if(WIN32)
            list(APPEND SHOTLET_NODE_SOURCES src/node/win_delay_load_hook.cpp)
        endif()

        add_library(shotlet_node MODULE ${SHOTLET_NODE_SOURCES})
        set_target_properties(shotlet_node PROPERTIES
            PREFIX ""
            OUTPUT_NAME "shotlet"
            SUFFIX ".node"
            LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}"
        )
        target_include_directories(shotlet_node PRIVATE ${NODE_INCLUDE_DIR})
        target_link_libraries(shotlet_node PRIVATE shotlet_core)
        target_compile_definitions(shotlet_node PRIVATE NAPI_VERSION=10)
        if(APPLE)
            set_source_files_properties(src/node/shotlet_node.cpp PROPERTIES LANGUAGE OBJCXX)
            set_target_properties(shotlet_node PROPERTIES
                BUNDLE FALSE
                MACOSX_BUNDLE FALSE
            )
            target_link_options(shotlet_node PRIVATE -undefined dynamic_lookup)
            # Node 通过这两个入口注册 addon，其余导出会阻碍未引用代码的移除。
            target_link_options(shotlet_node PRIVATE
                "$<$<CONFIG:Release,MinSizeRel>:-Wl,-dead_strip>"
                "$<$<CONFIG:Release,MinSizeRel>:-Wl,-exported_symbol,_napi_register_module_v1>"
                "$<$<CONFIG:Release,MinSizeRel>:-Wl,-exported_symbol,_node_api_module_get_api_version_v1>"
            )
        elseif(WIN32)
            find_library(NODE_LIBRARY node)
            if(NOT NODE_LIBRARY)
                message(FATAL_ERROR "node.lib not found. Set NODE_LIBRARY to the Node.js import library path.")
            endif()
            target_link_libraries(shotlet_node PRIVATE ${NODE_LIBRARY})
            target_link_options(shotlet_node PRIVATE /DELAYLOAD:node.exe)
            target_link_libraries(shotlet_node PRIVATE delayimp)
        endif()
    else()
        message(WARNING "node_api.h not found, skipping shotlet.node")
    endif()
endif()

# Copy resources
if(EXISTS "${CMAKE_SOURCE_DIR}/resources")
    if(APPLE)
        set(SHOTLET_RESOURCE_OUTPUT_DIR "$<TARGET_BUNDLE_DIR:shotlet>/Contents/Resources")
    else()
        set(SHOTLET_RESOURCE_OUTPUT_DIR "$<TARGET_FILE_DIR:shotlet>/resources")
    endif()
    add_custom_command(TARGET shotlet POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_directory
        "${CMAKE_SOURCE_DIR}/resources" "${SHOTLET_RESOURCE_OUTPUT_DIR}"
        VERBATIM
    )
endif()

if(APPLE)
    find_program(SHOTLET_CODESIGN_EXECUTABLE codesign REQUIRED)
    # 资源复制与剥离完成后签名应用包；仅在重新链接时更新未剥离副本。
    set_property(TARGET shotlet APPEND PROPERTY LINK_DEPENDS
        "${CMAKE_CURRENT_SOURCE_DIR}/cmake/macos/FinalizeReleaseApp.cmake")
    add_custom_command(TARGET shotlet POST_BUILD
        COMMAND ${CMAKE_COMMAND}
            "-DSHOTLET_CONFIG=$<CONFIG>"
            "-DSHOTLET_APP_BINARY=$<TARGET_FILE:shotlet>"
            "-DSHOTLET_APP_BUNDLE=$<TARGET_BUNDLE_DIR:shotlet>"
            "-DSHOTLET_UNSTRIPPED_DIR=${CMAKE_CURRENT_BINARY_DIR}/unstripped"
            "-DSHOTLET_STRIP=${CMAKE_STRIP}"
            "-DSHOTLET_CODESIGN=${SHOTLET_CODESIGN_EXECUTABLE}"
            -P "${CMAKE_CURRENT_SOURCE_DIR}/cmake/macos/FinalizeReleaseApp.cmake"
        VERBATIM
    )
endif()

# Tests
if(SHOTLET_BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()

if(SHOTLET_BUILD_CAPTURE_SDK)
    include(cmake/CaptureSDK.cmake)
endif()

if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    include(cmake/LinuxPackaging.cmake)
endif()
