"""1.19.0: the speech engine for AMD graphics cards (whisper.cpp built with Vulkan).

The release recipe on GitHub (.github/workflows/build-installer.yml) builds that engine once from whisper.cpp's own
source, puts it on this project's Releases page and writes its link, fingerprint and size here before the installer is
made. Left empty (as it is in the source), the "Use my graphics card" switch simply isn't offered on AMD cards."""

VULKAN = {"url": "", "sha256": "", "size": 0}
