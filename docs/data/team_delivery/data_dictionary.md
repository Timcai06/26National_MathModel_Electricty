# 数据字典 (Data Dictionary)

### 1. day_base.csv (附件1标准表)
- `slot`: 0~143 时段序号 (00:00-00:10 对应 slot 0)。
- `time`: 原始时段结束时刻。
- `price`: 确定性电价 (元/kWh)。
- `load_kw` / `load_kwh`: 小区负荷功率 (kW) 及 10 分钟耗电量 (kWh)。
- `pv_forecast_kw` / `pv_forecast_kwh`: 日前光伏预测功率 (kW) 及发电量 (kWh)。

### 2. annual_actual.csv (附件2标准表)
- `date`: 日期 (YYYY-MM-DD)。
- `slot`: 0~143。
- `time_str`: 原始列标签。
- `load_kw` / `load_kwh`: 实际小区负荷功率 (kW) 及能量 (kWh)。
- `pv_actual_kw` / `pv_actual_kwh`: 实际光伏发电功率 (kW) 及能量 (kWh)。

### 3. pv_forecast.csv (附件3长表)
- `date`: 发布日期 (YYYY-MM-DD)。
- `issue_time`: 发布时刻 (0:00, 6:00, 12:00, 18:00)。
- `target_date`: 目标日期 (跨日自动累加)。
- `target_time`: 目标整点时刻 (HH:00:00)。
- `forecast_horizon`: 预测步长 (1~24 小时)。
- `pv_forecast_kw`: 预测光伏功率 (kW)。

### 4. dynamic_price.csv (附件4标准表)
- `date`: 日期 (YYYY-MM-DD)。
- `slot`: 0~143。
- `price`: 实时交易电价 (元/kWh)。
