# 部署配置层

一份代码，多台机器。**环境差异不写进代码，写成配置数据**，这样任何一个
环境做了什么改动，`git diff` 都看得见。

## 加载顺序

后加载的覆盖先加载的：

| 顺序 | 文件 | 进 git | 放什么 |
| --- | --- | --- | --- |
| 1 | `defaults.env` | 是 | 与环境无关的默认值，所有键都在这 |
| 2 | `profiles/<主题>.env` | 是 | 该环境与默认值**不同**的键 |
| 3 | `local.env` | 否 | 本机临时覆盖、敏感值（从 `local.env.example` 复制） |

## 主题选择

`PROFILE` 默认按 `/etc/os-release` 的 `ID` 自动推导，正常不用管：

| ID | 主题 | 环境 |
| --- | --- | --- |
| `arch` | `arch` | 外网（项目在坚果云同步目录内） |
| `openEuler` | `openeuler` | 内网服务器 |

手动覆盖：

```bash
bash start.sh --profile arch
PROFILE=arch bash start.sh
```

## 已固化的差异

| 键 | arch（外网） | openeuler（内网） |
| --- | --- | --- |
| `PROJECTS_ROOT` | `/home/song/NutstoreFiles/projects` | `/home/songwp/projects` |
| `MICROMAMBA_BIN` | `/home/song/micromamba/bin/micromamba` | `/home/songwp/bin/micromamba` |
| `OPEN_BROWSER` | `true` | `false`（无桌面环境） |
| `PKG_HINT_WHIPTAIL` | `sudo pacman -S libnewt` | `sudo dnf install newt` |

两台机器相同的部分（端口 `8765/8000/5001`、环境名 `myetl`、数据区
`/home/song/NutstoreFiles/8-MyData`）只写在 `defaults.env` 里，不重复。

## 脚本约定

`start.sh` / `stop.sh` / `kill.sh` / `kill_shiny.sh` 都从 `lib.sh` 加载配置，
**端口只有一处定义**，不会再出现脚本之间端口不一致导致残留进程占住
DuckDB 锁的问题。

新增机器时：复制一个 `profiles/<主题>.env`，只写与默认值不同的行。

## 体检与可再生资产

| 命令 | 作用 |
| --- | --- |
| `bash deploy/doctor.sh` | 体检（只读，不改任何东西） |
| `bash deploy/doctor.sh --deep` | 依赖检查改为真实 import（慢，更准） |
| `bash deploy/doctor.sh --fix` | 修复可再生项（重建共享区软链、修正 local.env 权限） |
| `bash scripts/link_shared.sh` | 单独重建共享区软链，幂等 |

体检覆盖：路径、共享区软链、运行时与环境、按服务的依赖、端口、本机凭据、
外部配置（filepulse toml）里的每个路径是否真实存在、LaTeX 是否就绪。

### 依赖清单按服务拆分

`deploy/requirements/*.txt`，每行一个模块名；`bin:` 前缀表示外部命令；
首行 `# env: <环境名>` 指定跑在哪个 micromamba 环境（缺省用 `CONDA_ENV`）。

**同一个环境只起一个 python 子进程**做批量检查——每个 `micromamba run`
要 0.3~1 秒并抢锁，逐个模块起进程会慢到没法用。

### 共享区软链不入库

`standards`、`map_utils`、`generated_reports/data` 都指向仓库之外，
入库等于把某台机器的路径固化成事实（三个都踩过断链）。因此改为
`scripts/link_shared.sh` 按 `NUTSTORE_ROOT` 重建，由 doctor 检查。

### TinyTeX 由人工安装

`doctor.sh` 检测不到 `xelatex` 时打印提示词（安装 R → `install.packages('tinytex')`
→ `tinytex::install_tinytex()`），**不在脚本里自动装**。原因见
`deploy/texlive-packages.txt`：内网直连 `github.com/rstudio/tinytex-releases`
会被拦截，而官方安装脚本把下载地址硬编码、不支持配置镜像。
