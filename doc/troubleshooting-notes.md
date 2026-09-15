# 排错笔记 & 经验沉淀

## 1. 大数据量 OOM（内存溢出）

### 现象
```
[1] 10809 killed     kedro run
```
exit code 137 = SIGKILL，通常是 OOM Killer。

### 原因
`standardize_report_data` 对 238 万行数据 `iter_rows(named=True)` 逐行 Python 循环，把所有 dict 堆在内存里再转 DataFrame。

```
parsed_report_data: 2,388,015 行
         ↓
  for row in iter_rows():       ← 238万次 Python 循环
      records.append(dict)      ← 238万个 dict 堆内存 ~4.8GB
         ↓
  pl.DataFrame(records)         ← 再复制一次 → OOM 💥
```

### 解决：分批 + Parquet 中间文件

```python
batch_size = 50_000
for batch_start in range(0, n_total, batch_size):
    batch = df.slice(batch_start, batch_size)
    records = [...]  # 只处理 5 万行
    pl.DataFrame(records).write_parquet(tmp_dir / f"batch_{batch_idx:06d}.parquet")
    del records  # 立即释放

result = pl.scan_parquet(tmp_dir / "batch_*.parquet").collect()
```

**原则**：内存占用从「全量 ×2」降到「单批 + 原始 DataFrame（只读）」。

### 进度条

用 `tqdm` 包住 batch 循环，避免干等：

```python
from tqdm import tqdm
for batch_start in tqdm(range(0, n_total, batch_size), desc="标准化", unit="batch"):
    ...
```

---

## 2. DuckDB NaN 导致 JSON 解析失败

### 现象
前端显示「❌ 数据加载失败」，Network 面板看到 HTTP 500 或 AJAX `.fail()` 触发。

### 原因
DuckDB 的 LEFT JOIN 可能产出 `NaN`。Python `flask.jsonify` 会原样输出 `NaN`：

```json
{"账户性质": NaN, "账户类型": NaN}
```

**`NaN` 不是合法 JSON**。浏览器 `JSON.parse` 直接抛异常 `SyntaxError`，触发 AJAX `.fail()`。

### 解决
`jsonify` 之前清洗 NaN → None：

```python
import math

records = df.to_dict(orient="records")
for r in records:
    for k, v in r.items():
        if isinstance(v, float) and math.isnan(v):
            r[k] = None
return jsonify(records)
```

> 注意：`None` 在 JSON 中序列化为 `null`，是合法 JSON。

---

## 3. Kedro Pipeline 执行顺序

| 顺序 | Pipeline 标签 | 说明 |
|------|-------------|------|
| 1 | `ingest` | 解析 Excel → Parquet |
| 2 | `process` | 数据标准化、维度表构建 |
| 3 | `warehouse` | 构建事实表、写入 DuckDB |
| 4 | `treasury_data` | 司库数据（ingest → process → warehouse → dim_bank_branch → geo）|

`finance_report` = ingest + process + warehouse（不含司库）。

跳过已完成的节点：`kedro run --pipeline process` 等。

---

## 4. Flush 之后要重启服务

Kedro pipeline 把数据写入 DuckDB 后，Flask web 服务不会自动感知。必须重启 `my-finance-web` 让 Flask 重新连接 DuckDB（或用 `read_only=False` 连接，但当前实现是 `read_only=True`）。

---

## 5. Kitty 终端 Emoji 不显示

`~/.config/kitty/custom.conf` 添加 `symbol_map`：

```
symbol_map U+1F000-U+1FFFF,U+2600-U+27BF,U+2300-U+23FF,U+FE00-U+FE0F Noto Color Emoji
```

`Ctrl+Shift+F5` 重载配置。

---

## 6. 日报生成失败：papermill 缺失

### 现象
```
The papermill package is required for processing --execute-params
WARN: Error encountered when rendering files
bash: line 5: -P: command not found
```

### 原因
Quarto 通过 `-P year:2026 -P month:6 -P day:30` 传参依赖 `papermill` 包处理 Jupyter 参数化单元格。`quarto` micromamba 环境中未安装 papermill。

### 解决
```bash
micromamba run -n quarto pip install papermill
```

---

## 7. 日报发送失败：mailops 找不到

