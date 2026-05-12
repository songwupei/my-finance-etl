# 账户地图下方动态明细表方案

## 目标

在账户地图（`bank-account-map`）页面下方增加 AgGrid 动态明细表，实现：

1. **A: 筛选联动表** — 表格与地图共享四维筛选（子集团/银行/省份/城市），筛选条件变化时表和图同步更新
2. **B: 点击联动** — 点击地图气泡，表格只显示该网点的账户明细

## 交互流程

```
用户操作                    地图                     表格
─────────                  ──────                    ──────
页面加载                  显示全部网点              显示全部账户
选筛选条件(如北奔重汽)     地图缩小                  表格同步缩小
点击某网点气泡            高亮该网点                表格只显示该网点账户
清空点击                  恢复筛选后全图            恢复筛选后全表
```

## 实现方案

### 1. 新增 @capture("ag_grid") 函数

在 `bank_account_map` 函数旁边新增，接收相同的 Filter 过滤后 `data_frame`：

```python
@capture("ag_grid")
def account_detail_table(data_frame=None):
    if data_frame is None or data_frame.shape[0] == 0:
        data_frame = _bank_map_account_data
    return data_frame[[
        "sub_group_name",    # 子集团
        "financial_institution",  # 所属银行
        "branch_name",       # 开户网点
        "bank_city",         # 城市
        "province",          # 省份
        "balance_amount",    # 余额(元)
    ]].rename(columns={
        "sub_group_name": "子集团",
        "financial_institution": "所属银行",
        "branch_name": "开户网点",
        "bank_city": "城市",
        "province": "省份",
        "balance_amount": "余额",
    }).sort_values("余额", ascending=False)
```

### 2. 修改页面组件

将单 Graph 改为 Graph + AgGrid 纵向排列：

```python
_vizro_page_bank_map = vm.Page(
    id="bank-account-map",
    title="账户地图",
    components=[
        vm.Graph(
            id="bank-map-graph",
            figure=bank_account_map(data_frame=_bank_map_account_data),
            actions=[vm.Action(filter_interaction=["account-detail-table"])],
        ),
        vm.AgGrid(
            id="account-detail-table",
            figure=account_detail_table(data_frame=_bank_map_account_data),
            title="账户明细表",
        ),
    ],
    controls=[...],  # 现有四个 Filter 不变
)
```

### 3. 点击联动 (filter_interaction)

`vm.Action(filter_interaction=["account-detail-table"])` 让地图成为"驱动器"——点击气泡时，点击数据中的字段值自动作为 AgGrid 的过滤条件。

需要在 `bank_account_map` 的 scattermap marker 中添加 `customdata`，传递网点标识：

```python
# 在 add_scattermap 的 marker 中增加:
customdata=agg[["branch_name"]].values,
```

同时配置 `hovertemplate` 或依赖 Vizro 自动将 `branch_name` 作为 filter_interaction 的 key。

> **注意**: Vizro 的 `filter_interaction` 依赖 Plotly 的 `clickData`。具体行为需实测验证，可能需要调整 `customdata` 字段映射。

### 4. AgGrid 配置

- 列可排序、可筛选（AgGrid 自带）
- 余额列格式化为万元，右对齐
- 默认按余额降序
- 支持导出（AgGrid 自有功能）

```python
vm.AgGrid(
    id="account-detail-table",
    figure=account_detail_table(data_frame=_bank_map_account_data),
    title="账户明细表",
    header="点击地图气泡可筛选此表",
)
```

## 改动范围

只修改 `flask_app.py`：

| 位置 | 内容 | 行数 |
|------|------|------|
| `bank_account_map` 之后 | 新增 `@capture("ag_grid")` 函数 | ~25 行 |
| `_vizro_page_bank_map` 中 | 组件从 `[Graph]` 改为 `[Graph, AgGrid]` | ~10 行 |
| `add_scattermap` 调用处 | 新增 `customdata` | ~3 行 |

总计 ~40 行。

## 风险与降级

| 风险 | 降级方案 |
|------|---------|
| filter_interaction 点击联动不生效 | 去掉 Action，仅保留表图共享筛选 |
| AgGrid 大数据量性能慢 | 限制显示行数 TOP 500，或加虚拟滚动 |
| 余额为元单位不直观 | 在 @capture 内除以 10000 转为万元 |

## 验证步骤

1. 启动 Flask，打开账户地图页
2. 确认表格出现在地图下方
3. 选择筛选条件（如子集团=北奔重汽），确认表格同步过滤
4. 点击某个地图气泡，确认表格只显示该网点账户
5. 清空筛选/点击，确认恢复全表
