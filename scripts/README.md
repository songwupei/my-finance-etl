# 独立工具脚本

## geocoder.py

手动触发企业 + 银行地理编码，独立于 kedro run。

### 使用

```bash
# 从项目根目录运行
python scripts/geocoder.py
```

### 功能

- 读取 `data/03_primary/dim_unit_report.parquet` 中待编码企业
- 调用高德 API（geocode + POI 搜索）
- 增量写入 `~/NutstoreFiles/8-MyData/GeoData/geo_enterprise.parquet`
- 同步写入 `data/03_primary/dim_unit_geo.parquet`

### 依赖

- `AMAP_API_KEY_S` 环境变量（高德 Web 服务 API Key）
- `map_utils/amap_client` （位于 `~/NutstoreFiles/2-Code/1-MyPython/0-MyPyPkg/map_utils/`）

### 注意

- `kedro run` 已通过 `enrich_geo_coordinates` pipeline 节点自动编码，通常无需手动运行此脚本
- 此脚本保留用于：修复特定实体坐标、全量补编、调试
