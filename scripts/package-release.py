#!/usr/bin/env python3
"""校验发布版本，将桌面应用和许可证打包为可分发 ZIP。"""

import argparse
import hashlib
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLATFORMS = ("windows-x64", "macos-arm64", "macos-x64")
HASH_CHUNK_BYTES = 1024 * 1024
ZIP_COMPRESSION_LEVEL = 9
LICENSE_FILES = (
    ("LICENSE", "LICENSE"),
    ("THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md"),
    ("sdl3/LICENSE.txt", "licenses/SDL.txt"),
    ("imgui/LICENSE.txt", "licenses/ImGui.txt"),
    ("src/third_party/nlohmann/LICENSE.MIT", "licenses/nlohmann-json.txt"),
)


def project_version(tag):
    contents = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
    match = re.search(r"project\(shotlet\s+VERSION\s+(\d+\.\d+\.\d+)\s", contents)
    if not match:
        raise ValueError("无法从 CMakeLists.txt 读取项目版本")
    version = match.group(1)
    # 标签和应用内部版本必须一致，避免下载包名与系统显示的版本不同。
    if tag and tag != f"v{version}":
        raise ValueError(f"发布标签必须为 v{version}，当前为 {tag}")
    return version


def stage_package(build, destination, target):
    if target.startswith("macos-"):
        expected_arch = "arm64" if target == "macos-arm64" else "x86_64"
        if sys.platform != "darwin" or platform.machine() != expected_arch:
            raise ValueError(f"请在 {expected_arch} macOS 构建机上打包 {target}")
        bundle = build / "shotlet.app"
        # 检查实际架构与签名，防止矩阵配置错误或资源复制使签名失效。
        subprocess.run(["lipo", str(bundle / "Contents/MacOS/shotlet"),
                        "-verify_arch", expected_arch], check=True)
        subprocess.run(["codesign", "--verify", "--strict", str(bundle)], check=True)
        subprocess.run(["ditto", str(bundle), str(destination / bundle.name)], check=True)
    else:
        shutil.copy2(build / "Release/shotlet.exe", destination / "shotlet.exe")
        resources = build / "Release/resources"
        if resources.is_dir():
            shutil.copytree(resources, destination / "resources")

    for source, relative_destination in LICENSE_FILES:
        output = destination / relative_destination
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / source, output)


def write_archive(package, archive, target):
    if target.startswith("macos-"):
        # ditto 保留应用包的执行权限、符号链接与 macOS 元数据。
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                        str(package), str(archive)], check=True)
        return
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=ZIP_COMPRESSION_LEVEL) as output:
        for path in sorted(package.rglob("*")):
            if path.is_file():
                output.write(path, path.relative_to(package.parent).as_posix())


def package_release(build, output, target, version):
    output.mkdir(parents=True, exist_ok=True)
    name = f"shotlet-{version}-{target}"
    # 先在临时目录完成打包，失败时不覆盖已有 ZIP。
    with tempfile.TemporaryDirectory(prefix="shotlet-release-", dir=output) as temporary:
        staging = Path(temporary)
        package = staging / name
        package.mkdir()
        stage_package(build, package, target)
        archive = staging / f"{name}.zip"
        write_archive(package, archive, target)
        digest = hashlib.sha256()
        with archive.open("rb") as source:
            for chunk in iter(lambda: source.read(HASH_CHUNK_BYTES), b""):
                digest.update(chunk)
        checksum = staging / f"{name}.zip.sha256"
        # 固定 LF 换行，确保 macOS 的 shasum 不会把 Windows 的回车当作文件名。
        checksum.write_text(f"{digest.hexdigest()}  {archive.name}\n", encoding="utf-8", newline="\n")
        archive.replace(output / archive.name)
        checksum.replace(output / checksum.name)
    print(f"Release package created: {output / archive.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument("--platform", choices=PLATFORMS)
    parser.add_argument("--tag", default="", help="正式发布时必须与 CMake 版本一致")
    parser.add_argument("--print-version", action="store_true")
    args = parser.parse_args()
    version = project_version(args.tag)
    if args.print_version:
        print(version)
        return
    if not args.platform:
        parser.error("打包时需要 --platform")
    package_release(args.build_dir.resolve(), args.output.resolve(), args.platform, version)


if __name__ == "__main__":
    main()