### 现象
前端点击「发送日报」返回「请求失败，请检查后端日志」。

### 原因（两层）

1. **mailops 不在 PATH**：`mailops` 原本只安装在 `myetl` 环境，发送脚本直接调用 `mailops send` 找不到命令。

2. **mailops 配置路径错误**：`mailops` 的 `project_root()` 通过 `Path(__file__).parent.parent.parent` 推算项目根目录，在 site-packages 下安装后指向 `/home/song/micromamba/envs/quarto/lib/python3.14/`，而非实际项目目录，导致找不到 `config/accounts.yml`。

### 解决

统一使用 `quarto` 环境（与 Quarto 渲染同一环境）：

```bash
# 1. 在 quarto 环境安装 mailops
micromamba run -n quarto pip install mailops

# 2. 复制邮箱配置到 quarto 环境的 site-packages 同级 config/ 目录
mkdir -p /home/song/micromamba/envs/quarto/lib/python3.14/config
cp ~/NutstoreFiles/projects/mailops/config/accounts.yml \
   /home/song/micromamba/envs/quarto/lib/python3.14/config/accounts.yml

# 3. 发送脚本中 mailops 统一通过 micromamba run -n quarto 调用
micromamba run -n quarto mailops send \
    -t "$EMAIL_TO" \
    -s "$EMAIL_SUBJECT" \
    -b "$BODY" \
    -a "$PDF_PATH" \
    -f "$EMAIL_FROM"
```

### 影响范围
- 日报生成 API：`/api/generate_report`
- 日报发送 API：`/api/send_report`
- 自动发送脚本：`filepulse/hooks/treasury_daily.sh`

---

## 8. 内网重建 quarto 环境

内网服务器上原本没有 `quarto` 环境（`micromamba env list` 只有 `base`、`cli`、`myetl`），
而 `report.py`、`treasury_daily.sh` 都调用 `micromamba run -n quarto`，日报链路必挂。
2026-09-15 按下面步骤重建，与环境名、Python 版本与外网保持一致（均为 3.14）：

```bash
# 1. 建环境（quarto 本体 + jupyter 引擎 + qmd 里用到的库）
micromamba create -n quarto -c conda-forge -y \
    quarto python=3.14 pip jupyter polars pyyaml tabulate

# 2. 两个 pip 包：papermill 处理 -P 参数，mailops 发邮件
micromamba run -n quarto pip install papermill mailops

# 3. mailops 配置必须放到环境的 lib/pythonX.Y/config/ 下
#    （mailops 用 Path(__file__).parent.parent.parent 推算项目根，
#     装在 site-packages 下就会指向环境目录而不是项目目录）
micromamba run -n quarto python -c "import site;print(site.getsitepackages()[0])"
# → /home/songwp/micromamba/envs/quarto/lib/python3.14/site-packages
mkdir -p /home/songwp/micromamba/envs/quarto/lib/python3.14/config
cp /home/songwp/projects/mailops/config/accounts.yml \
   /home/songwp/micromamba/envs/quarto/lib/python3.14/config/accounts.yml
```

验证（应全部 OK）：

```bash
PYTHONPATH=/home/song/NutstoreFiles/2-Code/1-MyPython/pybox \
micromamba run -n quarto python -c "
for m in ['polars','yaml','tabulate','IPython','papermill','mailops','siku_utils.helpers']:
    __import__(m); print('OK', m)
"
```

### 已知缺口：LaTeX

`gbt9704-pdf` 走 LaTeX 出 PDF，但内网未装任何 TeX 引擎
（`xelatex` / `pdflatex` / `tlmgr` 均缺失，`quarto check` 报 `TinyTeX: (not installed)`）。
`gbt9704.cls` 是中文字体公文类，装 TinyTeX 后还需补 `ctex` 等宏包，
或改用 conda-forge 的 `texlive-core`。**渲染 PDF 前必须先解决此项。**

### 已知缺口：generated_reports/data 软链

该软链曾指向外网的绝对路径
`/home/song/NutstoreFiles/projects/my-finance-etl/data/01_raw/2026年司库账户数据`，
内网断链。已改为机器无关的相对链接：

```bash
ln -sfn "../data/01_raw/2026年司库账户数据" generated_reports/data
```
