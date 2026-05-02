# 集团财务数据标准化处理与可视化平台

基于Kedro数据管道框架的财务数据ETL与可视化平台，支持动态Excel文件扫描、指标标准化处理、组织树构建与可视化展示。

## 项目结构

```
my_finance_etl/
├── conf/                    # 配置文件目录
│   ├── base/               # 基础配置
│   │   ├── catalog.yml     # 数据目录配置
│   │   ├── parameters.yml  # 全局参数
│   │   ├── finance_loader.yml  # Excel解析配置
│   │   ├── indicator_mapping.yml  # 指标标准化配置
│   │   └── standard_accounts.json # 标准科目库
│   └── local/              # 本地配置
│       └── credentials.yml # 数据库凭证
├── src/my_finance_etl/     # 项目源码
│   ├── hooks/              # Kedro钩子
│   │   ├── __init__.py
│   │   └── hooks.py        # 动态Excel加载钩子
│   ├── pipelines/          # 数据管道
│   │   ├── data_ingestion.py   # 数据提取管道
│   │   ├── data_processing.py  # 数据处理管道
│   │   └── data_warehouse.py   # 数据仓库管道
│   ├── __init__.py         # 包初始化
│   ├── __main__.py         # 入口点
│   ├── parser.py           # Excel解析器
│   ├── matcher.py          # 标准科目匹配器
│   ├── tree_builder.py     # 组织树构建器
│   └── pipeline_registry.py # 管道注册器
├── data/                   # 数据目录
│   ├── 01_raw/            # 原始Excel文件
│   ├── 02_intermediate/   # 中间数据
│   └── warehouse/         # 数据仓库文件
├── templates/             # Flask模板
│   └── index.html         # 前端界面
├── flask_app.py           # Flask可视化服务
├── settings.py            # 项目设置
├── pyproject.toml         # 项目配置
├── requirements.txt       # 依赖列表
└── README.md              # 本文档
```

## 功能特性

1. **动态Excel加载**: 自动扫描月度文件夹，根据正则表达式提取元数据
2. **智能解析**: 自动识别基本信息和报表工作表，解析指标层级关系
3. **指标标准化**: 基于标准科目库匹配，支持上下文消歧
4. **组织树构建**: 自动构建集团组织树结构
5. **星型数据模型**: 生成维度表和事实表，存储在DuckDB
6. **可视化展示**: Flask + jsTree提供交互式组织树查看界面

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置数据源

将集团月度财务Excel文件按以下结构放置：
```
data/01_raw/
├── 2024年1月/
│   ├── 集团A-202401-财务.xlsx
│   ├── 集团B-202401-财务.xlsx
│   └── ...
├── 2024年2月/
└── ...
```

文件命名格式：`{集团名称}-{年月}-财务.xlsx`

### 3. 配置项目

编辑配置文件：
- `conf/base/parameters.yml`: 设置集团根代码等参数
- `conf/base/finance_loader.yml`: 调整Excel解析规则
- `conf/base/indicator_mapping.yml`: 配置标准科目映射
- `conf/base/standard_accounts.json`: 维护标准科目库

### 4. 运行ETL管道

```bash
python -m src.my_finance_etl
# 或
kedro run
```

### 5. 启动可视化服务

```bash
python flask_app.py
```

访问 http://localhost:5000 查看集团组织树和财务指标详情。

## 配置说明

### Excel解析配置 (finance_loader.yml)

- `file_pattern`: 文件命名正则表达式
- `sheet_type_rules`: 工作表识别规则
- `numbering_rules`: 指标编号解析规则
- `default_parsing_rules`: 默认解析规则

### 指标标准化配置 (indicator_mapping.yml)

- `standard_account_library`: 标准科目库引用路径
- `context_disambiguation`: 上下文消歧规则
- `hierarchical_matching`: 层级匹配规则

### 数据目录配置 (catalog.yml)

定义Kedro数据集，包括：
- 中间数据: `parsed_excel.*`, `normalized_indicators.*`
- 维度表: `dim_period`, `dim_organization_unit`, `dim_standard_account`, `dim_organization_tree`
- 事实表: `fact_finance_data`

## 数据模型

### 维度表

1. **dim_period**: 期间维度表
2. **dim_organization_unit**: 组织单元维度表  
3. **dim_standard_account**: 标准科目维度表
4. **dim_organization_tree**: 组织树维度表

### 事实表

**fact_finance_data**: 财务事实数据表

## 开发指南

### 扩展功能

1. **添加新的数据源**: 在`src/my_finance_etl/parser.py`中扩展`FinanceExcelParser`类
2. **添加新的指标类型**: 在`src/my_finance_etl/matcher.py`中扩展`StandardAccountMatcher`类
3. **修改可视化界面**: 编辑`templates/index.html`和`flask_app.py`

### 测试数据管道

```bash
kedro test
```

### 调试钩子

动态Excel加载钩子日志位于`logs/my_finance_etl.log`

## 故障排除

### 常见问题

1. **Kedro运行时缺少kedro_init_version错误**: 在`pyproject.toml`中添加`kedro_init_version = "0.19.0"`
2. **Excel文件无法解析**: 检查文件格式和命名规则，参考`finance_loader.yml`配置
3. **标准科目匹配失败**: 验证`standard_accounts.json`格式和`indicator_mapping.yml`配置
4. **可视化服务无法连接数据库**: 检查DuckDB文件路径和权限

### 日志查看

```bash
tail -f logs/my_finance_etl.log
```

## 许可证

MIT License