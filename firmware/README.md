# 预构建镜像

预构建镜像作为 GitHub Release 附件分发，不放进 git 历史。下载地址：

<https://github.com/Bright-codern/geoid-cc700pro-di2-page-turn/releases/tag/v1.905-di2>

| 文件 | 用途 | 状态 |
|---|---|---|
| `ota_0_app_di2_gui.bin` | Di2 7170 BLE 翻页单补丁 | 实机验证通过（单按/双击） |

镜像大小为 8,192,000 字节，checksum 为 `0x79`。SHA-256 见
[`SHA256SUMS.txt`](SHA256SUMS.txt)。

## 免责声明

仅用于个人学习、研究和自用，不得商用或据此获利；未经许可不得重新打包、
改名或二次分发；如权利人认为侵权，请通过仓库 Issues 联系，我会立即删除。
完整条款见 [`DISCLAIMER.md`](../DISCLAIMER.md)。

## 刷写前提

- 设备必须是 GEOID CC700 Pro，原厂固件为 `CC700Pro_1.9_V1.905-dirty`。
- 先备份完整 16 MB flash 和当前 app 分区。
- 确认当前活动 OTA 槽：`ota_0` 偏移 `0x20000`，`ota_1` 偏移 `0x7f0000`。
- 只写 app 分区，不动 bootloader、分区表、NVS、BLE 绑定和校准数据。

```powershell
py -3 -m esptool --port COM5 --baud 921600 write_flash 0x20000 ota_0_app_di2_gui.bin
```

## 隐私与内容边界

- 附件只包含 app 分区，不含 NVS、BLE 绑定密钥、校准数据、WiFi 凭据、
  用户数据、设备序列号或云端 token。
- 附件的二进制主体是厂商 app 代码。厂商代码和硬编码的云端/测试配置是固件
  运行所需，**无法在不破坏功能的前提下“抹除代码”**。如果不能再分发厂商
  代码，请只使用仓库里的脚本，从自己的设备读回 app 后本地构建。
- 原始串口日志、完整 flash 备份和 Ghidra 工程没有上传。

## 给其他 agent / 二次修改者

- 所有地址、字节和 segment 长度只对 V1.905 成立。其他版本必须重新定位
  Di2 注入点、GUI 发送函数和 cave。
- 刷写前用 `esptool image-info` 核对 app 版本、segment 3 长度、checksum 和
  validation hash。
- 不要直接把 V1.905 镜像刷到新版本固件或其他机型；先读回目标设备的 app
  并重新分析。
- 如果只需要补丁逻辑，优先使用 `scripts/build_patched_app_gui.py`，不要
  依赖预构建二进制。
