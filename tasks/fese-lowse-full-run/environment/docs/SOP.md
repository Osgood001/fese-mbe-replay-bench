# Lab SOP excerpt (real protocol file experiments/fese_grow_v2.md used during the run; Chinese original)

Mapping to the replay CLI: `poll_cnn.py`/`watch_alert.py` -> `fese-lab rheed cnn` / `monitor --channels cnn`; `rheed_w3d.py` -> `fese-lab rheed w3d` / `monitor --channels w3d`; `poll_temps.py` -> `fese-lab get-pv` / `monitor --channels temp`.
English gist: strong 3D (CNN p3D>0.5 sustained) -> close Fe, SeC +20 C, wait for 2D recovery (~2 min after the setpoint is reached), reopen Fe; if not recovered +20 again. Weak 3D (CNN p3D<0.3 but W3D>0.10 for >=5 frames) -> SeC +5..10 C, keep Fe open, re-check W3D; W3D 0.08-0.10 = grey zone, observe. Growth 0.2 layer/min of Fe-open time; stop = close both shutters; then return setpoints to standby.

**判断规则**（2D=理想薄膜 / 3D=Fe 过剩岛状 / STO=衬底裸露）：

| 状态                                | 动作                     |
| ----------------------------------- | ------------------------ |
| 初始 STO → 2D 过渡并保持           | 正常                     |
| 2D 主导（>0.8）                     | 正常，继续监控           |
| 3D <0.2 且回落                      | 正常波动，不动           |
| 3D 持续 >0.5 甚至升高               | **干预循环**（下） |
| 重开 Fe 后 2D 未稳定 >0.9 且 3D<0.1 | **微调 +5°C**     |

**3D 干预循环**：关 Fe（motivation "3D预警"）→ SeC +20°C → 等 2D 恢复 → 重开 Fe；2D 不恢复则继续 +20 爬坡。

- 实测：SeC 每档到位后 ~2min 判定是否恢复，不恢复即升下一档。0812 从 500 起需 520→540→**560** 三次才恢复；0811 需 **600** 才恢复。**550~600 均能维持 2D**。
- 微调：2D 恢复重开后若不能稳定 2D>0.9/3D<0.1，SeC +5（用户可视情况指令 +10）。

**监控节奏**：log 常驻轮询（sleep 循环 + tail）。常规 6s一次。每次查看顺带确认日志时间戳新鲜（坑位 5）。

**弱 3D 监控（W3D 凸度指标，`fese_rheed_lab/rheed_w3d.py`）**：CNN 对弱 3D 不敏感（0812 第二轮实测：CNN 101 帧仅 7 帧 >0.3，多数判 2D，但物理上 0 级杆已出现 3D 鼓包）。W3D 探针：0 级杆纵向剖面的短窗−长窗平滑差（凸度），在 specular 上方 55-105px 行带取最大窗均值（9px），除以**局部邻域背景 B_local**（鼓包上下 26-55px 杆亮度中值——不用 specular，镜面自身随 3D 变暗）。全帧自参考：rod 每帧重配准（信号带 0.12-0.6H、0 级=离屏中心最近峰），specular 帧间追踪——图案平移/漂移无需改坐标。0812 验证：弱 3D 期 W3D≈0.22 持续（93/101 帧 >0.10），干净 2D 期 ≤0.08，零误报。



**弱 3D 判据与决策流程**（CNN 信号弱/报 2D 时以此为准）：

| CNN p(3D) | W3D | 判读 | 动作 |
|-----------|-----|------|------|
| >0.5 | — | 强 3D | 干预循环（关 Fe → SeC +20 爬坡） |
| <0.3（信号弱） | **>0.10 持续（≥5 帧）** | **弱 3D 已出现** | **调节 Se 束流：SeC +5~10°C**，`poll_temps` 到位后每 10-15s 复核 W3D；仍 >0.10 或继续升 → 升级为干预循环（关 Fe） |
| <0.3 | 0.08-0.10 | 弱 3D 灰区/萌芽 | 观察，监控切 10-15s，暂不动；持续 >0.10 再调 |
| 任意 | <0.08 | 干净 2D | 正常，30s 节奏 |

- 每次 SeC 调节后记录 motivation（含 W3D 值与 CNN 值），供复盘。
- W3D 平台（0.10-0.27 区间）持续时间与 SeC 温度的关系是下批实验要积累的核心数据：**目标是找到让 W3D 稳定 <0.08 的最低 SeC**。
- 束流下调同理：W3D 长期 <0.05 且 2D 稳定 >0.9 → 可试探 SeC −5（降 Se 消耗，需用户确认）。

### 5. 停止 + 降温

- 生长速率 0.2 层/min，**只与 Fe 开启的累计时长有关**（SeC 无关；中途关 Fe 的时间不计）。用户报目标层数后按 `累计开启时长×0.2` 换算剩余时间，到点自动停止；无目标厚度则 15min 后询问用户。
- 停止：关双挡板，确认 position_steps=0、is_open=false。
- 降温：三源设回自检记录的初始温度（`set-fe/set-sec/set-seb <初始SP>`，速率同升温），`poll_temps.py` 后台确认到位。

