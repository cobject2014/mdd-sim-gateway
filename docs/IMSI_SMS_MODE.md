# IMSI 绑定的短信模式（2026-09-10）

用户约定：短信模式保留短信接收和发送，不限制发送。自动设置仅包括蜂窝射频开启、飞行模式关闭、移动数据关闭、VoWiFi 关闭。

入口：设备 → 选中蜂窝模块 → SIM → SIM 使用模式 → 仅短信。按当前实读 IMSI 绑定，界面脱敏显示。切回常规模式恢复手动控制，不自动开启数据。

持久化：网关数据目录下 `orchestrator/sim-policies.json`，权限 0600。当前实现需要 ModemManager 管理的蜂窝模块；普通 PC/SC 读卡器和显式 serial-only 后端无法应用蜂窝射频策略。

界面：总状态根据蜂窝/VoWiFi 的真实注册状态显示；移动数据关闭不等于蜂窝离线；短信模式隐藏 VoWiFi 草稿/SMSC 催办。短信发送仍需运营商接受，未自动发送任何测试短信。

验证：新策略持久化、重启及换卡身份模拟测试；实际网关保存策略、重启编排器后仍保持蜂窝漫游注册且数据关闭；原有两个 AK9563 引擎 ID 不变且 IMS 注册正常。未物理拔插 SIM 进行中断性试验。

备份：数据目录 `backups/before-imsi-policy-20260910.tar.gz`（源码）、`before-imsi-policy-config.yaml`、`before-imsi-policy-devices-desired.json`、`imsi-policy-20260910.patch`。旧控制容器和旧镜像带 `before-imsi-policy-20260910` 后缀保留。

已知基线测试不一致：`test_auto_provision.ExistingModemCardTests.test_metadata_match_migrates_reader_group_without_discovery_apdu` 在修改前后均失败；旧断言没有包含源码已有的 `rebuild_if_running=True` 参数。本次未修改该行为。
